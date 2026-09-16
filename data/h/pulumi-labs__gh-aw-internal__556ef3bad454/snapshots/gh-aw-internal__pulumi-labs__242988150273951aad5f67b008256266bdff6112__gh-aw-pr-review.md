---
description: Automated PR review for trusted internal contributors.
timeout-minutes: 15
strict: true
permissions:
  contents: read
  pull-requests: read
  id-token: write
on:
  pull_request:
    types: [opened, ready_for_review]
  workflow_dispatch:
    inputs:
      pr_number:
        description: "Pull request number to review"
        required: true
        type: string
imports:
  - shared/review.md
  - shared/plugins/code-review/code-review.md
---

# Internal Trusted PR Reviewer

Draft review policy: This workflow may review draft PRs only when manually dispatched with `workflow_dispatch`. For automatic `pull_request` runs, call `noop` if the pull request is a draft.
