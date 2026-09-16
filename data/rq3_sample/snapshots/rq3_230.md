---
description: Run PR re-review on explicit maintainer slash command.
timeout-minutes: 15
strict: true
on:
  slash_command:
    name: [review-again, review]
    events: [pull_request_comment, pull_request_review_comment]
imports:
  - shared/review.md
  - shared/plugins/code-review/code-review.md
permissions:
  contents: read
  pull-requests: read
  id-token: write
---

# Internal PR Re-Review (Slash Command)

Draft review policy: This workflow is an explicit maintainer-requested slash-command review. Review draft PRs; do not call `noop` solely because the pull request is a draft.

Accepted slash commands: `/review-again` and `/review`.
