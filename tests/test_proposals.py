#verifies Milestone 3 proposal, approval, and rollback safety

import pytest

from model import (
    DiagnosticReport,
    FileChange,
    RepairPlan,
)
from proposal_manager import (
    apply_proposal,
    load_proposal,
    rollback_proposal,
    save_proposal,
)


def create_test_plan() -> RepairPlan:
    """Create a controlled proposal for testing."""

    diagnostic = DiagnosticReport(
        summary="The add function subtracts.",
        test_status="failed",
        problems=["The add function uses subtraction."],
        evidence=["add(2, 3) returned -1."],
        root_causes=["The wrong operator is used."],
        proposed_fixes=["Replace subtraction with addition."],
        risk="low",
        tests_to_rerun=["tests/test_calculator.py"],
    )

    return RepairPlan(
        diagnostic=diagnostic,
        changes=[
            FileChange(
                file_path="sample_app/calculator.py",
                reason="Correct the arithmetic operator.",
                original_text="return a - b\n",
                replacement_text="return a + b\n",
            )
        ],
    )


def test_proposal_requires_separate_apply_step(tmp_path):
    """Saving a proposal must not modify source code."""

    sample_directory = tmp_path / "sample_app"
    sample_directory.mkdir()

    calculator = sample_directory / "calculator.py"
    calculator.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    proposal_id = save_proposal(
        create_test_plan(),
        project_root=tmp_path,
    )

    #saving the proposal did not change the source
    assert "return a - b" in calculator.read_text(
        encoding="utf-8"
    )

    _, envelope = load_proposal(
        proposal_id,
        project_root=tmp_path,
    )

    assert envelope["status"] == "pending"


def test_proposal_can_be_applied_and_rolled_back(tmp_path):
    """An approved change works and has a backup."""

    sample_directory = tmp_path / "sample_app"
    sample_directory.mkdir()

    calculator = sample_directory / "calculator.py"
    calculator.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    proposal_id = save_proposal(
        create_test_plan(),
        project_root=tmp_path,
    )

    apply_proposal(
        proposal_id,
        project_root=tmp_path,
    )

    assert "return a + b" in calculator.read_text(
        encoding="utf-8"
    )

    rollback_proposal(
        proposal_id,
        project_root=tmp_path,
    )

    assert "return a - b" in calculator.read_text(
        encoding="utf-8"
    )


def test_path_outside_project_is_rejected(tmp_path):
    """A proposal cannot escape the project directory."""

    plan = create_test_plan()
    plan.changes[0].file_path = "../private.py"

    with pytest.raises(ValueError):
        save_proposal(
            plan,
            project_root=tmp_path,
        )