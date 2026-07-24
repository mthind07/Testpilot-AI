#CLI integration tests for Milestone 4 proposal saving

import main
from model import (
    MultiAgentWorkflowResult,
    ProjectEvidence,
    RepairPlan,
    ReviewDecision,
    ValidationResult,
)

from tests.test_multi_agent_workflow import (
    make_investigation_plan,
    make_repair_plan,
)


def test_approved_team_workflow_uses_save_proposal(
    monkeypatch,
):
    """The CLI calls Milestone 3's real save_proposal interface."""

    plan: RepairPlan = make_repair_plan()
    result = MultiAgentWorkflowResult(
        status="approved",
        message="Approved.",
        evidence=ProjectEvidence(
            project_files=[
                "sample_app/calculator.py",
                "tests/test_calculator.py",
            ],
            pytest_exit_code=1,
            pytest_output="1 failed",
            file_contents={
                "sample_app/calculator.py": (
                    "def divide(a, b):\n"
                    "    return a + b\n"
                ),
            },
        ),
        investigation_plan=make_investigation_plan(),
        repair_plan=plan,
        validation_result=ValidationResult(
            valid=True,
            proposed_diff="--- a/file\n+++ b/file",
        ),
        review_decision=ReviewDecision(
            approved=True,
            summary="Approved.",
            verified_changes=["Exact divide repair."],
        ),
        proposed_diff="--- a/file\n+++ b/file",
    )

    saved_plans: list[RepairPlan] = []

    monkeypatch.setattr(main, "create_model", lambda: object())
    monkeypatch.setattr(
        main,
        "run_multi_agent_workflow",
        lambda model: result,
    )
    monkeypatch.setattr(
        main,
        "save_report",
        lambda report, stop_reason: 17,
    )
    monkeypatch.setattr(
        main,
        "save_proposal",
        lambda repair_plan: (
            saved_plans.append(repair_plan)
            or "proposal-20260723-120000-abcdef12"
        ),
    )

    main.run_team_proposal_mode()

    assert saved_plans == [plan]