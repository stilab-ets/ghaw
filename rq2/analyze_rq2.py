#!/usr/bin/env python3
"""Analyze maintenance activity in gh-aw Markdown file histories for RQ2."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


UNAVAILABLE = object()


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


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def split_document(text: str) -> tuple[str, str, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", normalized, "absent"
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            return "".join(lines[1:index]), "".join(lines[index + 1 :]), "ok"
    return "", normalized, "unterminated"


def line_diff_counts(old: str, new: str) -> tuple[int, int]:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    additions = 0
    deletions = 0
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deletions += old_end - old_start
        if tag in {"replace", "insert"}:
            additions += new_end - new_start
    return additions, deletions


def load_snapshot(change: dict[str, Any], history_dir: Path) -> str | None:
    snapshot_file = change.get("snapshot_file")
    if not snapshot_file or change.get("snapshot_error"):
        return None
    snapshot_path = history_dir / Path(snapshot_file)
    if not snapshot_path.is_file():
        return None
    return snapshot_path.read_bytes().decode("utf-8", errors="replace")


def flatten_events(history: dict[str, Any], history_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source = history.get("source", {})
    for commit in history.get("commits", []):
        for change in commit.get("md_changes", []):
            committed_at = change.get("committed_at") or commit.get("committed_at") or ""
            if not committed_at:
                continue
            rows.append(
                {
                    "source_key": source.get("source_key", change.get("source_key", "")),
                    "source_full_name": source.get("source_full_name", change.get("source_full_name", "")),
                    "md_path": source.get("md_path", change.get("md_path", "")),
                    "history_relative": history_path.name,
                    "commit_sha": change.get("commit_sha") or commit.get("commit_sha") or "",
                    "committed_at": committed_at,
                    "event_status": change.get("event_status", ""),
                    "previous_path": change.get("previous_path", ""),
                    "file_additions": int(change.get("file_additions") or 0),
                    "file_deletions": int(change.get("file_deletions") or 0),
                    "file_changes": int(change.get("file_changes") or 0),
                    "actor_type": commit.get("actor_type") or "unknown",
                    "author_login": commit.get("author_login") or "",
                    "author_name": commit.get("author_name") or "",
                    "snapshot_error": change.get("snapshot_error") or "",
                    "snapshot_text": load_snapshot(change, history_path.parent),
                }
            )
    rows.sort(key=lambda row: (parse_datetime(row["committed_at"]), row["commit_sha"]))
    return rows


def classify_transition(
    old_state: object | str | None,
    new_state: object | str | None,
) -> dict[str, Any]:
    empty = {
        "change_location": "unknown",
        "frontmatter_changed": "",
        "body_changed": "",
        "frontmatter_additions": "",
        "frontmatter_deletions": "",
        "body_additions": "",
        "body_deletions": "",
    }
    if old_state is UNAVAILABLE or new_state is UNAVAILABLE:
        return empty
    old_text = "" if old_state is None else str(old_state)
    new_text = "" if new_state is None else str(new_state)
    old_frontmatter, old_body, old_status = split_document(old_text) if old_text else ("", "", "empty")
    new_frontmatter, new_body, new_status = split_document(new_text) if new_text else ("", "", "empty")
    if old_status == "unterminated" or new_status == "unterminated":
        return empty

    # Git churn is line-oriented; ignore final-newline-only differences when
    # deciding which semantic section changed.
    frontmatter_changed = old_frontmatter.splitlines() != new_frontmatter.splitlines()
    body_changed = old_body.splitlines() != new_body.splitlines()
    if frontmatter_changed and body_changed:
        location = "both"
    elif frontmatter_changed:
        location = "frontmatter_only"
    elif body_changed:
        location = "body_only"
    else:
        location = "non_content"
    front_add, front_del = line_diff_counts(old_frontmatter, new_frontmatter)
    body_add, body_del = line_diff_counts(old_body, new_body)
    return {
        "change_location": location,
        "frontmatter_changed": int(frontmatter_changed),
        "body_changed": int(body_changed),
        "frontmatter_additions": front_add,
        "frontmatter_deletions": front_del,
        "body_additions": body_add,
        "body_deletions": body_del,
    }


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


def counter_rows(counter: Counter[str], denominator: int) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count, "percent": count * 100 / denominator if denominator else 0}
        for name, count in counter.most_common()
    ]


def interval_bands(intervals: list[float]) -> list[dict[str, Any]]:
    bands = Counter()
    for days in intervals:
        if days <= 1:
            bands["<=1_day"] += 1
        elif days <= 7:
            bands["1_to_7_days"] += 1
        elif days <= 30:
            bands["7_to_30_days"] += 1
        elif days <= 90:
            bands["30_to_90_days"] += 1
        else:
            bands[">90_days"] += 1
    return counter_rows(bands, len(intervals))


def process_history(
    history_path: Path,
    source_root: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any]]:
    with history_path.open("r", encoding="utf-8") as handle:
        history = json.load(handle)
    events = flatten_events(history, history_path)
    if not events:
        return None, [], history

    source = history.get("source", {})
    collected_at_value = history.get("summary", {}).get("collected_at_utc")
    collected_at = parse_datetime(collected_at_value) if collected_at_value else datetime.now(timezone.utc)
    previous_state: object | str | None = UNAVAILABLE
    previous_time: datetime | None = None
    processed_events: list[dict[str, Any]] = []

    for index, event in enumerate(events):
        current_time = parse_datetime(event["committed_at"])
        snapshot_text = event.pop("snapshot_text")
        status = event["event_status"]
        if status == "removed":
            old_state = previous_state if previous_state is not UNAVAILABLE else (snapshot_text or UNAVAILABLE)
            new_state: object | str | None = None
        else:
            old_state = previous_state
            new_state = snapshot_text if snapshot_text is not None else UNAVAILABLE

        if index == 0:
            transition = {
                "change_location": "initial_observation",
                "frontmatter_changed": "",
                "body_changed": "",
                "frontmatter_additions": "",
                "frontmatter_deletions": "",
                "body_additions": "",
                "body_deletions": "",
            }
        else:
            transition = classify_transition(old_state, new_state)

        interval = (current_time - previous_time).total_seconds() / 86400 if previous_time else ""
        processed_events.append(
            {
                **event,
                "history_relative": history_path.relative_to(source_root).as_posix(),
                "event_index": index + 1,
                "is_subsequent_change": int(index > 0),
                "interval_since_previous_days": interval,
                **transition,
            }
        )
        previous_time = current_time
        if status == "removed":
            previous_state = None
        elif snapshot_text is not None:
            previous_state = snapshot_text
        else:
            previous_state = UNAVAILABLE

    times = [parse_datetime(event["committed_at"]) for event in processed_events]
    intervals = [
        float(event["interval_since_previous_days"])
        for event in processed_events
        if event["interval_since_previous_days"] != ""
    ]
    subsequent = processed_events[1:]
    region_counts = Counter(event["change_location"] for event in subsequent)
    actor_counts = Counter(event["actor_type"] for event in processed_events)
    subsequent_actor_counts = Counter(event["actor_type"] for event in subsequent)
    first_time = times[0]
    last_time = times[-1]
    file_record = {
        "source_key": source.get("source_key", processed_events[0]["source_key"]),
        "source_full_name": source.get("source_full_name", processed_events[0]["source_full_name"]),
        "md_path": source.get("md_path", processed_events[0]["md_path"]),
        "history_relative": history_path.relative_to(source_root).as_posix(),
        "event_count": len(processed_events),
        "subsequent_change_count": len(subsequent),
        "is_write_once": int(len(processed_events) == 1),
        "first_observed_at": first_time.isoformat(),
        "last_observed_at": last_time.isoformat(),
        "collected_at": collected_at.isoformat(),
        "observed_age_days": max(0.0, (collected_at - first_time).total_seconds() / 86400),
        "change_span_days": max(0.0, (last_time - first_time).total_seconds() / 86400),
        "days_since_last_change": max(0.0, (collected_at - last_time).total_seconds() / 86400),
        "median_intercommit_days": statistics.median(intervals) if intervals else "",
        "first_followup_days": intervals[0] if intervals else "",
        "active_day_count": len({time.date() for time in times}),
        "active_month_count": len({(time.year, time.month) for time in times}),
        "total_additions": sum(event["file_additions"] for event in processed_events),
        "total_deletions": sum(event["file_deletions"] for event in processed_events),
        "total_churn": sum(event["file_changes"] for event in processed_events),
        "subsequent_additions": sum(event["file_additions"] for event in subsequent),
        "subsequent_deletions": sum(event["file_deletions"] for event in subsequent),
        "subsequent_churn": sum(event["file_changes"] for event in subsequent),
        "frontmatter_only_changes": region_counts["frontmatter_only"],
        "body_only_changes": region_counts["body_only"],
        "both_changes": region_counts["both"],
        "non_content_changes": region_counts["non_content"],
        "unknown_location_changes": region_counts["unknown"],
        "human_event_count": actor_counts["human"],
        "agent_event_count": actor_counts["agent"],
        "unknown_actor_event_count": actor_counts["unknown"],
        "subsequent_human_event_count": subsequent_actor_counts["human"],
        "subsequent_agent_event_count": subsequent_actor_counts["agent"],
    }
    return file_record, processed_events, history


def load_excluded_source_keys(path: Path) -> set[str]:
    if not path or not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def commit_count_bins(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter()
    for record in files:
        count = record["event_count"]
        if count == 1:
            counter["1"] += 1
        elif count <= 5:
            counter["2_to_5"] += 1
        elif count <= 10:
            counter["6_to_10"] += 1
        elif count <= 25:
            counter["11_to_25"] += 1
        elif count <= 50:
            counter["26_to_50"] += 1
        else:
            counter[">50"] += 1
    order = ["1", "2_to_5", "6_to_10", "11_to_25", "26_to_50", ">50"]
    return [
        {"name": name, "count": counter[name], "percent": counter[name] * 100 / len(files)}
        for name in order
    ]


def exposure_sensitivity(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for threshold in (30, 90, 180):
        eligible = [record for record in files if record["observed_age_days"] >= threshold]
        maintained = sum(record["event_count"] > 1 for record in eligible)
        result.append(
            {
                "minimum_observed_age_days": threshold,
                "eligible_files": len(eligible),
                "maintained_files": maintained,
                "maintained_percent": maintained * 100 / len(eligible) if eligible else 0,
                "write_once_files": len(eligible) - maintained,
                "write_once_percent": (len(eligible) - maintained) * 100 / len(eligible) if eligible else 0,
            }
        )
    return result


def concentration(files: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    total = sum(record[field] for record in files)
    ordered = sorted(files, key=lambda record: record[field], reverse=True)
    result = []
    for share in (0.01, 0.05, 0.10):
        count = max(1, math.ceil(len(files) * share))
        subtotal = sum(record[field] for record in ordered[:count])
        result.append(
            {
                "top_file_percent": int(share * 100),
                "file_count": count,
                "event_count": subtotal,
                "event_percent": subtotal * 100 / total if total else 0,
            }
        )
    return result


def aggregate(
    files: list[dict[str, Any]],
    events: list[dict[str, Any]],
    history_count: int,
    zero_event_histories: list[str],
) -> dict[str, Any]:
    subsequent = [event for event in events if event["is_subsequent_change"]]
    maintained_files = [record for record in files if record["event_count"] > 1]
    intervals = [float(event["interval_since_previous_days"]) for event in subsequent]
    first_followups = [float(record["first_followup_days"]) for record in maintained_files]
    region_counter = Counter(event["change_location"] for event in subsequent)
    content_region_count = sum(region_counter[name] for name in ("frontmatter_only", "body_only", "both"))
    regional_lines = Counter()
    for event in subsequent:
        for name in (
            "frontmatter_additions", "frontmatter_deletions", "body_additions", "body_deletions"
        ):
            if event[name] != "":
                regional_lines[name] += int(event[name])
    regional_lines["frontmatter_churn"] = (
        regional_lines["frontmatter_additions"] + regional_lines["frontmatter_deletions"]
    )
    regional_lines["body_churn"] = regional_lines["body_additions"] + regional_lines["body_deletions"]
    classified_regional_churn = regional_lines["frontmatter_churn"] + regional_lines["body_churn"]

    line_metrics = {}
    for prefix, rows in (("all", events), ("subsequent", subsequent)):
        for name in ("file_additions", "file_deletions", "file_changes"):
            line_metrics[f"{prefix}_{name}"] = describe(event[name] for event in rows)

    location_rows = []
    for name in ("frontmatter_only", "body_only", "both", "non_content", "unknown"):
        count = region_counter[name]
        location_rows.append(
            {
                "name": name,
                "count": count,
                "percent_all_subsequent": count * 100 / len(subsequent),
                "percent_content_changes": count * 100 / content_region_count
                if name in {"frontmatter_only", "body_only", "both"} and content_region_count
                else "",
            }
        )

    file_region_features = {
        "ever_frontmatter_changed": sum(
            record["frontmatter_only_changes"] + record["both_changes"] > 0
            for record in maintained_files
        ),
        "ever_body_changed": sum(
            record["body_only_changes"] + record["both_changes"] > 0
            for record in maintained_files
        ),
        "ever_both_in_same_commit": sum(record["both_changes"] > 0 for record in maintained_files),
        "active_in_at_least_3_months": sum(record["active_month_count"] >= 3 for record in files),
        "changed_within_30_days_of_collection": sum(record["days_since_last_change"] <= 30 for record in files),
        "changed_within_90_days_of_collection": sum(record["days_since_last_change"] <= 90 for record in files),
    }

    actor_counter = Counter(event["actor_type"] for event in subsequent)
    status_counter = Counter(event["event_status"] for event in subsequent)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "population": {
            "history_files_inspected": history_count,
            "histories_with_events": len(files),
            "zero_event_histories": len(zero_event_histories),
            "zero_event_history_paths": zero_event_histories,
            "all_path_restricted_events": len(events),
            "subsequent_change_events": len(subsequent),
            "snapshot_errors": sum(bool(event["snapshot_error"]) for event in events),
        },
        "definitions": {
            "write_once": "Exactly one observed commit touching the Markdown path.",
            "subsequent_change": "Every observed path-restricted event after a file's first observed event.",
            "observed_age": "Days from first observed event to per-history collection time; used to expose right-censoring.",
            "intercommit_interval": "Elapsed days between consecutive commits touching the same Markdown source path.",
            "change_location": "Literal frontmatter/body section whose content differs between consecutive retrieved snapshots.",
            "regional_churn": "Line additions and deletions from section-level sequence diffs; GitHub file-level churn remains authoritative for total lines.",
        },
        "file_distributions": {
            "event_count": describe(record["event_count"] for record in files),
            "subsequent_change_count": describe(record["subsequent_change_count"] for record in files),
            "observed_age_days": describe(record["observed_age_days"] for record in files),
            "change_span_days": describe(record["change_span_days"] for record in files),
            "days_since_last_change": describe(record["days_since_last_change"] for record in files),
            "median_intercommit_days": describe(record["median_intercommit_days"] for record in maintained_files),
            "active_day_count": describe(record["active_day_count"] for record in files),
            "active_month_count": describe(record["active_month_count"] for record in files),
            "subsequent_additions": describe(record["subsequent_additions"] for record in files),
            "subsequent_deletions": describe(record["subsequent_deletions"] for record in files),
            "subsequent_churn": describe(record["subsequent_churn"] for record in files),
        },
        "event_line_distributions": line_metrics,
        "event_count_bins": commit_count_bins(files),
        "exposure_sensitivity": exposure_sensitivity(files),
        "pooled_intercommit_days": describe(intervals),
        "pooled_intercommit_bands": interval_bands(intervals),
        "first_followup_days": describe(first_followups),
        "first_followup_bands": interval_bands(first_followups),
        "change_locations": location_rows,
        "regional_lines": {
            **dict(regional_lines),
            "frontmatter_churn_percent": regional_lines["frontmatter_churn"] * 100 / classified_regional_churn
            if classified_regional_churn else 0,
            "body_churn_percent": regional_lines["body_churn"] * 100 / classified_regional_churn
            if classified_regional_churn else 0,
        },
        "file_region_features": {
            name: {
                "count": count,
                "percent_all_files": count * 100 / len(files),
                "percent_maintained_files": count * 100 / len(maintained_files)
                if name.startswith("ever_") else "",
            }
            for name, count in file_region_features.items()
        },
        "subsequent_actor_types": counter_rows(actor_counter, len(subsequent)),
        "subsequent_event_statuses": counter_rows(status_counter, len(subsequent)),
        "all_event_totals": {
            "additions": sum(event["file_additions"] for event in events),
            "deletions": sum(event["file_deletions"] for event in events),
            "churn": sum(event["file_changes"] for event in events),
        },
        "subsequent_event_totals": {
            "additions": sum(event["file_additions"] for event in subsequent),
            "deletions": sum(event["file_deletions"] for event in subsequent),
            "churn": sum(event["file_changes"] for event in subsequent),
        },
        "event_concentration": concentration(files, "event_count"),
        "subsequent_event_concentration": concentration(files, "subsequent_change_count"),
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
    file_records: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    zero_event_histories: list[str] = []
    excluded_histories: list[str] = []
    for history_path in history_paths:
        file_record, events, _ = process_history(history_path, source_root)
        if file_record is None:
            zero_event_histories.append(history_path.relative_to(source_root).as_posix())
            continue
        if file_record["source_key"] in excluded_source_keys:
            excluded_histories.append(history_path.relative_to(source_root).as_posix())
            continue
        file_records.append(file_record)
        event_records.extend(events)
    file_records.sort(key=lambda row: row["source_key"].casefold())
    event_records.sort(
        key=lambda row: (row["source_key"].casefold(), row["event_index"])
    )
    summary = aggregate(file_records, event_records, len(history_paths), zero_event_histories)
    summary["population"]["excluded_by_rq1_rq2_filter"] = len(excluded_histories)
    summary["population"]["excluded_history_paths"] = excluded_histories
    summary["definitions"]["rq1_rq2_population_filter"] = (
        "Excludes latest snapshots whose Markdown body has zero natural-language words "
        "or whose body language is clearly non-English."
    )
    write_csv(output_dir / "rq2_per_file_metrics.csv", file_records)
    write_csv(output_dir / "rq2_per_event_metrics.csv", event_records)
    dates = [row["committed_at"] for row in event_records]
    corpus = {
        "markdown_files": len(file_records),
        "source_repositories": len({row["source_full_name"] for row in file_records}),
        "distinct_markdown_commits": len({row["commit_sha"] for row in event_records}),
        "markdown_file_changes": len(event_records),
        "first_commit_date": min(dates)[:10],
        "last_commit_date": max(dates)[:10],
    }
    (output_dir / "corpus_summary.json").write_text(json.dumps(corpus, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "rq2_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(summary["population"], indent=2))
    print(f"Wrote {len(file_records)} file rows and {len(event_records)} event rows to {output_dir}")


if __name__ == "__main__":
    main()
