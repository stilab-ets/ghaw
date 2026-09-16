"""Recompute author agreement and resolved taxonomy prevalence, without editing labels."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.labels import ROOT, SAMPLE, annotations, metrics, parents, read, save, vocabulary, write_csv


def main():
    out = ROOT / 'rq3/output'
    a, b, resolved = (annotations(name) for name in ('author_1', 'author_2', 'resolved'))
    labels = vocabulary()
    categories = list(dict.fromkeys(x.split(':', 1)[0] for x in labels))
    eligible = [sid for sid in a if a[sid]['status'] == b[sid]['status'] == 'labeled']
    refs = [set(a[sid]['labels']) for sid in eligible]
    preds = [set(b[sid]['labels']) for sid in eligible]
    summary = dict(eligible_ids=eligible,
                   subcategory=metrics(refs, preds, labels),
                   category=metrics(parents(refs), parents(preds), categories),
                   excluded=[dict(id=sid, author_1_status=a[sid]['status'], author_2_status=b[sid]['status'])
                             for sid in a if sid not in eligible])
    save(out / 'agreement.json', summary)
    rows = [{'label': label, **metrics(refs, preds, [label])} for label in labels]
    write_csv(out / 'agreement_by_label.csv', sorted(rows, key=lambda r: (r['agreement'], r['label'])))
    write_csv(out / 'agreement_by_category.csv', [dict(category=c, **metrics(parents(refs), parents(preds), [c])) for c in categories])
    write_csv(out / 'binary_decisions.csv', [dict(id=sid, label=label, author_1=int(label in ra), author_2=int(label in rb))
                                             for sid, ra, rb in zip(eligible, refs, preds) for label in labels])
    final = [set(c['labels']) for c in resolved.values() if c['status'] == 'labeled']
    for sid, c in resolved.items():
        if c['status'] == 'labeled':
            sa, sb, sf = set(a[sid]['labels']), set(b[sid]['labels']), set(c['labels'])
            assert sa & sb <= sf <= sa | sb, f'Resolution introduced or removed an agreed label: {sid}'
    counts = Counter(x for s in final for x in s)
    category_counts = Counter(x for s in parents(final) for x in s)
    book = {t['label']: t for t in read(SAMPLE / 'taxonomy.json')}
    prevalence = []
    for category in sorted(categories, key=lambda c: (-category_counts[c], c)):
        prevalence.append(dict(level='category', label=category, count=category_counts[category],
                               percent=100 * category_counts[category] / len(final), definition=''))
        for label in sorted((l for l in labels if l.startswith(category + ':')), key=lambda l: (-counts[l], l)):
            prevalence.append(dict(level='subcategory', label=label, count=counts[label],
                                   percent=100 * counts[label] / len(final), definition=book[label]['definition']))
    write_csv(out / 'taxonomy_prevalence.csv', prevalence)
    save(out / 'prevalence.json', dict(denominator=len(final), semantic_assignments=sum(counts.values()),
                                     counts=dict(counts | category_counts), rows=prevalence))
    print(f'RQ3 agreement: {summary["subcategory"]["agreement"]:.2%}, kappa={summary["subcategory"]["kappa"]:.3f}')


if __name__ == '__main__':
    main()
