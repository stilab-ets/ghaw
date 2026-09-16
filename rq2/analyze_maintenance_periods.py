#!/usr/bin/env python3
"""Describe maintenance in four non-overlapping periods of the fixed RQ2 cohort."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest

from history_helpers import holm_adjust, load_snapshot_line_counts
from change_locations import plot_event_violins, summarize_events


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "output"
OUT = DATA / "maintenance_periods_120d"
FIGURES = ROOT.parent / "figures"
PERIOD_DAYS = 28
PERIODS = 4
METRICS = ("maintenance_commits", "relative_churn", "end_size")


def size_profile(times: np.ndarray, sizes: np.ndarray, left: float, right: float) -> tuple[float, float, float]:
    """Integrate a stepwise snapshot history, with zero size before creation."""
    boundaries = np.unique(np.r_[left, times[(times > left) & (times < right)], right])
    indices = np.searchsorted(times, boundaries[:-1], side="right") - 1
    values = np.where(indices >= 0, sizes[np.maximum(indices, 0)], 0)
    mean = float(np.dot(np.diff(boundaries), values) / (right - left))

    def at(day: float) -> float:
        index = np.searchsorted(times, day, side="right") - 1
        return float(sizes[index]) if index >= 0 else 0.0

    return at(left), at(right), mean


def aggregate_periods(events: pd.DataFrame, starts: pd.Series, key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = events.loc[events[key].isin(starts.index)].copy()
    frame["day"] = (frame.committed_at - frame[key].map(starts)).dt.total_seconds() / 86400
    frame = frame.loc[frame.day.between(0, PERIODS * PERIOD_DAYS)].copy()
    if frame.snapshot_line_count.isna().any():
        raise ValueError("Missing snapshot size in the analysis window")
    frame["period"] = np.ceil(frame.day / PERIOD_DAYS).clip(1, PERIODS).astype(int)
    maintenance = frame.loc[frame.is_subsequent_change.eq(1)]
    rows = []
    for entity in starts.index:
        group = frame.loc[frame[key].eq(entity)]
        paths = []
        for _, path in group.groupby("source_key"):
            path = path.sort_values(["day", "commit_sha"]).drop_duplicates("day", keep="last")
            paths.append((path.day.to_numpy(), path.snapshot_line_count.to_numpy()))
        for period in range(1, PERIODS + 1):
            left, right = (period - 1) * PERIOD_DAYS, period * PERIOD_DAYS
            sizes = np.sum([size_profile(t, s, left, right) for t, s in paths], axis=0)
            changes = maintenance.loc[maintenance[key].eq(entity) & maintenance.period.eq(period)]
            churn = int(changes.file_changes.sum())
            if sizes[2] == 0 and churn:
                raise ValueError(f"Undefined relative churn for {entity}, period {period}")
            rows.append({
                key: entity, "period": period,
                "maintenance_commits": changes.commit_sha.nunique(),
                "commit_file_events": len(changes), "churn": churn,
                "start_size": sizes[0], "end_size": sizes[1], "mean_size": sizes[2],
                "relative_churn": 100 * churn / sizes[2] if sizes[2] else np.nan,
                "net_growth": sizes[1] - sizes[0],
                "expanding_events": int(changes.file_additions.gt(changes.file_deletions).sum()),
                "shrinking_events": int(changes.file_additions.lt(changes.file_deletions).sum()),
                "balanced_content_events": int((changes.file_additions.eq(changes.file_deletions) & changes.file_changes.gt(0)).sum()),
                "non_content_events": int(changes.file_changes.eq(0).sum()),
            })
    result = pd.DataFrame(rows)
    assert len(result) == len(starts) * PERIODS
    assert not result.duplicated([key, "period"]).any()
    assert result.churn.sum() == maintenance.file_changes.sum()
    assert result.commit_file_events.sum() == len(maintenance)
    assert result["maintenance_commits"].sum() == len(maintenance.drop_duplicates([key, "commit_sha"]))
    return result, frame


def endpoint_tests(projects: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in METRICS:
        paired = projects.pivot(index="source_full_name", columns="period", values=metric)[[1, 4]].dropna()
        differences = paired[4] - paired[1]
        positive = int(differences.gt(1e-10).sum())
        negative = int(differences.lt(-1e-10).sum())
        nonzero = positive + negative
        p = float(binomtest(positive, nonzero, .5, alternative="two-sided").pvalue) if nonzero else 1.0
        rows.append({
            "metric": metric, "projects": len(paired), "higher": positive,
            "lower": negative, "ties": len(paired) - nonzero,
            "median_first": float(paired[1].median()), "median_last": float(paired[4].median()),
            "median_paired_difference": float(differences.median()), "p_value": p,
        })
    result = pd.DataFrame(rows)
    result["holm_p_value"] = holm_adjust(result.p_value.to_list())
    return result


def activity_baseline(projects: pd.DataFrame, origins: pd.Series, events: pd.DataFrame) -> pd.DataFrame:
    """Compare Markdown maintenance with all commits in the identical project window."""
    rows = []
    for repo, origin in origins.items():
        path = ROOT.parent / "data/project_activity" / (repo.replace("/", "__") + ".json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload["complete"] or pd.Timestamp(payload["origin"]) != origin:
            raise ValueError(f"Incomplete or misaligned repository baseline: {repo}")
        commits = pd.DataFrame(payload["commits"])
        if commits.sha.duplicated().any():
            raise ValueError(f"Duplicate repository commits: {repo}")
        days = (pd.to_datetime(commits.committed_at, utc=True) - origin).dt.total_seconds() / 86400
        if not days.between(0, PERIODS * PERIOD_DAYS).all():
            raise ValueError(f"Repository commits outside the analysis window: {repo}")
        periods = np.ceil(days / PERIOD_DAYS).clip(1, PERIODS).astype(int)
        expected = events.loc[events.source_full_name.eq(repo)].copy()
        event_days = (expected.committed_at - origin).dt.total_seconds() / 86400
        expected = expected.loc[event_days.between(0, PERIODS * PERIOD_DAYS)]
        dates = pd.to_datetime(commits.set_index("sha").committed_at, utc=True)
        if not set(expected.commit_sha).issubset(set(dates.index)):
            raise ValueError(f"Markdown commits absent from the repository baseline: {repo}")
        if not expected.commit_sha.map(dates).eq(expected.committed_at).all():
            raise ValueError(f"Commit-date disagreement: {repo}")
        for period in range(1, PERIODS + 1):
            rows.append(dict(source_full_name=repo, period=period, repository_commits=int(periods.eq(period).sum())))
    result = projects.merge(pd.DataFrame(rows), on=["source_full_name", "period"], validate="one_to_one")
    assert result.maintenance_commits.le(result.repository_commits).all()
    result["maintenance_commit_share"] = 100 * result.maintenance_commits / result.repository_commits.replace(0, np.nan)
    return result


def adjacent_tests(projects: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for metric in (*METRICS, "maintenance_commit_share"):
        wide = projects.pivot(index="source_full_name", columns="period", values=metric)
        for period in (2, 3, 4):
            pair = wide[[period - 1, period]].dropna()
            differences = pair[period] - pair[period - 1]
            higher = int(differences.gt(1e-10).sum())
            lower = int(differences.lt(-1e-10).sum())
            nonzero = higher + lower
            rows.append(dict(metric=metric, previous_period=period - 1, period=period,
                             projects=len(pair), higher=higher, lower=lower, ties=len(pair) - nonzero,
                             median_paired_difference=float(differences.median()),
                             p_value=float(binomtest(higher, nonzero, .5).pvalue) if nonzero else 1.0))
    result = pd.DataFrame(rows)
    result["holm_p_value"] = holm_adjust(result.p_value.tolist())
    return result


def fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def plot_periods(frame: pd.DataFrame, level: str, tests: pd.DataFrame | None = None) -> None:
    titles = ("(a) Maintenance commits", "(b) Size-normalized churn", "(c) Markdown size")
    labels = ("Commits per month", "Changed lines per 100 lines", "Lines at month end")
    colors = ("#9573BA", "#5395AE", "#D29A48")
    metrics = METRICS
    project_level = level == "project"
    if project_level:
        metrics = ("maintenance_commits", "maintenance_commit_share", "relative_churn", "end_size")
        titles = ("(a) Maintenance\ncommits",
                  "(b) gh-aw share of\nproject commits",
                  "(c) Size-normalized\nchurn", "(d) Markdown\nsize")
        labels = (labels[0], "Repository commits (%)", labels[1], labels[2])
        colors = (colors[0], "#548F72", colors[1], colors[2])
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9, "pdf.fonttype": 42}):
        fig, axes = plt.subplots(1, len(metrics), figsize=(7.25, 2.85))
        fig.suptitle("Project level" if project_level else "File level",
                     fontsize=10.5, fontweight="medium", y=.985)
        fig.subplots_adjust(left=.07 if project_level else .085, right=.995,
                            top=(.72 if project_level else .79) * 2.55 / 2.85,
                            bottom=.22 * 2.55 / 2.85,
                            wspace=.70 if project_level else .52)
        for ax, metric, title, label, color in zip(axes, metrics, titles, labels, colors):
            values = [frame.loc[frame.period.eq(p), metric].dropna().to_numpy() for p in range(1, 5)]
            bp = ax.boxplot(values, widths=.42, showfliers=False, patch_artist=True,
                            boxprops={"edgecolor": color, "linewidth": 1.1},
                            whiskerprops={"color": color, "linewidth": 1},
                            capprops={"color": color, "linewidth": 1},
                            medianprops={"color": "#222222", "linewidth": 1.35})
            for box in bp["boxes"]:
                box.set_facecolor(color)
                box.set_alpha(.42)
            ymax = max(float(max(line.get_ydata())) for line in bp["whiskers"])
            scale = max(1.0, ymax)
            for x, values_p in enumerate(values, 1):
                ax.text(x, np.quantile(values_p, .75) + .04 * scale, fmt(float(np.median(values_p))),
                        ha="center", va="bottom", fontsize=7 if project_level else 7.5,
                        bbox={"facecolor": "white", "edgecolor": "none", "pad": .45})
            ax.set_ylim(-.02 * scale, 1.19 * scale)
            ax.set_xticks(range(1, 5), ["1", "2", "3", "4"])
            ax.set_xlabel("Month", labelpad=4)
            ax.set_ylabel(label, fontsize=7.5 if project_level else 8)
            ax.set_title(title, fontsize=8 if project_level else 9, pad=23 if project_level else 21)
            if tests is not None:
                for period in (2, 3, 4):
                    p = float(tests.loc[tests.metric.eq(metric) & tests.period.eq(period), "holm_p_value"].iloc[0])
                    label_p = "p<.001" if p < .001 else f"p={p:.2f}"
                    if project_level:
                        label_p = "<.001" if p < .001 else f"{p:.2f}".removeprefix("0")
                    ax.text(period, 1.04, label_p, transform=ax.get_xaxis_transform(),
                            ha="center", fontsize=6.3, color="#454545")
                    if p < .05:
                        bp["boxes"][period - 1].set_linestyle(":")
                        for component in ("whiskers", "caps"):
                            for line in bp[component][2 * (period - 1):2 * period]:
                                line.set_linestyle(":")
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines[["left", "bottom"]].set_color("#ABB2B7")
            ax.grid(axis="y", color="#E5E7EB", linewidth=.65)
            ax.set_axisbelow(True)
            ax.tick_params(axis="both", labelsize=8, length=3, color="#ABB2B7")
        for suffix in ("pdf", "png"):
            fig.savefig(FIGURES / f"rq2_{level}_maintenance_periods.{suffix}", dpi=220)
        plt.close(fig)


def describe(frame: pd.DataFrame, key: str) -> dict:
    periods = {}
    for period, group in frame.groupby("period"):
        periods[int(period)] = {
            "entities": len(group),
            "active_entities": int(group.maintenance_commits.gt(0).sum()),
            "active_percent": float(100 * group.maintenance_commits.gt(0).mean()),
            "medians": {m: float(group[m].median()) for m in (*METRICS, "churn", "net_growth")},
        }
    counts = frame.groupby(key).maintenance_commits.agg(lambda x: int(x.gt(0).sum()))
    return {"periods": periods, "active_period_counts": {int(k): int(v) for k, v in counts.value_counts().sort_index().items()}}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    files = pd.read_csv(DATA / "rq2_per_file_metrics.csv")
    events = pd.read_csv(DATA / "rq2_per_event_metrics.csv")
    retained = pd.read_csv(ROOT.parent / "data/rq1_rq2_population/retained_rq1_rq2_files.csv")
    assert set(files.source_key) == set(retained.source_key)
    assert not events.duplicated(["source_key", "commit_sha"]).any()
    files["first_observed_at"] = pd.to_datetime(files.first_observed_at, utc=True)
    events["committed_at"] = pd.to_datetime(events.committed_at, utc=True)
    selected = files.loc[files.change_span_days.ge(120)].copy()
    repositories = files.loc[files.source_full_name.isin(selected.source_full_name)].copy()
    assert len(selected) == 348 and selected.source_full_name.nunique() == 43
    sizes = load_snapshot_line_counts(ROOT.parent / "data/h", set(repositories.source_key))
    events = events.loc[events.source_key.isin(repositories.source_key)].merge(sizes, on=["source_key", "commit_sha"], validate="one_to_one")
    # A rename away from the tracked path leaves that path absent, not unchanged.
    renamed_away = events.event_status.eq("renamed") & events.previous_path.eq(events.md_path)
    events.loc[renamed_away, "snapshot_line_count"] = 0
    starts = {
        "file": selected.set_index("source_key").first_observed_at,
        "project": repositories.groupby("source_full_name").first_observed_at.min(),
    }
    observed = events.groupby("source_key").committed_at.min()
    assert starts["file"].eq(observed.reindex(starts["file"].index)).all()
    first_events = events.sort_values(["committed_at", "commit_sha"]).drop_duplicates("source_key")
    assert first_events.event_status.isin(["added", "renamed"]).all()
    frames = {}
    summary = {
        "selection": "Unchanged cohort: >=120 days between first and last observed changes.",
        "selected_files": len(selected), "projects": len(starts["project"]),
        "repository_files": len(repositories), "period_days": PERIOD_DAYS,
        "period_boundaries": "[0,28], (28,56], (56,84], (84,112] days from origin; initial file events excluded from maintenance.",
        "relative_churn": "100 * period additions plus deletions / time-weighted mean snapshot line count during that same period. May exceed 100 because lines may change repeatedly.",
        "size": "Physical lines including frontmatter, body and code. Zero before first observation and after removal. Snapshots carried forward between changes.",
        "inference": "Exploratory project-paired exact two-sided sign tests of each period versus its predecessor, ties omitted, Holm across all 12 tests (commits, relative churn, size, maintenance share). Files shown descriptively.",
        "scope_limit": "Describes selected maintained paths, not write-once prevalence. Repository commit share contextualizes activity but is not a causal control or a per-file-type maintenance comparison.",
        "rename_handling": "A renamed event whose previous_path equals the tracked md_path sets that path's size to zero until it reappears. This corrects the old carry-forward treatment of outgoing renames.",
        "input_sha256": {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in ("rq2_per_file_metrics.csv", "rq2_per_event_metrics.csv")},
    }
    for level, key in (("file", "source_key"), ("project", "source_full_name")):
        frame, window = aggregate_periods(events, starts[level], key)
        frame.to_csv(OUT / f"{level}_period_metrics.csv", index=False)
        frames[level] = frame
        summary[level] = describe(frame, key)
        if level == "project":
            location_events, locations = summarize_events(window)
            location_events.to_csv(OUT / "project_file_event_locations.csv", index=False)
            locations.to_csv(OUT / "project_change_locations.csv", index=False)
            plot_event_violins(locations, FIGURES / "rq2_period_project_change_locations")
            changes = window.loc[window.is_subsequent_change.eq(1)]
            front = changes[["frontmatter_additions", "frontmatter_deletions"]].sum().sum()
            body = changes[["body_additions", "body_deletions"]].sum().sum()
            content = changes.loc[changes.file_changes.gt(0)]
            summary["edit_nature"] = {
                "location_unit": "Unique (source_key, commit_sha) maintenance events, not repository-deduplicated commits.",
                "location_denominator": "All subsequent commit-file events within the project window, including non-content and unknown events. Both-region events enter both numerators.",
                "zero_event_convention": "Projects without maintenance events are assigned 0% for each region and retained in medians and violins.",
                "projects_in_location_plot": len(locations),
                "projects_with_maintenance_events": int(locations.maintenance_events.gt(0).sum()),
                "maintenance_events": int(locations.maintenance_events.sum()),
                "unknown_location_events": int(locations.unknown_events.sum()),
                "non_content_location_events": int(locations.non_content_events.sum()),
                "median_frontmatter_percent": float(locations.frontmatter_percent.median()),
                "median_body_percent": float(locations.body_percent.median()),
                "body_share_of_region_churn": float(100 * body / (front + body)),
                "content_events": len(content),
                "expanding_percent": float(100 * content.file_additions.gt(content.file_deletions).mean()),
                "shrinking_percent": float(100 * content.file_additions.lt(content.file_deletions).mean()),
                "equal_line_count_percent": float(100 * content.file_additions.eq(content.file_deletions).mean()),
            }
    baseline = activity_baseline(frames["project"], starts["project"], events)
    baseline.to_csv(OUT / "project_activity_adjusted_metrics.csv", index=False)
    tests = adjacent_tests(baseline)
    tests.to_csv(OUT / "project_adjacent_month_tests.csv", index=False)
    summary["project_adjacent_month_tests"] = tests.to_dict(orient="records")
    summary["project_activity"] = [dict(period=int(period), projects=len(group),
                                        projects_with_commits=int(group.repository_commits.gt(0).sum()),
                                        median_repository_commits=float(group.repository_commits.median()),
                                        median_maintenance_share=float(group.maintenance_commit_share.median()))
                                   for period, group in baseline.groupby("period")]
    summary["baseline_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in sorted((ROOT.parent / "data/project_activity").glob("*.json"))
                                  if path.name != "collection_audit.json"}
    for level, origins in starts.items():
        origins.rename("origin").to_csv(OUT / f"{level}_origins.csv")
    plot_periods(frames["file"], "file")
    plot_periods(baseline, "project", tests)
    selected.to_csv(OUT / "selected_files.csv", index=False)
    repositories.to_csv(OUT / "repository_files.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
