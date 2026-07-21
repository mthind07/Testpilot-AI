#confirms that Milestone 2 can save and retrieve reports.

from model import DiagnosticReport
from storage import (
    initialize_database,
    list_recent_runs,
    save_report,
)


def test_report_can_be_saved_and_retrieved(tmp_path):
    database_path = tmp_path / "testpilot-test.db"

    initialize_database(database_path)

    report = DiagnosticReport(
        summary="A controlled storage test.",
        test_status="failed",
        problems=["Example problem"],
        evidence=["Example evidence"],
        root_causes=["Example root cause"],
        proposed_fixes=["Example proposed fix"],
        risk="low",
        tests_to_rerun=["tests/test_example.py"],
    )

    run_id = save_report(
        report=report,
        stop_reason="end_turn",
        database_path=database_path,
    )

    runs = list_recent_runs(
        limit=5,
        database_path=database_path,
    )

    assert run_id == 1
    assert len(runs) == 1
    assert runs[0]["summary"] == "A controlled storage test."
    assert runs[0]["test_status"] == "failed"
    assert runs[0]["risk"] == "low"