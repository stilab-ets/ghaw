---
description: |
  Demo agentic workflow that uses APM to install agent primitives (skills, instructions, agents)
  before the AI engine starts. Proves end-to-end integration of apm-action with GitHub Agentic Workflows.

on:
  workflow_dispatch:

timeout-minutes: 10

permissions: read-all

steps:
  - uses: actions/checkout@v4
    with:
      persist-credentials: false
  - name: Install agent primitives via APM
    uses: microsoft/apm-action@main
    with:
      skip-manifest: 'true'
      dependencies: |
        - microsoft/apm-sample-package
  - name: Verify primitives installed
    run: |
      echo "=== APM primitives installed ==="
      find .github -type f | grep -v workflows | head -20

tools:
  bash: true
  github:
    toolsets: [all]

engine: copilot
---

# APM Demo — Agent Primitives in Action

You are an agent running inside a GitHub Agentic Workflow with APM-installed primitives.

## Your Task

1. List all files under `.github/` (excluding workflows) to confirm agent primitives were deployed by APM
2. Read the contents of any instruction file found in `.github/instructions/`
3. Read the contents of any skill file found in `.github/skills/`
4. Summarize what primitives are available and confirm the APM + GH AW integration works

Report your findings as a GitHub Actions job summary.
