---
on:
  schedule: weekly
  workflow_dispatch:

engine:
  id: copilot
  model: claude-opus-4.6

permissions:
  contents: read

network:
  allowed:
    - defaults
    - github
    - "github.blog"

safe-outputs:
  create-pull-request:
    title-prefix: "[news] "
    labels: [news, automated]
    draft: true
    allowed-files:
      - docs/news/articles/**
---

# AI Coding News Excerpts

Scan the GitHub Blog changelog for new Copilot-related announcements and create excerpt files in `docs/news/articles/`.

## What to do

1. Read the existing excerpt files in `docs/news/articles/` to understand the format and avoid duplicates.
2. Fetch `https://github.blog/changelog/` and find announcements tagged `copilot` from the past 7 days.
3. For each new announcement that does NOT already have an excerpt file, create one.

## Excerpt file format

Each excerpt is a markdown file with ONLY YAML frontmatter (no body content). Follow this exact format:

```markdown
---
title: "Title in Norwegian (bokmål)"
date: YYYY-MM-DD
category: copilot
excerpt: "One-sentence Norwegian summary of the announcement."
url: "https://github.blog/changelog/..."
tags:
  - relevant-tag
---
```

## Rules

- **Language**: Title and excerpt in Norwegian (bokmål). Use English tech terms where developers do (e.g. "MCP", "PR", "GA", "public preview").
- **Filename**: Derive from the URL slug, e.g. `figma-mcp-server.md`, `vscode-v1-110.md`. Keep it short and descriptive.
- **No duplicates**: If an excerpt file already exists for an announcement (check by URL in frontmatter), skip it.
- **Only Copilot-related**: Skip announcements not related to GitHub Copilot, AI coding, or developer tools.
- **Tags**: Use lowercase kebab-case. Reuse existing tags from other excerpt files when applicable.
- **Date**: Use the announcement date from the changelog, not today's date.

## Scope

Only create or modify files under `docs/news/articles/`. Do not modify any other files.
