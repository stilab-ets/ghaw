---
description: "AI code review on push to main"
on:
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: read

engine:
  id: claude

runtimes:
  node:
    version: "22"

network:
  allowed:
    - node

steps:
  - name: Save commit range
    env:
      BEFORE_SHA: ${{ github.event.before }}
      AFTER_SHA: ${{ github.event.after }}
    run: |
      echo "${BEFORE_SHA}..${AFTER_SHA}" > /tmp/gh-aw/commit-range.txt
      git log --oneline "${BEFORE_SHA}..${AFTER_SHA}" > /tmp/gh-aw/commit-log.txt 2>&1 || true
      git diff "${BEFORE_SHA}..${AFTER_SHA}" > /tmp/gh-aw/commit-diff.txt 2>&1 || true
  - name: Install dependencies
    run: |
      npm ci 2>&1 || npm install 2>&1 || true
    continue-on-error: true
  - name: Run lint
    run: |
      npx next lint > /tmp/gh-aw/lint-results.txt 2>&1 || true
    continue-on-error: true

safe-outputs:
  noop:
    report-as-issue: false
  create-pull-request:
    base-branch: dev
    title-prefix: "[code-review] "
    labels: [code-review, ai]
    reviewers: [okaris]
    max: 5

timeout-minutes: 30
---

# Code Review on Push

You are an expert code reviewer for a UI component registry (shadcn-based). Review pushed code for patterns/antipatterns.

## Step 1: Check Lint Results

```bash
cat /tmp/gh-aw/lint-results.txt
```

Fix any lint errors first.

## Step 2: Read the Diff

```bash
cat /tmp/gh-aw/commit-range.txt
cat /tmp/gh-aw/commit-log.txt
cat /tmp/gh-aw/commit-diff.txt
```

**Only review code from the commit diff. Do not scan unrelated parts of the repository.**

If the diff is empty, use the noop tool.

## Step 3: Review

- Compare against existing component patterns
- Check accessibility (aria attrs, keyboard nav, focus management)
- Check for proper TypeScript typing
- Flag style inconsistencies with existing components

## Output

Open **separate PRs** for each independent fix. Only fix things you're confident about.
