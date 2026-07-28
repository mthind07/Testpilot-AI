# TestPilot AI

[![TestPilot CI](https://github.com/mthind07/Testpilot-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/mthind07/Testpilot-AI/actions/workflows/ci.yml)

A safety-first, agentic software testing and debugging platform that
investigates failing Python tests, proposes validated repairs, and keeps
developers in control of every source-code change.

## What TestPilot does

TestPilot combines specialized AI agents with deterministic validation:

1. Runs the project's pytest suite
2. Collects trusted failure evidence
3. Plans an investigation
4. Diagnoses root causes
5. Produces exact code changes
6. Validates the proposed diff
7. Performs an independent review
8. Saves a pending proposal
9. Waits for explicit human approval
10. Applies the repair and reruns tests
11. Supports rollback when an applied repair is unsuccessful

## Features
- Structured diagnostic reports
- Planner, debugger, validator, and reviewer agents
- Exact unified-diff previews
- Human-in-the-loop repair approval
- Protected paths and traversal prevention
- Automatic backups and rollback
- SQLite diagnostic history
- Streamlit operations dashboard
- Deterministic release evaluations
- GitHub Actions CI and automated releases

## Technology
- Python 3.12
- uv
- Strands Agents
- Google Gemini
- Pydantic
- pytest
- SQLite
- Streamlit
- GitHub Actions

## Architecture

```mermaid
flowchart LR
    A[Pytest evidence] --> B[Planner agent]
    B --> C[Debugger agent]
    C --> D[Deterministic validator]
    D --> E[Reviewer agent]
    E --> F[Pending proposal]
    F --> G{Human decision}
    G -->|APPLY| H[Backup and apply]
    H --> I[Rerun pytest]
    I -->|Pass| J[Verified repair]
    I -->|Fail| K[Rollback available]
    G -->|Reject| L[No files changed]

