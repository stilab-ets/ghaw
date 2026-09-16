"""Check that the word cloud and structural metrics use identical headings."""

import unittest

from analyze_rq1 import markdown_metrics, split_frontmatter
from generate_heading_wordcloud import iter_headings, tokenize


class HeadingExtractionTests(unittest.TestCase):
    def test_markdown_constructs(self):
        cases = [
            ("# Title\n\n## Section\n", ["Title", "Section"]),
            ("Title\n=====\n\nSection\n-------\n", ["Title", "Section"]),
            ("> ## Quoted heading\n\n- ### Nested heading\n",
             ["Quoted heading", "Nested heading"]),
            ("````markdown\n```\n# Not a heading\n````\n# Visible\n", ["Visible"]),
            ("    # Indented code\n\n# Visible\n", ["Visible"]),
            ("Paragraph\n\n---\n", []),
            ("<div>\n# Inside HTML\n</div>\n\n# Visible\n", ["Visible"]),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                headings = iter_headings(body)
                self.assertEqual(expected, headings)
                self.assertEqual(markdown_metrics(body)["heading_count"], len(headings))

    def test_frontmatter_is_excluded(self):
        _, body, _, _ = split_frontmatter("---\n# YAML comment\nname: test\n---\n# Body\n")
        self.assertEqual(["Body"], iter_headings(body))

    def test_content_filter_is_preserved(self):
        self.assertEqual(["issue", "report"], tokenize("The task process rules issue report", content_focused=True))


if __name__ == "__main__":
    unittest.main()
