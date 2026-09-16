"""Compare regenerated measurements with frozen paper results and validate input identity."""
import hashlib
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.labels import ROOT, SAMPLE, read, save

REFERENCE = ROOT / 'verification/reference'


def close(a, b):
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a:
            close(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            close(x, y)
    elif isinstance(a, (float, int)):
        assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10), (a, b)
    else:
        assert a == b, (a, b)


def compare_csv(a, b):
    pd.testing.assert_frame_equal(pd.read_csv(a), pd.read_csv(b), check_dtype=False,
                                  check_exact=False, rtol=1e-10, atol=1e-10)


def main():
    checks = []
    hashes = read(ROOT / 'verification/input_sha256.json')
    for name, expected in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, f'Input changed: {name}'
    checks.append('Frozen input byte hashes')
    compare_csv(ROOT / 'rq1/output/rq1_per_file_metrics.csv', REFERENCE / 'rq1/rq1_per_file_metrics.csv')
    compare_csv(ROOT / 'rq1/output/rq1_heading_word_frequencies_content_terms.csv', REFERENCE / 'rq1/rq1_heading_word_frequencies_content_terms.csv')
    table = pd.read_csv(ROOT / 'rq1/output/paper_table.csv')
    expected_table = read(REFERENCE / 'paper_table_rq1.json')
    for row in table.to_dict('records'):
        exp = expected_table[row['metric']]
        for field in ('min', 'mean', 'median', 'max'):
            displayed = exp[field]
            decimals = len(displayed.split('.')[1]) if '.' in displayed else 0
            assert f'{row[field]:.{decimals}f}' == displayed, (row['metric'], field, row[field], displayed)
    checks.append('RQ1 per-file measurements, heading frequencies, and paper table rounding')
    for name in ('rq2_per_file_metrics.csv', 'rq2_per_event_metrics.csv'):
        compare_csv(ROOT / 'rq2/output' / name, REFERENCE / 'rq2' / name)
    corpus = read(ROOT / 'rq2/output/corpus_summary.json')
    close(corpus, dict(markdown_files=1248, source_repositories=276,
                       distinct_markdown_commits=7446, markdown_file_changes=20841,
                       first_commit_date='2025-07-31', last_commit_date='2026-08-04'))
    for name in ('file_period_metrics.csv', 'project_period_metrics.csv', 'project_adjacent_month_tests.csv',
                 'project_change_locations.csv', 'project_activity_adjusted_metrics.csv'):
        compare_csv(ROOT / 'rq2/output/maintenance_periods_120d' / name, REFERENCE / 'rq2' / name)
    current = read(ROOT / 'rq2/output/maintenance_periods_120d/summary.json')
    previous = read(REFERENCE / 'rq2/summary.json')
    for key in ('selected_files', 'projects', 'repository_files', 'file', 'project', 'edit_nature',
                'project_adjacent_month_tests', 'project_activity'):
        close(current[key], previous[key])
    checks.append('RQ2 event histories, monthly metrics, edit targets, and corrected tests')
    agreement = read(ROOT / 'rq3/output/agreement.json')
    expected = read(REFERENCE / 'rq3_agreement.json')
    assert agreement['eligible_ids'] == expected['eligible_ids']
    for level, reference_level in [('category', 'high_level'), ('subcategory', 'low_level')]:
        close(agreement[level]['agreement'], expected[reference_level]['agreement_rate'])
        close(agreement[level]['kappa'], expected[reference_level]['cohens_kappa'])
    prevalence = read(ROOT / 'rq3/output/prevalence.json')
    close(prevalence['counts'], read(REFERENCE / 'rq3_prevalence.json')['counts'])
    close(prevalence['denominator'], read(REFERENCE / 'rq3_prevalence.json')['denominator'])
    checks.append('RQ3 author agreement and every resolved category/subcategory frequency')
    expected = read(REFERENCE / 'rq4.json')
    for row in read(ROOT / 'rq4/output/comparison.json'):
        key = f'{row["model"]}/{row["shots"]}'
        for metric in ('tp', 'tn', 'fp', 'fn', 'agreement', 'kappa', 'precision', 'recall', 'f1'):
            close(row[metric], expected[key][metric])
    checks.append('RQ4 all model/shot metrics and confusion counts')
    manifest = {x['id']: x for x in read(SAMPLE / 'manifest.json')}
    for shot in (1, 3, 5):
        demos = read(ROOT / f'rq4/prompts/{shot}shot_demonstrations.json')
        for target in demos:
            for label in target['selected']:
                assert len(label['examples']) == shot
                for example in label['examples']:
                    assert example['id'] != target['id'], 'Target leaked into its demonstrations'
                    assert example['source_sha256'] == manifest[example['id']]['source_sha256']
                    lines = (SAMPLE / f'snapshots/{example["id"]}.md').read_text(encoding='utf-8-sig').splitlines()
                    assert example['text'] == '\n'.join(lines[example['start_line'] - 1:example['end_line']])
    checks.append('Few-shot target exclusion and exact source snippets')
    save(ROOT / 'verification/report.json', dict(status='passed', checks=checks))
    print('\n'.join('PASS: ' + c for c in checks))


if __name__ == '__main__':
    main()
