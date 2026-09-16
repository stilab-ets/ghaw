---
name: "Traffic Updater"
description: "Weekly collection of repo traffic data (views and unique visitors). Appends the previous week's daily numbers to CSV files."
on:
  schedule: weekly on monday
  workflow_dispatch:
tools:
  bash: ["gh", "date"]
  edit:
  github:
    toolsets: [repos]
# NOTE: After running `gh aw compile`, manually add the following env var
# to the agent step in the lock file (the step that runs `copilot`):
#   GH_TOKEN: ${{ secrets.GH_AW_GITHUB_TOKEN }}
# This is required because engine.env is not yet supported by the compiler.
safe-outputs:
  allowed-domains:
    - github.com
  create-pull-request:
    labels: [automated-update, traffic-data]
    title-prefix: "[bot] "
    base-branch: main
---

# Collect Weekly Repo Traffic

You are a traffic collection bot for the **copilot-cli-for-beginners** repository. Your job is to fetch the previous week's traffic numbers from the GitHub API and append them to two CSV files.

## Definitions

- **Unique visitors** go in `.github/uvs.csv`
- **Total views** go in `.github/views.csv`
- Both files use the format `"MM/DD",count` — one line per day, no header row.
- The workflow can be triggered on any day. It always resumes from where the files left off.

## Step 1 — Determine the last recorded date

Read the last line of `.github/uvs.csv` (or `.github/views.csv` — they should be in sync). Parse the `"MM/DD"` date to determine the last day already recorded. Assume the current year for the date.

If both files are empty, treat the start date as 14 days ago (the maximum the GitHub API provides).

## Step 2 — Fetch traffic data

Use the `gh` CLI to call the GitHub Traffic API for this repository:

```bash
gh api repos/{owner}/{repo}/traffic/views
```

The response includes a `views` array with objects containing `timestamp`, `count`, and `uniques` for each day in the last 14 days.

## Step 3 — Filter to new dates only

From the API response, keep only entries whose date is **after** the last recorded date from Step 1.

Also exclude **today's date** since the day is not yet complete and the numbers would be partial.

Format each kept date as `"MM/DD"` (zero-padded month and day, no year).

If there are no new dates to add, stop here and report that no new data is available.

## Step 4 — Append new rows

Append the new rows to the end of each file, keeping the existing data intact:

- **`.github/uvs.csv`** — append `"MM/DD",{uniques}` for each new day
- **`.github/views.csv`** — append `"MM/DD",{count}` for each new day

Rows should be in chronological order (earliest date first).

## Step 5 — Open a pull request

Create a pull request targeting the `main` branch. The PR title should summarize the date range, e.g.:

> Add traffic data for week of MM/DD – MM/DD

The PR body should include:

1. The date range collected
2. Total views and unique visitors for the week
3. A short table or list showing the daily breakdown
