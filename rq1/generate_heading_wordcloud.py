#!/usr/bin/env python3
"""Generate a word cloud from headings in retained gh-aw Markdown snapshots."""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections import Counter
from pathlib import Path

import regex
from wordcloud import STOPWORDS, WordCloud

from analyze_rq1 import parse_markdown, split_frontmatter

WORD_PATTERN = regex.compile(r"(?V1)\b[\p{L}\p{N}]+(?:['\u2019-][\p{L}\p{N}]+)*\b")
TEMPLATE_PATTERN = re.compile(r"\$?\{\{.*?\}\}", re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


EXTRA_STOPWORDS = {
    "about",
    "after",
    "again",
    "all",
    "also",
    "and",
    "any",
    "are",
    "can",
    "could",
    "does",
    "done",
    "each",
    "for",
    "from",
    "github",
    "gh",
    "gh-aw",
    "guide",
    "have",
    "how",
    "into",
    "its",
    "just",
    "make",
    "markdown",
    "md",
    "must",
    "new",
    "not",
    "now",
    "only",
    "please",
    "repo",
    "repository",
    "should",
    "that",
    "the",
    "then",
    "this",
    "use",
    "using",
    "when",
    "with",
    "workflow",
    "workflows",
    "your",
}


PALETTE = [
    "#226f8f",
    "#2a9d8f",
    "#4c78a8",
    "#7f52b8",
    "#b66a21",
    "#c44e52",
    "#425466",
]


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    workspace = script_dir.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--retained-csv",
        type=Path,
        default=workspace / "data" / "rq1_rq2_population" / "retained_rq1_rq2_files.csv",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=workspace / "data" / "h",
    )
    parser.add_argument(
        "--figure-dir",
        type=Path,
        default=workspace / "figures",
    )
    parser.add_argument("--output-dir", type=Path, default=script_dir / "output")
    parser.add_argument(
        "--content-focused",
        action="store_true",
        help="Filter generic heading scaffold terms such as step and phase.",
    )
    return parser.parse_args()


def clean_heading(heading: str) -> str:
    heading = TEMPLATE_PATTERN.sub(" ", heading)
    heading = URL_PATTERN.sub(" ", heading)
    heading = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", heading)
    heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
    heading = re.sub(r"`([^`]*)`", r"\1", heading)
    heading = re.sub(r"\{#[-\w]+\}", " ", heading)
    heading = HTML_TAG_PATTERN.sub(" ", heading)
    return heading


def iter_headings(markdown_body: str) -> list[str]:
    tokens = parse_markdown(markdown_body)
    return [
        clean_heading(tokens[index + 1].content)
        for index, token in enumerate(tokens)
        if token.type == "heading_open"
    ]


def excluded_terms(*, content_focused: bool = False) -> set[str]:
    stopwords = {word.lower() for word in STOPWORDS} | EXTRA_STOPWORDS
    if content_focused:
        stopwords |= {
            "action",
            "actions",
            "content",
            "context",
            "criteria",
            "current",
            "details",
            "example",
            "examples",
            "find",
            "found",
            "important",
            "inputs",
            "label",
            "labels",
            "notes",
            "phase",
            "process",
            "required",
            "requirements",
            "rules",
            "scope",
            "step",
            "steps",
            "structure",
            "summary",
            "task",
            "template",
        }
    return stopwords


def tokenize(text: str, *, content_focused: bool = False) -> list[str]:
    stopwords = excluded_terms(content_focused=content_focused)
    tokens = []
    for match in WORD_PATTERN.findall(text.lower()):
        token = match.strip("-_'’")
        if token in stopwords:
            continue
        if len(token) < 3 and token not in {"ai", "ci", "qa"}:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def color_func(*_: object, **__: object) -> str:
    return random.choice(PALETTE)


def main() -> None:
    args = parse_args()
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    heading_counter: Counter[str] = Counter()
    heading_count = 0
    file_count_with_headings = 0

    with args.retained_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            snapshot_path = args.source_root / row["snapshot_relative"]
            if not snapshot_path.exists():
                raise FileNotFoundError(snapshot_path)
            _, body, _, _ = split_frontmatter(
                snapshot_path.read_text(encoding="utf-8-sig", errors="replace")
            )
            headings = iter_headings(body)
            if headings:
                file_count_with_headings += 1
            heading_count += len(headings)
            for heading in headings:
                heading_counter.update(tokenize(heading, content_focused=args.content_focused))

    if not heading_counter:
        raise RuntimeError("No heading terms found.")

    suffix = "_content_terms" if args.content_focused else ""
    frequency_path = args.output_dir / f"rq1_heading_word_frequencies{suffix}.csv"
    with frequency_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["term", "heading_occurrences"])
        writer.writerows(heading_counter.most_common())

    random.seed(7)
    cloud = WordCloud(
        width=2400,
        height=1350,
        background_color="white",
        max_words=140,
        prefer_horizontal=0.92,
        min_font_size=12,
        max_font_size=220,
        relative_scaling=0.45,
        collocations=False,
        margin=6,
        random_state=7,
    ).generate_from_frequencies(heading_counter)
    cloud = cloud.recolor(color_func=color_func, random_state=7)

    png_path = args.figure_dir / f"rq1_heading_wordcloud{suffix}.png"
    pdf_path = args.figure_dir / f"rq1_heading_wordcloud{suffix}.pdf"
    cloud.to_file(str(png_path))

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=300)
    ax.imshow(cloud, interpolation="bilinear")
    ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(pdf_path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    summary_path = args.output_dir / f"rq1_heading_wordcloud_summary{suffix}.txt"
    summary_path.write_text(
        "\n".join(
            [
                f"files_with_headings={file_count_with_headings}",
                f"heading_lines={heading_count}",
                "heading_parser=analyze_rq1.parse_markdown",
                f"excluded_terms={sorted(excluded_terms(content_focused=args.content_focused))}",
                f"distinct_terms={len(heading_counter)}",
                f"top_terms={heading_counter.most_common(25)}",
                f"png={png_path.name}",
                f"pdf={pdf_path.name}",
                f"frequencies={frequency_path.name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
