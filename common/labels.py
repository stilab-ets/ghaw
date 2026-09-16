"""Validated annotation loading and pooled binary classification metrics."""
import csv
import json
import math
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'data/rq3_sample'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def vocabulary():
    return [x['label'] for x in read(SAMPLE / 'taxonomy.json')]


def annotations(name):
    rows = read(SAMPLE / 'labels' / (name + '.json'))['cases']
    manifest = {x['id']: x for x in read(SAMPLE / 'manifest.json')}
    result = {x['id']: x for x in rows}
    if len(result) != len(rows) or set(result) != set(manifest):
        raise ValueError(f'Duplicate or mismatched sample IDs in {name}')
    known = set(vocabulary()) | {'Cannot Label:Cannot Label'}
    for sid, row in result.items():
        if row['snapshot_url'] != manifest[sid]['url']:
            raise ValueError(f'Snapshot mismatch: {name}/{sid}')
        labels = set(row['labels'])
        if len(labels) != len(row['labels']) or not labels <= known:
            raise ValueError(f'Duplicate or unknown labels: {name}/{sid}')
        if row['status'] == 'labeled' and (not labels or 'Cannot Label:Cannot Label' in labels):
            raise ValueError(f'Invalid semantic labels: {name}/{sid}')
    return result


def metrics(references, predictions, labels):
    if not references or len(references) != len(predictions):
        raise ValueError('Empty or mismatched comparisons')
    a = np.array([[int(l in r) for l in labels] for r in references]).ravel()
    b = np.array([[int(l in r) for l in labels] for r in predictions]).ravel()
    tp = int(((a == 1) & (b == 1)).sum())
    tn = int(((a == 0) & (b == 0)).sum())
    fp = int(((a == 0) & (b == 1)).sum())
    fn = int(((a == 1) & (b == 0)).sum())
    n = len(a)
    agreement = (tp + tn) / n
    chance = ((tp + fn) * (tp + fp) + (fp + tn) * (fn + tn)) / n**2
    kappa = (agreement - chance) / (1 - chance) if chance != 1 else None
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else 0.
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.
    if kappa is not None:
        assert math.isclose(kappa, cohen_kappa_score(a, b, labels=[0, 1]), abs_tol=1e-12)
    p, r, f, _ = precision_recall_fscore_support(a, b, average='binary', zero_division=0)
    assert np.allclose([p, r, f], [precision, recall, f1], atol=1e-12)
    return dict(tp=tp, tn=tn, fp=fp, fn=fn, agreement=agreement, kappa=kappa,
                precision=precision, recall=recall, f1=f1)


def parents(sets):
    return [{x.split(':', 1)[0] for x in s} for s in sets]
