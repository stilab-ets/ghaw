"""Focused checks for period boundaries, exposure normalization, and pairing."""

import unittest

import numpy as np
import pandas as pd

from analyze_maintenance_periods import aggregate_periods, adjacent_tests, endpoint_tests, size_profile
from change_locations import summarize_events


class PeriodTests(unittest.TestCase):
    def test_location_events_overlap_zero_and_shared_commit(self):
        rows = []
        for repo, path, sha, subsequent, location in (
            ("a", "one", "shared", 1, "frontmatter_only"),
            ("a", "two", "shared", 1, "body_only"),
            ("a", "one", "both", 1, "both"),
            ("a", "one", "empty", 1, "non_content"),
            ("a", "one", "unclassified", 1, "unknown"),
            ("b", "one", "initial", 0, "initial_observation"),
        ):
            rows.append(dict(source_full_name=repo, source_key=repo + ":" + path,
                             commit_sha=sha, is_subsequent_change=subsequent, change_location=location))
        events, projects = summarize_events(pd.DataFrame(rows))
        projects = projects.set_index("source_full_name")
        self.assertEqual(len(events), 5)
        self.assertEqual(projects.loc["a", "maintenance_events"], 5)
        self.assertEqual(projects.loc["a", "frontmatter_percent"], 40)
        self.assertEqual(projects.loc["a", "body_percent"], 40)
        self.assertTrue(projects.loc["b", "zero_event_convention"])
        self.assertEqual(projects.loc["b", "body_percent"], 0)
        self.assertEqual(projects.frontmatter_percent.median(), 20)
        with self.assertRaises(ValueError):
            summarize_events(pd.DataFrame(rows + [rows[0]]))

    def test_time_weighted_size_and_deletion(self):
        self.assertEqual(size_profile(np.array([0., 14.]), np.array([100., 200.]), 0, 28), (100, 200, 150))
        self.assertEqual(size_profile(np.array([14.]), np.array([100.]), 0, 28), (0, 100, 50))
        self.assertEqual(size_profile(np.array([0., 14.]), np.array([100., 0.]), 0, 28), (100, 0, 50))

    def test_periods_zero_activity_and_project_deduplication(self):
        origin = pd.Timestamp("2025-01-01", tz="UTC")
        rows = []
        for path in ("a", "b"):
            for day, sha, initial, churn in ((0, "initial", 0, 100), (28, "shared", 1, 2), (29, "later", 1, 2)):
                rows.append(dict(source_key=path, source_full_name="repo", committed_at=origin + pd.Timedelta(days=day),
                                 commit_sha=sha, is_subsequent_change=initial, snapshot_line_count=100,
                                 file_changes=churn, file_additions=churn // 2, file_deletions=churn // 2))
        result, _ = aggregate_periods(pd.DataFrame(rows), pd.Series({"repo": origin}), "source_full_name")
        self.assertEqual(result.maintenance_commits.tolist(), [1, 1, 0, 0])
        self.assertEqual(result.churn.tolist(), [4, 4, 0, 0])
        self.assertEqual(result.relative_churn.tolist(), [2, 2, 0, 0])
        self.assertEqual(result.end_size.tolist(), [200] * 4)

    def test_sign_test_ties_and_holm(self):
        rows = []
        for project in range(12):
            for period in range(1, 5):
                rows.append(dict(source_full_name=str(project), period=period,
                                 maintenance_commits=period if project < 10 else 1,
                                 relative_churn=100 - period if project < 10 else 1,
                                 end_size=100))
        tests = endpoint_tests(pd.DataFrame(rows)).set_index("metric")
        self.assertEqual(tests.loc["maintenance_commits", "higher"], 10)
        self.assertEqual(tests.loc["maintenance_commits", "ties"], 2)
        self.assertAlmostEqual(tests.loc["maintenance_commits", "p_value"], 2 / 1024)
        self.assertEqual(tests.loc["relative_churn", "lower"], 10)
        self.assertEqual(tests.loc["end_size", "holm_p_value"], 1)
        self.assertTrue((tests.holm_p_value >= tests.p_value).all())

    def test_adjacent_pairing_and_undefined_shares(self):
        rows = []
        for project in range(12):
            for period in range(1, 5):
                value = (1, 3, 3, 2)[period - 1]
                rows.append(dict(source_full_name=str(project), period=period,
                                 maintenance_commits=value, relative_churn=value, end_size=value,
                                 maintenance_commit_share=np.nan if project == 0 and period == 3 else value))
        tests = adjacent_tests(pd.DataFrame(rows))
        self.assertEqual(len(tests), 12)
        commits = tests.loc[tests.metric.eq("maintenance_commits")].set_index("period")
        self.assertEqual(commits.higher.tolist(), [12, 0, 0])
        self.assertEqual(commits.lower.tolist(), [0, 0, 12])
        self.assertEqual(commits.loc[3, "ties"], 12)
        self.assertEqual(commits.loc[2, "median_paired_difference"], 2)
        shares = tests.loc[tests.metric.eq("maintenance_commit_share")].set_index("period")
        self.assertEqual(shares.projects.tolist(), [12, 11, 11])
        self.assertTrue((tests.holm_p_value >= tests.p_value).all())


if __name__ == "__main__":
    unittest.main()
