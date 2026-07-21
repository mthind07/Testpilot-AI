#creates the local SQLite database, saves every structured diagnostic report & allows previous runs to be viewed later

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from model import DiagnosticReport


DATABASE_PATH = Path(__file__).resolve().parent / "testpilot.db"


def initialize_database(
    database_path: Path = DATABASE_PATH,
) -> None:
    """Create the diagnostic_runs table if it does not already exist."""

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnostic_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                test_status TEXT NOT NULL,
                risk TEXT NOT NULL,
                summary TEXT NOT NULL,
                stop_reason TEXT NOT NULL,
                report_json TEXT NOT NULL
            )
            """
        )


def save_report(
    report: DiagnosticReport,
    stop_reason: str,
    database_path: Path = DATABASE_PATH,
) -> int:
    """Save one report and return its database ID."""

    created_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO diagnostic_runs (
                created_at,
                test_status,
                risk,
                summary,
                stop_reason,
                report_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                report.test_status,
                report.risk,
                report.summary,
                stop_reason,
                report.model_dump_json(),
            ),
        )

        return int(cursor.lastrowid)


def list_recent_runs(
    limit: int = 5,
    database_path: Path = DATABASE_PATH,
) -> list[dict]:
    """Return a summary of the newest diagnostic runs."""

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                test_status,
                risk,
                summary,
                stop_reason
            FROM diagnostic_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]