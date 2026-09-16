---
name: デイリー3日目

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

`.github/skills/one-day-in-scrum/SKILL.md` の指示に従い、デイリースクラムとインクリメント作成を実施してください。
- 対応日: Day3

完了後、全ての変更ファイルをコミットし、`create_pull_request` ツールを呼び出してPRを作成してください。
