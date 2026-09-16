---
description: |
  Weekly check of all skills for staleness against their upstream source URLs.
  Compares each SKILL.md against the documentation it encodes and opens a PR
  if anything has drifted.

on:
  schedule: weekly
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: read
  issues: read

network: defaults

tools:
  github:
    lockdown: false
  web-fetch:
  edit:

safe-outputs:
  create-pull-request:
    title-prefix: "[skill-freshness] "
    labels: [automated, skill-freshness]
  add-comment:
  close-issue:
---

# Weekly Skill Freshness Check

Check all skills in `skills/**/SKILL.md` for staleness against their upstream source URLs.

## Process

1. Find every `SKILL.md` file under the `skills/` directory.
2. For each skill:
   - Read the SKILL.md file.
   - Identify every source URL in its reference/sources section.
   - Fetch each source URL and compare the upstream content against the rules, syntax, and options encoded in the skill.
   - If the skill is stale (new rules added, syntax changed, options removed, links broken), update the SKILL.md to reflect the current upstream state.
3. If any files changed, open a pull request summarizing what drifted and why.
4. If nothing changed, close this issue with a comment confirming all skills are current.
