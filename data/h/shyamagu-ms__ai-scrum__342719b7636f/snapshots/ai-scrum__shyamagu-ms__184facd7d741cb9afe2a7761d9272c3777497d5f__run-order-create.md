---
name: 依頼事項整理

on:
  workflow_dispatch:
  workflow_call:

engine:
  id: copilot
  model: claude-opus-4.6

timeout-minutes: 360

permissions: read-all

network:
  allowed:
    - defaults

tools:
  edit:
  bash: true
  github:

safe-outputs:
  create-pull-request:
    draft: true
    protected-files: fallback-to-issue

---

`.github/skills/order-create-without-user/SKILL.md` の指示に従い、依頼事項の整理を実施してください。

完了後、全ての変更ファイルをコミットし、`create_pull_request` ツールを呼び出してPRを作成してください。
