---
description: Quarterly Adoptium issue burn-down report. Data is fetched and aggregated deterministically; the agent only ranks and writes.
on:
  schedule:
    - cron: "0 9 1 */3 *"
  workflow_dispatch:
engine:
  id: copilot
  model: gpt-4o
timeout-minutes: 30
permissions:
  contents: read
  issues: read
  pull-requests: read
  copilot-requests: write
network:
  allowed:
    - defaults
steps:
  - name: Fetch and aggregate quarterly issue burn-down data
    env:
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    run: |
      set -euo pipefail
      mkdir -p /tmp/gh-aw/agent

      # Reporting window: the last full calendar quarter relative to today.
      Y=$(date -u +%Y); M=$(date -u +%-m); CQ=$(( (M-1)/3 ))
      if [ "$CQ" -eq 0 ]; then
        START="$((Y-1))-10-01"; END="$((Y-1))-12-31"
      else
        SM=$(( (CQ-1)*3 + 1 )); EM=$(( SM+2 ))
        START=$(printf '%d-%02d-01' "$Y" "$SM")
        END=$(date -u -d "$(printf '%d-%02d-01' "$Y" "$EM") +1 month -1 day" +%Y-%m-%d)
      fi
      STALE=$(date -u -d '30 days ago' +%Y-%m-%d)
      echo "Period: $START..$END   Stale-before: $STALE"

      # 1) Issues opened in the period (keep state + labels for the label tally).
      gh api -X GET search/issues \
        -f q="org:adoptium is:issue created:$START..$END" \
        -f per_page=100 --paginate \
        --jq '.items[] | {repo: (.repository_url | sub("https://api.github.com/repos/";"")), state, labels: [.labels[].name]}' \
        | jq -s '.' > /tmp/gh-aw/agent/opened.json

      # 2) Issues closed in the period.
      gh api -X GET search/issues \
        -f q="org:adoptium is:issue closed:$START..$END" \
        -f per_page=100 --paginate \
        --jq '.items[] | {repo: (.repository_url | sub("https://api.github.com/repos/";""))}' \
        | jq -s '.' > /tmp/gh-aw/agent/closed.json

      # 3) Stale open issues (no activity in the last 30 days), oldest first.
      gh api -X GET search/issues \
        -f q="org:adoptium is:issue is:open updated:<$STALE" \
        -f sort=updated -f order=asc \
        -f per_page=100 --paginate \
        --jq '.items[] | {repo: (.repository_url | sub("https://api.github.com/repos/";"")), title, url: .html_url, updated: .updated_at}' \
        | jq -s '.' > /tmp/gh-aw/agent/stale.json

      # Aggregate everything deterministically into summary.json.
      jq -n \
        --slurpfile opened /tmp/gh-aw/agent/opened.json \
        --slurpfile closed /tmp/gh-aw/agent/closed.json \
        --slurpfile stale  /tmp/gh-aw/agent/stale.json \
        --arg start "$START" --arg end "$END" --arg stale_before "$STALE" \
        '
        ($opened[0]) as $o | ($closed[0]) as $c | ($stale[0]) as $s |
        ([$o[].repo] | group_by(.) | map({repo: .[0], opened: length})) as $orepo |
        ([$c[].repo] | group_by(.) | map({repo: .[0], closed: length})) as $crepo |
        ([$s[].repo] | group_by(.) | map({repo: .[0], stale: length}))  as $srepo |
        ([ $orepo[].repo, $crepo[].repo, $srepo[].repo ] | unique) as $repos |
        {
          period_start: $start,
          period_end: $end,
          stale_before: $stale_before,
          total_opened: ($o | length),
          total_closed: ($c | length),
          total_stale_open: ($s | length),
          repositories: (
            $repos | map(. as $r |
              ((($orepo[] | select(.repo==$r) | .opened) // 0)) as $op |
              ((($crepo[] | select(.repo==$r) | .closed) // 0)) as $cl |
              ((($srepo[] | select(.repo==$r) | .stale)  // 0)) as $st |
              {
                repo: $r,
                opened: $op,
                closed: $cl,
                burn_down: ($cl - $op),
                stale: $st,
                stale_examples: ( [ $s[] | select(.repo==$r) ] | .[0:5] )
              }
            ) | sort_by(-.stale)
          ),
          underserved_labels: (
            [ $o[] | . as $i | $i.labels[] | {label: ., state: $i.state} ]
            | group_by(.label)
            | map({
                label: .[0].label,
                open:   ([.[] | select(.state=="open")]   | length),
                closed: ([.[] | select(.state=="closed")] | length)
              })
            | map(. + {deficit: (.open - .closed)})
            | sort_by(-.deficit)
            | .[0:10]
          )
        }
        ' > /tmp/gh-aw/agent/summary.json
      echo "=== summary.json ==="
      cat /tmp/gh-aw/agent/summary.json
safe-outputs:
  create-issue:
    title-prefix: "[burndown] "
    labels: [report, burndown]
    close-older-issues: true
---
# Adoptium Issue Burn-down Report
All GitHub data has already been fetched and aggregated for you before this step. Do NOT call any GitHub tools or shell commands to fetch data — everything you need is on disk.
## Pre-fetched data
- `/tmp/gh-aw/agent/summary.json` — pre-computed aggregates: reporting window, org totals, per-repository opened/closed/burn-down/stale counts (already sorted by stale count, most first) with up to 5 stale-issue examples each, and the top 10 under-served labels ranked by `open - closed`. Read this first; it contains everything the report needs.
- `/tmp/gh-aw/agent/stale.json` — the full list of stale open issues (repo, title, url, last-updated) if you need more detail than the per-repo examples.
- `/tmp/gh-aw/agent/opened.json` and `/tmp/gh-aw/agent/closed.json` — the underlying opened/closed issue records, if needed.
## Your task
Using only the files above, write a concise quarterly issue burn-down report and create exactly one GitHub issue in this repository. Every figure and issue title in the report must be copied from these files — do not invent, estimate, or add repositories or issues that are not present in the data.
## The issue must contain
- A header summary: the reporting window (`period_start` to `period_end`), total issues opened, total closed, and total stale open across the org.
- A per-repository table sorted by stale count (as already ordered in `summary.json`): repository, opened, closed, burn-down score (`closed - opened`; negative means the backlog grew), and stale count. Skip repositories whose opened, closed, and stale counts are all zero.
- For each repository with stale issues, list its up-to-5 stale examples from `stale_examples`, showing title, link, and last-updated date, most-stale first.
- An "Under-served labels" section from `underserved_labels`: the top 10 labels where open issues outpace closed, with their open and closed counts.
- A short "Items needing maintainer attention next quarter" note, drawn only from what the data shows (e.g., repositories with the most negative burn-down or the highest stale counts).
## Constraints
- Create exactly one issue.
- Do not fetch any additional data; rank and summarize only what is on disk.
- If `summary.json` shows zero activity everywhere, still create the issue and state that the org had no qualifying issue activity in the window.
- Keep it concise and skimmable.
