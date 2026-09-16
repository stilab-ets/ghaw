#!/usr/bin/env python3
"""Compute reproducible RQ1 characteristics for latest gh-aw Markdown snapshots."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import regex
import yaml
import nltk
from langdetect import DetectorFactory, LangDetectException, detect_langs
from markdown_it import MarkdownIt
from textstat import textstat
from textstat.backend.counts import count_syllables

nltk.data.path.insert(0, str(Path(__file__).resolve().parents[1] / "data/nltk_data"))
nltk.data.find("corpora/cmudict")


DetectorFactory.seed = 0

WORD_PATTERN = regex.compile(
    r"(?V1)\b[\p{L}\p{N}]+(?:['\u2019-][\p{L}\p{N}]+)*\b"
)
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
TEMPLATE_PATTERN = re.compile(r"\$?\{\{.*?\}\}", re.DOTALL)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
TERMINAL_PUNCTUATION_PATTERN = re.compile(r"[.!?][\"')\]]*$")
STATUS_SYMBOL_PATTERN = regex.compile(r"\p{Extended_Pictographic}")

READABILITY_MIN_WORDS = 100
READABILITY_MIN_ENGLISH_PROBABILITY = 0.80


class FrontmatterLoader(yaml.BaseLoader):
    """YAML loader that preserves keys such as `on` as strings."""


def _construct_unknown(loader: FrontmatterLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


FrontmatterLoader.add_constructor(None, _construct_unknown)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    workspace = script_dir.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=workspace / "data" / "h",
    )
    parser.add_argument("--output-dir", type=Path, default=script_dir / "output")
    parser.add_argument(
        "--exclude-source-keys",
        type=Path,
        default=workspace / "data" / "rq1_rq2_population" / "excluded_source_keys.txt",
        help="Optional newline-delimited source keys to remove from the RQ1/RQ2 population.",
    )
    return parser.parse_args()


def canonical_key(value: Any) -> str:
    return str(value).strip().lower().replace("_", "-")


def split_frontmatter(text: str) -> tuple[str, str, bool, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", normalized, False, "absent"
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            return "".join(lines[1:index]), "".join(lines[index + 1 :]), True, "ok"
    return "", normalized, False, "unterminated"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.strip():
        return {}, "empty"
    try:
        parsed = yaml.load(text, Loader=FrontmatterLoader)
    except yaml.YAMLError:
        return {}, "parse_error"
    if parsed is None:
        return {}, "empty"
    if not isinstance(parsed, dict):
        return {}, "not_mapping"
    return {canonical_key(key): value for key, value in parsed.items()}, "ok"


def recursive_mapping_key_count(value: Any) -> int:
    if isinstance(value, dict):
        return len(value) + sum(recursive_mapping_key_count(v) for v in value.values())
    if isinstance(value, list):
        return sum(recursive_mapping_key_count(item) for item in value)
    return 0


def configured_names(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [canonical_key(key) for key in value]
    if isinstance(value, list):
        return [canonical_key(item) for item in value if not isinstance(item, (dict, list))]
    if value is None or str(value).strip() == "":
        return []
    return [canonical_key(value)]


def normalized_scalar(value: Any) -> str:
    if isinstance(value, (dict, list)) or value is None:
        return ""
    return canonical_key(value)


def normalized_engine(value: Any) -> str:
    if isinstance(value, dict):
        normalized = {canonical_key(key): item for key, item in value.items()}
        for candidate in ("id", "name", "engine"):
            result = normalized_scalar(normalized.get(candidate))
            if result:
                return result
        return "unresolved-mapping"
    if isinstance(value, list):
        for item in value:
            result = normalized_engine(item)
            if result:
                return result
        return "unresolved-list"
    return normalized_scalar(value)


def count_words(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def clean_text(text: str, code_placeholder: bool) -> str:
    value = TEMPLATE_PATTERN.sub(" value ", text)
    value = URL_PATTERN.sub(" ", value)
    value = HTML_TAG_PATTERN.sub(" ", value)
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    if code_placeholder:
        return value
    return value


def inline_text(token: Any, code_placeholder: bool) -> tuple[str, dict[str, int]]:
    parts: list[str] = []
    counts = {"links": 0, "images": 0, "inline_code": 0}
    children = token.children or []
    for child in children:
        if child.type == "text":
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
        elif child.type == "code_inline":
            counts["inline_code"] += 1
            if code_placeholder:
                parts.append(" code ")
        elif child.type == "link_open":
            counts["links"] += 1
        elif child.type == "image":
            counts["images"] += 1
        elif child.type == "html_inline" and not child.content.lstrip().startswith("<!--"):
            parts.append(HTML_TAG_PATTERN.sub(" ", child.content))
    return clean_text(" ".join(parts), code_placeholder), counts


def parse_markdown(body: str) -> list[Any]:
    return MarkdownIt("commonmark", {"html": True}).enable("table").parse(body)


def markdown_metrics(body: str) -> dict[str, Any]:
    tokens = parse_markdown(body)
    stack: list[str] = []
    heading_counts = {f"h{level}_count": 0 for level in range(1, 7)}
    heading_levels: list[int] = []
    all_blocks: list[str] = []
    prose_blocks: list[str] = []
    feature_counts = Counter()

    for token in tokens:
        if token.nesting == -1:
            if stack:
                stack.pop()
            continue

        parent = stack[-1] if stack else ""

        if token.type == "heading_open":
            level = int(token.tag[1])
            heading_counts[f"h{level}_count"] += 1
            heading_levels.append(level)
        elif token.type == "paragraph_open":
            feature_counts["paragraph_count"] += 1
        elif token.type == "list_item_open":
            feature_counts["list_item_count"] += 1
        elif token.type == "bullet_list_open":
            feature_counts["bullet_list_count"] += 1
        elif token.type == "ordered_list_open":
            feature_counts["ordered_list_count"] += 1
        elif token.type in {"fence", "code_block"}:
            feature_counts["code_block_count"] += 1
            feature_counts["code_block_lines"] += len(token.content.splitlines())
        elif token.type == "blockquote_open":
            feature_counts["blockquote_count"] += 1
        elif token.type == "table_open":
            feature_counts["table_count"] += 1
        elif token.type == "inline":
            body_text, body_counts = inline_text(token, code_placeholder=False)
            prose_text, _ = inline_text(token, code_placeholder=True)
            feature_counts.update(body_counts)
            if body_text:
                all_blocks.append(body_text)
            if parent == "paragraph_open" and prose_text:
                if not TERMINAL_PUNCTUATION_PATTERN.search(prose_text):
                    prose_text += "."
                prose_blocks.append(prose_text)

        if token.nesting == 1:
            stack.append(token.type)

    heading_skip_count = sum(
        1 for previous, current in zip(heading_levels, heading_levels[1:])
        if current > previous + 1
    )
    natural_body_text = "\n".join(all_blocks)
    readability_text = "\n".join(prose_blocks)
    total_headings = sum(heading_counts.values())
    body_word_count = count_words(natural_body_text)

    metrics: dict[str, Any] = {
        **heading_counts,
        **feature_counts,
        "heading_count": total_headings,
        "max_heading_level": max(heading_levels, default=0),
        "heading_skip_count": heading_skip_count,
        "starts_above_h1": int(bool(heading_levels) and heading_levels[0] > 1),
        "multiple_h1": int(heading_counts["h1_count"] > 1),
        "body_word_count": body_word_count,
        "readability_word_count": count_words(readability_text),
        "natural_body_text": natural_body_text,
        "readability_text": readability_text,
        "template_expression_count": len(TEMPLATE_PATTERN.findall(body)),
        "status_symbol_count": len(STATUS_SYMBOL_PATTERN.findall(body)),
    }
    for key in [
        "paragraph_count", "list_item_count", "bullet_list_count", "ordered_list_count",
        "code_block_count", "code_block_lines", "blockquote_count", "table_count",
        "links", "images", "inline_code",
    ]:
        metrics.setdefault(key, 0)
    metrics["heading_density_per_1000_words"] = (
        total_headings * 1000 / body_word_count if body_word_count else 0.0
    )
    return metrics


def detect_language(text: str) -> tuple[str, float]:
    if count_words(text) < 20:
        return "insufficient", 0.0
    try:
        candidates = detect_langs(text[:20000])
    except LangDetectException:
        return "unknown", 0.0
    if not candidates:
        return "unknown", 0.0
    top = candidates[0]
    return top.lang, float(top.prob)


def readability_metrics(text: str, language: str, probability: float) -> dict[str, Any]:
    word_count = count_words(text)
    eligible = (
        language == "en"
        and probability >= READABILITY_MIN_ENGLISH_PROBABILITY
        and word_count >= READABILITY_MIN_WORDS
    )
    if not eligible:
        return {
            "readability_eligible": 0,
            "flesch_reading_ease": "",
            "flesch_kincaid_grade": "",
            "gunning_fog": "",
            "sentence_count": "",
            "readability_syllable_count": "",
        }
    textstat.set_lang("en_US")
    return {
        "readability_eligible": 1,
        "flesch_reading_ease": float(textstat.flesch_reading_ease(text)),
        "flesch_kincaid_grade": float(textstat.flesch_kincaid_grade(text)),
        "gunning_fog": float(textstat.gunning_fog(text)),
        "sentence_count": int(textstat.sentence_count(text)),
        "readability_syllable_count": int(count_syllables(text, "en_US")),
    }


def iter_snapshot_changes(history: dict[str, Any], history_path: Path) -> Iterable[dict[str, Any]]:
    for commit in history.get("commits", []):
        for change in commit.get("md_changes", []):
            snapshot_file = change.get("snapshot_file")
            if not snapshot_file or change.get("snapshot_error"):
                continue
            snapshot_path = history_path.parent / Path(snapshot_file)
            if not snapshot_path.is_file():
                continue
            yield {
                "committed_at": change.get("committed_at") or commit.get("committed_at") or "",
                "commit_sha": change.get("commit_sha") or commit.get("commit_sha") or "",
                "event_status": change.get("event_status", ""),
                "snapshot_file": snapshot_file,
                "snapshot_path": snapshot_path,
            }


def latest_record(history_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    with history_path.open("r", encoding="utf-8") as handle:
        history = json.load(handle)
    changes = list(iter_snapshot_changes(history, history_path))
    if not changes:
        return None, history
    latest = max(changes, key=lambda row: (row["committed_at"], row["commit_sha"]))
    return latest, history


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def describe(values: Iterable[Any]) -> dict[str, float | int]:
    numeric = [float(value) for value in values if value != "" and value is not None]
    if not numeric:
        return {"n": 0}
    return {
        "n": len(numeric),
        "mean": statistics.fmean(numeric),
        "sd": statistics.stdev(numeric) if len(numeric) > 1 else 0.0,
        "min": min(numeric),
        "p25": percentile(numeric, 0.25),
        "median": percentile(numeric, 0.50),
        "p75": percentile(numeric, 0.75),
        "p90": percentile(numeric, 0.90),
        "p95": percentile(numeric, 0.95),
        "max": max(numeric),
    }


def prevalence(counter: Counter[str], denominator: int) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count, "percent": count * 100 / denominator}
        for name, count in counter.most_common()
    ]


def flesch_band(score: float) -> str:
    if score >= 90:
        return "very_easy"
    if score >= 80:
        return "easy"
    if score >= 70:
        return "fairly_easy"
    if score >= 60:
        return "standard"
    if score >= 50:
        return "fairly_difficult"
    if score >= 30:
        return "difficult"
    return "very_difficult"


def analyze_file(history_path: Path, source_root: Path) -> dict[str, Any] | None:
    latest, history = latest_record(history_path)
    if latest is None:
        return None
    raw_bytes = latest["snapshot_path"].read_bytes()
    text = raw_bytes.decode("utf-8", errors="replace")
    frontmatter_text, body, has_frontmatter, delimiter_status = split_frontmatter(text)
    frontmatter, yaml_status = parse_frontmatter(frontmatter_text) if has_frontmatter else ({}, "absent")
    markdown = markdown_metrics(body)
    language, probability = detect_language(markdown["readability_text"])
    readability = readability_metrics(markdown["readability_text"], language, probability)
    source = history.get("source", {})
    top_fields = sorted(frontmatter)
    on_field_names = configured_names(frontmatter.get("on"))
    tool_names = configured_names(frontmatter.get("tools"))
    safe_output_names = configured_names(frontmatter.get("safe-outputs"))
    engine = normalized_engine(frontmatter.get("engine"))
    body_bytes = len(body.encode("utf-8"))
    frontmatter_bytes = len(frontmatter_text.encode("utf-8"))
    body_lines = len(body.splitlines())
    frontmatter_lines = len(frontmatter_text.splitlines())
    total_content_bytes = body_bytes + frontmatter_bytes
    total_content_lines = body_lines + frontmatter_lines

    return {
        "source_key": source.get("source_key", ""),
        "source_full_name": source.get("source_full_name", ""),
        "md_path": source.get("md_path", ""),
        "history_relative": history_path.relative_to(source_root).as_posix(),
        "snapshot_relative": latest["snapshot_path"].relative_to(source_root).as_posix(),
        "commit_sha": latest["commit_sha"],
        "committed_at": latest["committed_at"],
        "event_status": latest["event_status"],
        "file_bytes": len(raw_bytes),
        "replacement_character_count": text.count("\ufffd"),
        "has_frontmatter": int(has_frontmatter),
        "frontmatter_delimiter_status": delimiter_status,
        "frontmatter_yaml_status": yaml_status,
        "frontmatter_bytes": frontmatter_bytes,
        "frontmatter_lines": frontmatter_lines,
        "frontmatter_byte_percent": frontmatter_bytes * 100 / total_content_bytes if total_content_bytes else 0,
        "frontmatter_line_percent": frontmatter_lines * 100 / total_content_lines if total_content_lines else 0,
        "top_level_field_count": len(top_fields),
        "recursive_mapping_key_count": recursive_mapping_key_count(frontmatter),
        "top_level_fields": "|".join(top_fields),
        "on_fields": "|".join(sorted(on_field_names)),
        "tools": "|".join(sorted(tool_names)),
        "safe_outputs": "|".join(sorted(safe_output_names)),
        "engine": engine,
        "body_bytes": body_bytes,
        "body_lines": body_lines,
        "language": language,
        "language_probability": probability,
        **{key: value for key, value in markdown.items() if not key.endswith("_text")},
        **readability,
    }


def load_excluded_source_keys(path: Path) -> set[str]:
    if not path or not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def aggregate(records: list[dict[str, Any]], missing_histories: list[str]) -> dict[str, Any]:
    n = len(records)
    top_fields = Counter()
    on_fields = Counter()
    tools = Counter()
    safe_outputs = Counter()
    engines = Counter()
    languages = Counter(record["language"] for record in records)
    for record in records:
        top_fields.update(filter(None, record["top_level_fields"].split("|")))
        on_fields.update(filter(None, record["on_fields"].split("|")))
        tools.update(filter(None, record["tools"].split("|")))
        safe_outputs.update(filter(None, record["safe_outputs"].split("|")))
        if record["engine"]:
            engines[record["engine"]] += 1

    metric_names = [
        "file_bytes", "body_bytes", "body_lines", "body_word_count", "readability_word_count",
        "frontmatter_bytes", "frontmatter_lines", "frontmatter_byte_percent",
        "frontmatter_line_percent", "top_level_field_count", "recursive_mapping_key_count",
        "heading_count", "heading_density_per_1000_words", "h1_count", "h2_count",
        "h3_count", "h4_count", "h5_count", "h6_count", "paragraph_count",
        "list_item_count", "code_block_count", "code_block_lines", "links",
        "inline_code", "template_expression_count", "status_symbol_count",
    ]
    distributions = {name: describe(record[name] for record in records) for name in metric_names}
    readability_records = [record for record in records if record["readability_eligible"]]
    readability_distributions = {
        name: describe(record[name] for record in readability_records)
        for name in [
            "flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog",
            "sentence_count", "readability_syllable_count"
        ]
    }
    flesch_bands = Counter(
        flesch_band(float(record["flesch_reading_ease"])) for record in readability_records
    )
    file_features = {
        "with_frontmatter": sum(record["has_frontmatter"] for record in records),
        "frontmatter_yaml_parse_error": sum(record["frontmatter_yaml_status"] == "parse_error" for record in records),
        "with_no_headings": sum(record["heading_count"] == 0 for record in records),
        "with_h1": sum(record["h1_count"] > 0 for record in records),
        "with_h2": sum(record["h2_count"] > 0 for record in records),
        "with_h3": sum(record["h3_count"] > 0 for record in records),
        "with_h4": sum(record["h4_count"] > 0 for record in records),
        "with_h5": sum(record["h5_count"] > 0 for record in records),
        "with_h6": sum(record["h6_count"] > 0 for record in records),
        "with_heading_skip": sum(record["heading_skip_count"] > 0 for record in records),
        "starting_above_h1": sum(record["starts_above_h1"] for record in records),
        "with_multiple_h1": sum(record["multiple_h1"] for record in records),
        "with_lists": sum(record["list_item_count"] > 0 for record in records),
        "with_code_blocks": sum(record["code_block_count"] > 0 for record in records),
        "with_links": sum(record["links"] > 0 for record in records),
        "with_templates": sum(record["template_expression_count"] > 0 for record in records),
        "with_tables": sum(record["table_count"] > 0 for record in records),
        "with_no_natural_language_words": sum(record["body_word_count"] == 0 for record in records),
        "with_under_100_readability_words": sum(record["readability_word_count"] < 100 for record in records),
        "readability_eligible": len(readability_records),
    }
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "population": {
            "history_files": n + len(missing_histories),
            "latest_usable_snapshots": n,
            "missing_latest_snapshots": len(missing_histories),
            "missing_histories": missing_histories,
        },
        "definitions": {
            "snapshot": "Latest available retrieved snapshot per source history.",
            "body": "Content after the closing YAML frontmatter delimiter.",
            "body_word_count": "Natural-language Markdown text; fenced code, URL targets, image alt text, and inline-code contents excluded.",
            "readability_text": "Body paragraphs and list text; headings, tables, fenced code, URLs, and HTML excluded; inline code and template expressions replaced by neutral one-word placeholders.",
            "readability_eligibility": f"Detected English probability >= {READABILITY_MIN_ENGLISH_PROBABILITY:.2f} and at least {READABILITY_MIN_WORDS} readability words.",
            "top_level_field_count": "Number of top-level YAML mapping keys.",
            "recursive_mapping_key_count": "Number of YAML mapping keys at all nesting levels; list values themselves are not counted as fields.",
            "status_symbol_count": "Count of Unicode Extended Pictographic symbols in the Markdown body, including emoji-like markers and inline icons.",
        },
        "distributions": distributions,
        "readability_distributions": readability_distributions,
        "flesch_bands": prevalence(flesch_bands, len(readability_records)) if readability_records else [],
        "file_features": {
            name: {"count": count, "percent": count * 100 / n}
            for name, count in file_features.items()
        },
        "top_level_fields": prevalence(top_fields, n),
        "on_fields": prevalence(on_fields, n),
        "tools": prevalence(tools, n),
        "safe_outputs": prevalence(safe_outputs, n),
        "engines": prevalence(engines, n),
        "languages": prevalence(languages, n),
    }


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    args = parse_args()
    source_root = args.source_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    excluded_source_keys = load_excluded_source_keys(args.exclude_source_keys.resolve())
    history_paths = sorted(source_root.rglob("history.json"))
    records: list[dict[str, Any]] = []
    missing_histories: list[str] = []
    excluded_histories: list[str] = []
    for history_path in history_paths:
        record = analyze_file(history_path, source_root)
        if record is None:
            missing_histories.append(history_path.relative_to(source_root).as_posix())
        else:
            if record["source_key"] in excluded_source_keys:
                excluded_histories.append(history_path.relative_to(source_root).as_posix())
                continue
            records.append(record)
    records.sort(key=lambda row: row["source_key"].casefold())
    summary = aggregate(records, missing_histories)
    summary["population"]["history_files"] = len(history_paths)
    summary["population"]["history_files_inspected"] = len(history_paths)
    summary["population"]["latest_usable_snapshots_before_rq1_rq2_filter"] = (
        len(records) + len(excluded_histories)
    )
    summary["population"]["excluded_by_rq1_rq2_filter"] = len(excluded_histories)
    summary["population"]["excluded_histories"] = excluded_histories
    summary["definitions"]["rq1_rq2_population_filter"] = (
        "Excludes latest snapshots whose Markdown body has zero natural-language words "
        "or whose body language is clearly non-English."
    )
    write_csv(output_dir / "rq1_per_file_metrics.csv", records)
    with (output_dir / "rq1_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(summary["population"], indent=2))
    print(f"Wrote {len(records)} per-file records to {output_dir}")


if __name__ == "__main__":
    main()
