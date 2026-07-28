# Changelog

All notable changes to TestPilot AI are documented here

## [1.0.0] - 2026-07-27

### Added

- Safe project file inspection and pytest execution
- Structured AI-generated diagnostic reports
- SQLite-backed diagnostic history
- Human-reviewed repair proposals
- Exact diff validation before modification
- Explicit APPLY confirmation
- Backups and rollback support
- Planner, debugger, validator, and reviewer agents
- End-to-end workflow orchestration
- Streamlit operations dashboard
- Deterministic release evaluations
- GitHub Actions CI and automated releases

### Safety

- AI agents cannot directly modify project files
- Proposed paths are restricted to approved project areas
- Ambiguous text replacements are rejected
- Protected TestPilot files cannot be rewritten by the agent
- Every repair requires human approval
- Applied repairs are verified by rerunning pytest