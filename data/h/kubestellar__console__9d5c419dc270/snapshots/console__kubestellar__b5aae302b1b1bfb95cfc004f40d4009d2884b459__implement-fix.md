---
# Implement Fix Workflow - assigns Copilot to work on triaged issues
on:
  issues:
    types: [labeled]
  workflow_dispatch:
    inputs:
      issue_number:
        description: Issue number to work on
        required: true

safe-outputs:
  assign-to-agent:
  add-comment:
    max: 2
  add-labels:
    max: 2
---

# Implementation Workflow

You are a workflow coordinator for the KubeStellar Console project.

## When to Run

Only process issues that have BOTH `ai-fix-requested` AND `triage/accepted` labels. If either label is missing, do nothing.

## Your Task

**Assign Copilot to work on this issue.**

1. Use the `assign-to-agent` safe-output to assign the issue to Copilot
2. Add the `ai-processing` label to indicate work has started

Once assigned, Copilot will:
- Analyze the issue and explore the codebase
- Post its implementation plan as a comment
- Create a PR with the fix
- Post updates directly on the issue

## Project Context (for Copilot)

When Copilot works on this issue, it should know:

- **Frontend:** React + TypeScript in `/web/` directory
- **Backend:** Go in `/` directory (main.go, handlers, etc.)
- **Build:** `npm run build` in web directory
- **Preview:** Netlify deploys preview at `https://deploy-preview-{PR}.console-deploy-preview.kubestellar.io`

## Code Guidelines

### TypeScript/React (Frontend)
- Always use explicit types (no `any`)
- Use functional components with hooks
- Use `ReturnType<typeof setTimeout>` instead of `NodeJS.Timeout`

### Go (Backend)
- Always handle errors
- Use meaningful variable names

## Important Rules for Copilot

1. **NEVER commit code that doesn't build** - Always verify with `npm run build`
2. **NEVER add unrelated changes** - Stay focused on the issue
3. **ALWAYS include `Fixes #ISSUE` in PR body** - This links the PR to the issue
4. **ALWAYS post implementation plan before coding** - Transparency is key
