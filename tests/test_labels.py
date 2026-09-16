"""Focused checks for multi-label metrics and export integrity."""
import unittest
from common.labels import annotations, metrics, parents, vocabulary


class LabelTests(unittest.TestCase):
    def test_pooled_binary_metrics(self):
        result = metrics([{'a'}, {'b'}], [{'a', 'b'}, set()], ['a', 'b'])
        self.assertEqual((result['tp'], result['tn'], result['fp'], result['fn']), (1, 1, 1, 1))
        self.assertEqual(result['agreement'], .5)
        self.assertEqual(result['kappa'], 0)
        self.assertEqual(result['f1'], .5)

    def test_constant_absence_kappa(self):
        result = metrics([set()], [set()], ['a'])
        self.assertIsNone(result['kappa'])
        self.assertEqual(result['agreement'], 1)

    def test_category_deduplicates_children(self):
        self.assertEqual(parents([{'TASK:A', 'TASK:B', 'OUTPUT:C'}]), [{'TASK', 'OUTPUT'}])

    def test_export_ids_and_taxonomy(self):
        a, b, r = (annotations(name) for name in ('author_1', 'author_2', 'resolved'))
        self.assertEqual(set(a), set(b))
        self.assertEqual(set(a), set(r))
        known = set(vocabulary())
        for sid, row in r.items():
            if row['status'] == 'labeled':
                assigned = set(row['labels'])
                self.assertLessEqual(assigned, known)
                self.assertLessEqual(assigned, set(a[sid]['labels']) | set(b[sid]['labels']))
                self.assertLessEqual(set(a[sid]['labels']) & set(b[sid]['labels']), assigned)


if __name__ == '__main__':
    unittest.main()
