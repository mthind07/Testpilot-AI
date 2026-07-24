#Milestone 1: Agent inspected code and ran tests

#Milestone 2: Code is divided into modules, report output follows a validated structure & reports are saved in SQLite
#agent is still read-only & can't edit project files

#Milestone 3: Creates safe fix proposals, requires approval, verifies fixes, and supports rollback 

#Milestone 4: 

import argparse

from strands import Agent

from agent_tools import (
    list_project_files,
    read_project_file,
    reset_test_cache,
    run_python_tests,
)
from model import DiagnosticReport, RepairPlan, create_model
from multi_agent_workflow import run_multi_agent_workflow
from proposal_manager import (
    apply_proposal,
    get_proposal_diff,
    rollback_proposal,
    save_proposal,
)
from storage import (
    DATABASE_PATH,
    initialize_database,
    list_recent_runs,
    save_report,
)


SYSTEM_PROMPT = """
You are TestPilot AI, a read-only software testing and debugging agent.

Your job is to:
1. Inspect the available project files.
2. Read only files relevant to the failure.
3. Run the Python tests exactly once.
4. Compare test failures with the source code.
5. Separate source defects from incorrectly written tests.
6. Produce an evidence-backed structured diagnostic report.

Rules:
- Never claim that you modified a file.
- Never claim that a suggested fix was applied.
- Never invent test results.
- Do not repeatedly call run_python_tests.
- Do not read secrets, databases, virtual environments, or Git data.
"""


DIAGNOSTIC_TASK = """
Analyze this Python project.
List the project files, inspect the relevant source and tests, and run pytest.
Return a structured DiagnosticReport backed by the observed evidence.
Proposed fixes must remain recommendations only.
"""


PROPOSAL_TASK = """
Analyze this Python project and prepare an exact RepairPlan.

Required process:
1. List the project files.
2. Read relevant source and test files.
3. Run pytest exactly once.
4. Identify source-code defects and test defects.
5. Produce exact, unique text replacements.

Rules:
- Do not modify any files.
- original_text must match existing file content exactly.
- Include enough surrounding text to make replacements unique.
- Do not change TestPilot infrastructure or safety tests.
- Only propose changes inside sample_app/ or related tests.
"""


def display_history() -> None:
    """Print the five most recent diagnostic runs."""

    runs = list_recent_runs(limit=5)
    print("\n========== RECENT TESTPILOT RUNS ==========\n")

    if not runs:
        print("No saved diagnostic runs were found.")
        return

    for run in runs:
        print(
            f"Run #{run['id']} | "
            f"Status: {run['test_status']} | "
            f"Risk: {run['risk']}"
        )
        print(f"Created: {run['created_at']}")
        print(f"Summary: {run['summary']}")
        print(f"Stop reason: {run['stop_reason']}")
        print()


def build_agent() -> Agent:
    """Create the original read-only TestPilot agent."""

    return Agent(
        model=create_model(),
        tools=[
            list_project_files,
            read_project_file,
            run_python_tests,
        ],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None,
    )


def run_diagnostic() -> None:
    """Run one Milestone 2 diagnostic session."""

    print("\n========== TESTPILOT AI: DIAGNOSTIC ==========\n")
    print("Starting a read-only diagnostic run...\n")

    initialize_database()
    reset_test_cache()
    agent = build_agent()

    try:
        result = agent(
            DIAGNOSTIC_TASK,
            structured_output_model=DiagnosticReport,
            limits={
                "turns": 10,
                "output_tokens": 3000,
                "total_tokens": 20_000,
            },
        )
    except Exception as error:
        print("\nThe diagnostic run failed.")
        print(f"{type(error).__name__}: {error}")
        raise SystemExit(1) from error

    report = result.structured_output
    if report is None:
        raise SystemExit(
            "Gemini finished without producing a DiagnosticReport."
        )

    run_id = save_report(
        report=report,
        stop_reason=str(result.stop_reason),
    )

    print("\n========== STRUCTURED REPORT ==========\n")
    print(report.model_dump_json(indent=2))
    print("\n========== RUN INFORMATION ==========\n")
    print(f"Saved run: #{run_id}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Database: {DATABASE_PATH.name}")


def create_repair_proposal() -> None:
    """Run the original Milestone 3 single-agent proposal mode."""

    print("\n========== TESTPILOT REPAIR PROPOSAL ==========\n")
    print("No source files will be modified.\n")

    initialize_database()
    reset_test_cache()
    agent = build_agent()

    try:
        result = agent(
            PROPOSAL_TASK,
            structured_output_model=RepairPlan,
            limits={
                "turns": 10,
                "output_tokens": 5000,
                "total_tokens": 25_000,
            },
        )
    except Exception as error:
        print("Proposal generation failed.")
        print(f"{type(error).__name__}: {error}")
        raise SystemExit(1) from error

    plan = result.structured_output
    if plan is None:
        raise SystemExit(
            "Gemini finished without producing a RepairPlan."
        )

    diagnostic_run_id = save_report(
        report=plan.diagnostic,
        stop_reason=str(result.stop_reason),
    )

    try:
        proposal_id = save_proposal(plan)
    except Exception as error:
        print("The proposed changes failed safety validation.")
        print(f"{type(error).__name__}: {error}")
        raise SystemExit(1) from error

    print("\n========== DIAGNOSTIC ==========\n")
    print(plan.diagnostic.model_dump_json(indent=2))
    print("\n========== PROPOSED CHANGES ==========\n")
    print(get_proposal_diff(proposal_id))
    print("\n========== APPROVAL INFORMATION ==========\n")
    print(f"Diagnostic run: #{diagnostic_run_id}")
    print(f"Proposal ID: {proposal_id}")
    print("Status: pending")
    print("No project files were changed.")
    print("\nTo review and apply it, run:")
    print(f"uv run main.py --apply {proposal_id}")


