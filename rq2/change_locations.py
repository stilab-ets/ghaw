"""Per-project maintenance targets and their violin plot."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
LOCATIONS = {"frontmatter_only", "body_only", "both", "non_content", "unknown"}

def summarize_events(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep each (Markdown path, SHA) as an event, including zero-event projects."""
    if events.duplicated(["source_key", "commit_sha"]).any():
        raise ValueError("Duplicate commit-file events")
    if events[["source_full_name", "source_key", "commit_sha"]].isna().any().any():
        raise ValueError("Missing event identifiers")
    changes = events.loc[events.is_subsequent_change.eq(1)].copy()
    if not set(changes.change_location).issubset(LOCATIONS):
        raise ValueError("Unexpected maintenance change location")
    changes["frontmatter"] = changes.change_location.isin(["frontmatter_only", "both"])
    changes["body"] = changes.change_location.isin(["body_only", "both"])
    rows = []
    for project in sorted(events.source_full_name.unique()):
        group = changes.loc[changes.source_full_name.eq(project)]
        n = len(group)
        front, body = int(group.frontmatter.sum()), int(group.body.sum())
        both = int((group.frontmatter & group.body).sum())
        non_content = int(group.change_location.eq("non_content").sum())
        unknown = int(group.change_location.eq("unknown").sum())
        assert front + body - both + non_content + unknown == n
        rows.append(dict(source_full_name=project, maintenance_events=n,
                         frontmatter_events=front, body_events=body, both_regions_events=both,
                         non_content_events=non_content, unknown_events=unknown,
                         zero_event_convention=n == 0,
                         frontmatter_percent=100 * front / n if n else 0.0,
                         body_percent=100 * body / n if n else 0.0))
    return changes, pd.DataFrame(rows)


def plot_event_violins(projects: pd.DataFrame, destination: Path) -> None:
    values = [projects.frontmatter_percent.to_numpy(), projects.body_percent.to_numpy()]
    colors = ["#5395AE", "#D29A48"]
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "pdf.fonttype": 42, "ps.fonttype": 42}):
        fig, ax = plt.subplots(figsize=(3.8, 2.8), layout="constrained")
        for x, y, color in zip([1, 2], values, colors):
            if np.ptp(y) > 0:
                violin = ax.violinplot([y], positions=[x], widths=.72, points=200,
                                      bw_method=.3, showextrema=False)
                shape = violin["bodies"][0]
                shape.set_facecolor(color)
                shape.set_edgecolor(color)
                shape.set_alpha(.65)
                shape.set_linewidth(1)
            q1, median, q3 = np.quantile(y, [.25, .5, .75])
            ax.vlines(x, q1, q3, color="#34414A", linewidth=2.5, zorder=3)
            ax.hlines(median, x - .09, x + .09, color="white", linewidth=2.2, zorder=4)
            ax.annotate(f"{median:.1f}%", xy=(x, median), xytext=(0, 5),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=9, color="#263238", zorder=5,
                        bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.1})
        ax.set_xticks([1, 2], ["Frontmatter", "Markdown body"])
        ax.set_yticks(np.arange(0, 101, 20))
        ax.set_ylim(-3, 113)
        ax.set_xlim(.4, 2.6)
        ax.set_ylabel("Maintenance file events\nper project (%)")
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#E4E7EA", linewidth=.65)
        ax.spines[["top", "right"]].set_visible(False)
        for side in ["bottom", "left"]:
            ax.spines[side].set_color("#A3ACB2")
        ax.tick_params(length=3, color="#A3ACB2")
        for suffix in [".pdf", ".png"]:
            fig.savefig(destination.with_suffix(suffix), dpi=240)
        plt.close(fig)
