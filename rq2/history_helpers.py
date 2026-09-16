"""Snapshot sizes and Holm correction used by the monthly analysis."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

def count_lines(path: Path) -> int | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(text.splitlines())


def load_snapshot_line_counts(history_root: Path, retained_keys: set[str]) -> pd.DataFrame:
    rows = []
    for history_path in history_root.glob("*/history.json"):
        history = json.loads(history_path.read_text(encoding="utf-8"))
        for commit in history.get("commits", []):
            for change in commit.get("md_changes", []):
                source_key = change.get("source_key", "")
                if source_key not in retained_keys:
                    continue
                line_count = None
                if change.get("event_status") == "removed":
                    line_count = 0
                elif change.get("snapshot_file"):
                    line_count = count_lines(history_path.parent / change["snapshot_file"])
                rows.append(
                    {
                        "source_key": source_key,
                        "commit_sha": change.get("commit_sha", ""),
                        "snapshot_line_count": line_count,
                    }
                )
    return pd.DataFrame(rows).drop_duplicates(["source_key", "commit_sha"], keep="last")


def holm_adjust(p_values: list[float]) -> list[float]:
    adjusted = [np.nan] * len(p_values)
    valid = [(index, p_value) for index, p_value in enumerate(p_values) if not np.isnan(p_value)]
    m = len(valid)
    running_max = 0.0
    for rank, (index, p_value) in enumerate(sorted(valid, key=lambda item: item[1]), start=1):
        value = min(1.0, (m - rank + 1) * p_value)
        running_max = max(running_max, value)
        adjusted[index] = running_max
    return adjusted