def apply_saved_proposal(proposal_id: str) -> None:
    """Show a proposal and require explicit human approval."""

    print("\n========== PROPOSAL REVIEW ==========\n")
    print(get_proposal_diff(proposal_id))
    print("\nThis operation will modify project files.")

    confirmation = input(
        "Type APPLY exactly to approve these changes: "
    )
    if confirmation != "APPLY":
        print("Approval was not provided. Nothing was changed.")
        return

    try:
        changed_files = apply_proposal(proposal_id)
    except Exception as error:
        print("The proposal could not be applied.")
        print(f"{type(error).__name__}: {error}")
        raise SystemExit(1) from error

    print("\nChanged files:")
    for file_path in changed_files:
        print(f"- {file_path}")

    print("\nRerunning the test suite...\n")
    reset_test_cache()
    test_output = run_python_tests()
    print(test_output)

    if "Pytest exit code: 0" in test_output:
        print("\nVerification successful: all tests passed.")
    else:
        print("\nSome tests are still failing.")
        print("To restore the original files, run:")
        print(f"uv run main.py --rollback {proposal_id}")


def rollback_saved_proposal(proposal_id: str) -> None:
    """Restore files from their Milestone 3 backups."""

    try:
        restored_files = rollback_proposal(proposal_id)
    except Exception as error:
        print("Rollback failed.")
        print(f"{type(error).__name__}: {error}")
        raise SystemExit(1) from error

    print("\nRestored files:")
    for file_path in restored_files:
        print(f"- {file_path}")
    print("\nRollback complete.")


def run_team_proposal_mode() -> None:
    """Run the corrected Milestone 4 multi-agent workflow."""

    print("\n========== TESTPILOT MULTI-AGENT WORKFLOW ==========\n")
    print("Python is collecting trusted project evidence...")
    print("No project files will be modified.\n")

    try:
        workflow_result = run_multi_agent_workflow(
            model=create_model(),
        )
    except KeyboardInterrupt:
        print("\nMilestone 4 workflow cancelled.")
        return
    except Exception as error:
        print("\nMilestone 4 could not complete:")
        print(f"{type(error).__name__}: {error}")
        print("No project files were changed.")
        raise SystemExit(1) from error

    if workflow_result.status == "no_failures":
        print("\n========== NO REPAIR NEEDED ==========\n")
        print(workflow_result.message)
        print("No proposal was saved.")
        print("No project files were changed.")
        return

    if workflow_result.status == "error":
        print("\n========== EVIDENCE COLLECTION ERROR ==========\n")
        print(workflow_result.message)
        print(workflow_result.evidence.pytest_output)
        print("No proposal was saved.")
        return

    repair_plan = workflow_result.repair_plan
    review = workflow_result.review_decision
    validation = workflow_result.validation_result

    if repair_plan is None or review is None or validation is None:
        raise SystemExit(
            "Milestone 4 returned an incomplete workflow result."
        )

    diagnostic_run_id = save_report(
        report=repair_plan.diagnostic,
        stop_reason=f"milestone-4-{workflow_result.status}",
    )

    if workflow_result.status == "rejected":
        print("\n========== WORKFLOW REJECTED ==========\n")
        print(review.summary)

        if validation.issues:
            print("\nPython validation issues:")
            for issue in validation.issues:
                print(f"- {issue}")

        if review.concerns:
            print("\nReviewer concerns:")
            for concern in review.concerns:
                print(f"- {concern}")

        if review.required_changes:
            print("\nRequired changes:")
            for required_change in review.required_changes:
                print(f"- {required_change}")

        print(f"\nDiagnostic run: #{diagnostic_run_id}")
        print("No proposal was saved.")
        print("No project files were changed.")
        return

    #Python validation and independent review approved the plan
    proposal_id = save_proposal(repair_plan)

    print("\n========== REVIEW APPROVED ==========\n")
    print(review.summary)
    print("\n========== VALIDATED DIFF ==========\n")
    print(workflow_result.proposed_diff)
    print("\n========== PENDING PROPOSAL ==========\n")
    print(f"Diagnostic run: #{diagnostic_run_id}")
    print(f"Proposal ID: {proposal_id}")
    print("Status: pending")
    print("No project files were changed.")
    print("\nTo review and apply it, run:")
    print(f"uv run main.py --apply {proposal_id}")


def main() -> None:
    """Run the requested TestPilot operation."""

    parser = argparse.ArgumentParser(description="TestPilot AI")
    operation = parser.add_mutually_exclusive_group()

    operation.add_argument(
        "--history",
        action="store_true",
        help="Display saved diagnostic runs.",
    )
    operation.add_argument(
        "--propose",
        action="store_true",
        help="Generate a single-agent repair proposal.",
    )
    operation.add_argument(
        "--team-propose",
        action="store_true",
        help="Run the Milestone 4 multi-agent workflow.",
    )
    operation.add_argument(
        "--apply",
        metavar="PROPOSAL_ID",
        help="Review and apply a saved proposal.",
    )
    operation.add_argument(
        "--rollback",
        metavar="PROPOSAL_ID",
        help="Restore files changed by a proposal.",
    )

    arguments = parser.parse_args()
    initialize_database()

    if arguments.history:
        display_history()
    elif arguments.propose:
        create_repair_proposal()
    elif arguments.team_propose:
        run_team_proposal_mode()
    elif arguments.apply:
        apply_saved_proposal(arguments.apply)
    elif arguments.rollback:
        rollback_saved_proposal(arguments.rollback)
    else:
        run_diagnostic()


if __name__ == "__main__":
    main()