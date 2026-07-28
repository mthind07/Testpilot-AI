# TestPilot AI Security

## Secret handling

Never commit any of the following:

- `.env`
- `.streamlit/secrets.toml`
- Gemini API keys
- Personal credentials

If a key is accidentally committed, revoke it immediately in Google AI Studio
and create a new key. Removing the key from only the latest commit is not
enough because it may remain in Git history.

## Repair safety

TestPilot uses a human-in-the-loop repair process:

1. Agents inspect project evidence.
2. A repair is proposed as an exact diff.
3. Deterministic validation checks the proposal.
4. A reviewer agent assesses the repair.
5. A human must approve it explicitly.
6. Tests run after application.
7. Backups allow rollback if verification fails.

## Reporting security issues

Do not include API keys or private source code in a public GitHub issue.
Use GitHub private vulnerability reporting if it is enabled for this
repository.