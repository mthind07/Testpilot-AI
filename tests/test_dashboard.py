#tests for Milestone 6 dashboard safety helpers

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import dashboard


def test_dashboard_loads_without_errors() -> None:
    """The complete Streamlit page should render successfully."""

    #AppTest opens the page without starting a real browser
    app = AppTest.from_file("dashboard.py")

    #give the dashboard up to 10 seconds to load
    app.run(timeout=10)

    #page should load without a Streamlit exception
    assert not app.exception

    #confirm that the correct page was loaded
    assert app.title[0].value == "TestPilot AI"


def test_list_saved_proposals_returns_newest_first(
    tmp_path: Path,
) -> None:
    """The dashboard should show safe proposal metadata."""

    #ARRANGE:
    #create a temporary proposal folder just for this test
    proposals_directory = (
        tmp_path / ".testpilot_proposals"
    )
    proposals_directory.mkdir()

    older_id = "proposal-20260726-100000-aaaaaaaa"
    newer_id = "proposal-20260726-110000-bbbbbbbb"

    for proposal_id, created_at, status in [
        (
            older_id,
            "2026-07-26T10:00:00+00:00",
            "applied",
        ),
        (
            newer_id,
            "2026-07-26T11:00:00+00:00",
            "pending",
        ),
    ]:
        #use the same JSON structure saved by proposal_manager
        envelope = {
            "proposal_id": proposal_id,
            "status": status,
            "created_at": created_at,
            "plan": {
                "diagnostic": {
                    "summary": (
                        f"Summary for {proposal_id}"
                    ),
                    "risk": "low",
                }
            },
        }

        proposal_file = (
            proposals_directory
            / f"{proposal_id}.json"
        )

        proposal_file.write_text(
            json.dumps(envelope),
            encoding="utf-8",
        )

    #ACT:
    #ask the dashboard helper to read the proposals
    proposals = dashboard.list_saved_proposals(
        tmp_path
    )

    #ASSERT:
    #the newest proposal should appear first
    assert [
        proposal["proposal_id"]
        for proposal in proposals
    ] == [
        newer_id,
        older_id,
    ]

    assert proposals[0]["status"] == "pending"


def test_apply_requires_exact_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lowercase approval must not modify any file."""

    was_called = False

    #this fake records whether apply_proposal was reached
    def fake_apply(*args, **kwargs):
        nonlocal was_called

        was_called = True
        return []

    #replace the real file-changing function with the fake
    monkeypatch.setattr(
        dashboard,
        "apply_proposal",
        fake_apply,
    )

    #lowercase "apply" must be rejected
    with pytest.raises(
        ValueError,
        match="Type APPLY exactly",
    ):
        dashboard.apply_from_dashboard(
            "proposal-20260726-110000-bbbbbbbb",
            "apply",
            tmp_path,
        )

    #confirm that the file-changing function was never called
    assert was_called is False


def test_apply_runs_tests_after_the_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful apply must immediately run pytest."""

    #replace the real apply function with a safe fake
    monkeypatch.setattr(
        dashboard,
        "apply_proposal",
        lambda proposal_id, project_root: [
            "sample_app/calculator.py"
        ],
    )

    #replace pytest execution with a predictable passing result
    monkeypatch.setattr(
        dashboard,
        "execute_python_tests",
        lambda project_root: (
            0,
            "17 passed",
        ),
    )

    #exact uppercase confirmation should be accepted
    result = dashboard.apply_from_dashboard(
        "proposal-20260726-110000-bbbbbbbb",
        "APPLY",
        tmp_path,
    )

    #the action should be reported as applied
    assert result["action"] == "applied"

    #the result should list the changed file
    assert result["files"] == [
        "sample_app/calculator.py"
    ]

    #pytest should have been run and reported as passing
    assert result["test_result"]["passed"] is True


def test_rollback_requires_exact_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback must have its own explicit confirmation."""

    was_called = False

    #this fake records whether rollback_proposal was reached
    def fake_rollback(*args, **kwargs):
        nonlocal was_called

        was_called = True
        return []

    #replace the real restore function with the fake
    monkeypatch.setattr(
        dashboard,
        "rollback_proposal",
        fake_rollback,
    )

    #lowercase "rollback" must be rejected
    with pytest.raises(
        ValueError,
        match="Type ROLLBACK exactly",
    ):
        dashboard.rollback_from_dashboard(
            "proposal-20260726-110000-bbbbbbbb",
            "rollback",
            tmp_path,
        )

    #confirm that no restore was attempted
    assert was_called is False


def test_rollback_restores_files_and_runs_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approved rollback should restore backups and rerun pytest."""

    #fake the restoration of one file
    monkeypatch.setattr(
        dashboard,
        "rollback_proposal",
        lambda proposal_id, project_root: [
            "sample_app/calculator.py"
        ],
    )

    #fake a failing post-rollback pytest result
    #the dashboard must display failures instead of hiding them
    monkeypatch.setattr(
        dashboard,
        "execute_python_tests",
        lambda project_root: (
            1,
            "1 failed",
        ),
    )

    #exact uppercase confirmation should be accepted
    result = dashboard.rollback_from_dashboard(
        "proposal-20260726-110000-bbbbbbbb",
        "ROLLBACK",
        tmp_path,
    )

    #the action should be reported as rolled back
    assert result["action"] == "rolled_back"

    #the restored file should be included in the result
    assert result["files"] == [
        "sample_app/calculator.py"
    ]

    #the failing pytest result must still be reported accurately
    assert result["test_result"]["passed"] is False