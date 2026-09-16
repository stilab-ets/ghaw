"""Evaluate saved model predictions against the resolved annotations, entirely offline."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.labels import ROOT, SAMPLE, annotations, metrics, parents, read, save, vocabulary, write_csv


def main():
    reference = annotations('resolved')
    eligible = [sid for sid, c in reference.items() if c['status'] == 'labeled']
    manifest = {x['id']: x for x in read(SAMPLE / 'manifest.json')}
    labels = vocabulary()
    categories = list(dict.fromkeys(x.split(':', 1)[0] for x in labels))
    references = [set(reference[sid]['labels']) for sid in eligible]
    results, category_results = [], []
    out = ROOT / 'rq4/output'
    for model in ('gemini', 'glm_5_2', 'gpt_oss_120b'):
        for shot in (0, 1, 3, 5):
            data = read(ROOT / f'rq4/predictions/{model}/{shot}shot.json')
            assert data['model'] == model and data['shots'] == shot
            rows = {x['id']: x for x in data['cases']}
            assert len(rows) == len(data['cases']) and set(rows) == set(manifest)
            for sid, row in rows.items():
                assert row['status'] == 'ok', f'Failed prediction: {model}/{shot}/{sid}'
                snapshot = SAMPLE / f'snapshots/{sid}.md'
                assert row['snapshot_sha256'] == manifest[sid]['source_sha256'] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
                assert row['included_in_evaluation'] == (sid in eligible)
                assigned = [x['label'] for x in row['prediction']['labels']]
                assert len(assigned) == len(set(assigned)) and set(assigned) <= set(labels)
                lines = snapshot.read_text(encoding='utf-8-sig').splitlines()
                for item in row['prediction']['labels']:
                    assert 1 <= len(item['evidence_lines']) <= 3
                    for n in item['evidence_lines']:
                        assert manifest[sid]['body_start_line'] <= n <= len(lines)
                    for evidence in item.get('evidence', []):
                        assert evidence['line'] in item['evidence_lines']
                        assert evidence['quote'] == lines[evidence['line'] - 1]
            predictions = [{x['label'] for x in rows[sid]['prediction']['labels']} for sid in eligible]
            result = dict(model=model, shots=shot, **metrics(references, predictions, labels))
            results.append(result)
            category_results.append(dict(model=model, shots=shot, **metrics(parents(references), parents(predictions), categories)))
            per_label = [dict(label=label, reference_positive=sum(label in r for r in references),
                              predicted_positive=sum(label in p for p in predictions),
                              **metrics(references, predictions, [label])) for label in labels]
            write_csv(out / model / f'{shot}shot_by_label.csv', sorted(per_label, key=lambda r: (r['agreement'], r['label'])))
            write_csv(out / model / f'{shot}shot_by_file.csv', [dict(id=sid, tp=len(r & p), fp=len(p-r), fn=len(r-p),
                        reference_labels=' | '.join(sorted(r)), predicted_labels=' | '.join(sorted(p)))
                        for sid, r, p in zip(eligible, references, predictions)])
    save(out / 'comparison.json', results)
    write_csv(out / 'comparison.csv', results)
    write_csv(out / 'category_comparison.csv', category_results)
    lines = ['| Model | Shots | Agreement | Kappa | Precision | Recall | F1 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in results:
        lines.append(f'| {r["model"]} | {r["shots"]} | {r["agreement"]:.2%} | {r["kappa"]:.3f} | {r["precision"]:.3f} | {r["recall"]:.3f} | {r["f1"]:.3f} |')
    (out / 'paper_table.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
