#Milestone 5: combines  existing components created in milestone 4 into one reusable workflow that can later be called by a dashboard, API, or terminal.
#this workflow never applies a repair automatically, an approved repair is saved only as a pending proposal & the user must still run main.py --apply and type APPLY

from __future__ import annotations

from pathlib import Path
from typing import Any

from model import create_model
from multi_agent_workflow import (
    PROJECT_ROOT,
    run_multi_agent_workflow,
)
from proposal_manager import save_proposal
from storage import initialize_database, save_report


def run_workflow(
    model: Any | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    """Run TestPilot from evidence collection to a pending proposal.

    This returns a dictionary so a future dashboard or API can easily
    display the workflow result.
    """

    #ensure the Milestone 2 SQLite database exists
    initialize_database()

    #normally TestPilot creates the Gemini model, allowing a model to be supplied also makes the function testable
    active_model = model if model is not None else create_model()


    result = run_multi_agent_workflow(
        model=active_model,
        project_root=project_root,
    )

    #store a consistent summary for every possible result
    outcome: dict[str, object] = {
        "status": result.status,
        "message": result.message,
        "diagnostic_run_id": None,
        "proposal_id": None,
        "proposed_diff": result.proposed_diff,
        "validation_issues": [],
        "reviewer_concerns": [],
    }

    #passing tests do not need a repair, evidence errors must never create a proposal
    if result.status in {"no_failures", "error"}:
        return outcome

    repair_plan = result.repair_plan
    validation = result.validation_result
    review = result.review_decision

    #refuse incomplete AI results
    if repair_plan is None or validation is None or review is None:
        return {
            **outcome,
            "status": "error",
            "message": (
                "The multi-agent workflow returned incomplete results. "
                "No proposal was saved."
            ),
        }

    #save the debugger's diagnostic in Milestone 2's history database
    diagnostic_run_id = save_report(
        report=repair_plan.diagnostic,
        stop_reason=f"milestone-5-{result.status}",
    )

    outcome["diagnostic_run_id"] = diagnostic_run_id
    outcome["validation_issues"] = list(validation.issues)
    outcome["reviewer_concerns"] = list(review.concerns)

    #rejected repairs are recorded but cannot become proposals
    if result.status != "approved":
        return outcome

    #prevents an AI reviewer from approving an invalid repair
    if not validation.valid or not review.approved:
        return {
            **outcome,
            "status": "rejected",
            "message": (
                "The workflow failed its final safety gate. "
                "No proposal was saved."
            ),
        }

    #save the approved repair as a pending proposal
    proposal_id = save_proposal(
        repair_plan,
        project_root=project_root,
    )

    outcome["proposal_id"] = proposal_id
    outcome["message"] = (
        "The workflow approved and saved a pending repair proposal. "
        "No project files were changed."
    )

    return outcome


def display_outcome(outcome: dict[str, object]) -> None:
    """Print a beginner-friendly summary of one workflow run."""

    print("\n========== MILESTONE 5 WORKFLOW RESULT ==========\n")

    print(f"Status: {outcome['status']}")
    print(f"Message: {outcome['message']}")

    diagnostic_run_id = outcome.get("diagnostic_run_id")

    if diagnostic_run_id is not None:
        print(f"Diagnostic run: #{diagnostic_run_id}")

    validation_issues = outcome.get(
        "validation_issues",
        [],
    )

    if validation_issues:
        print("\nPython validation issues:")

        for issue in validation_issues:
            print(f"- {issue}")

    reviewer_concerns = outcome.get(
        "reviewer_concerns",
        [],
    )

    if reviewer_concerns:
        print("\nReviewer concerns:")

        for concern in reviewer_concerns:
            print(f"- {concern}")

    proposed_diff = outcome.get("proposed_diff")

    if proposed_diff:
        print("\n========== VALIDATED DIFF ==========\n")
        print(proposed_diff)

    proposal_id = outcome.get("proposal_id")

    if proposal_id:
        print("\n========== PENDING PROPOSAL ==========\n")
        print(f"Proposal ID: {proposal_id}")
        print("No project files were changed.")

        print("\nTo review and apply it, run:")
        print(f"uv run main.py --apply {proposal_id}")


def main() -> None:
    """Run Milestone 5 directly from Kiro's terminal."""

    try:
        outcome = run_workflow()

    except KeyboardInterrupt:
        print("\nMilestone 5 workflow cancelled.")
        return

    except Exception as error:
        print("\nMilestone 5 workflow could not complete.")
        print(f"{type(error).__name__}: {error}")
        print("No project files were changed.")

        raise SystemExit(1) from error

    display_outcome(outcome)


if __name__ == "__main__":
    main()