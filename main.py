#Milestone 1: agent inspected code and ran tests

#Milestone 2: Code is divided into modules, report output follows a validated structure & reports are saved in SQLite
#agent is still read-only & can't edit project files

#Milestone 3: 

import sys
import argparse

from strands import Agent

from agent_tools import (
    list_project_files,
    read_project_file,
    reset_test_cache,
    run_python_tests,
)
from model import ( DiagnosticReport, RepairPlan, create_model,)
from storage import (
    DATABASE_PATH,
    initialize_database,
    list_recent_runs,
    save_report,
)

from proposal_manager import (apply_proposal, get_proposal_diff, rollback_proposal, save_proposal, )


SYSTEM_PROMPT = """
You are TestPilot AI, a read-only software testing and debugging agent.

Your job is to:
1. Inspect the available project files.
2. Read only the files that are relevant to the failure.
3. Run the Python tests exactly once.
4. Compare the test failures with the source code.
5. Distinguish source-code defects from incorrectly written tests.
6. Produce an evidence-backed structured diagnostic report.

Important rules:
- Never claim that you modified a file.
- Never claim that a suggested fix was applied.
- Never invent test results.
- Do not repeatedly call run_python_tests.
- Do not read .env, database files, virtual environments, or Git data.
- Stop after producing the structured report.
"""

PROPOSAL_TASK = """
Analyze this Python project and prepare an exact repair proposal.

Required process:
1. List the project files.
2. Read the relevant source and test files.
3. Run pytest exactly once.
4. Identify source-code defects and test defects.
5. Produce a RepairPlan containing exact replacements.

Rules:
- Do not claim that any file was modified.
- Do not use Markdown fences inside original_text or replacement_text.
- original_text must match the existing file exactly.
- Include enough surrounding text to make every replacement unique.
- Combine related changes when appropriate.
- Do not propose changes to TestPilot's infrastructure files.
- Only propose changes inside sample_app or its related tests.
- Stop after producing the RepairPlan.
"""

DIAGNOSTIC_TASK = """
Analyze this Python project.

First, list the project files.
Then read the relevant source code and test files.
Run pytest once.
Use the test output and source code to identify the root causes.

Return a structured TestPilot diagnostic report.
Proposed fixes must remain recommendations only.
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


def run_diagnostic() -> None:
    """Run one complete TestPilot diagnostic session."""

    print("\n========== TESTPILOT AI: MILESTONE 2 ==========\n")
    print("Starting a read-only diagnostic run...")
    print("The Gemini analysis may take several seconds.\n")

    #create the database table if necessary.
    initialize_database()

    #allow pytest to run once during this new session.
    reset_test_cache()

    model = create_model()

    agent = Agent(
        model=model,
        tools=[
            list_project_files,
            read_project_file,
            run_python_tests,
        ],
        system_prompt=SYSTEM_PROMPT,

        #prevent Strands from printing a second copy of the answer.
        callback_handler=None,
    )

    try:
        result = agent(
            DIAGNOSTIC_TASK,

            #forces Gemini's response into our Pydantic structure.
            structured_output_model=DiagnosticReport,

            #prevents an accidental endless tool loop.
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
        print("Gemini finished without producing a structured report.")
        raise SystemExit(1)

    run_id = save_report(
        report=report,
        stop_reason=str(result.stop_reason),
    )

    print("\n========== STRUCTURED TESTPILOT REPORT ==========\n")
    print(report.model_dump_json(indent=2))

    print("\n========== RUN INFORMATION ==========\n")
    print(f"Saved run: #{run_id}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Database: {DATABASE_PATH.name}")


def build_agent() -> Agent:
    """Create the read-only TestPilot agent."""

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


def create_repair_proposal() -> None:
    """Generate and save a repair proposal without applying it."""

    print("\n========== TESTPILOT REPAIR PROPOSAL ==========\n")
    print("Analyzing the project...")
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
        print("Gemini did not produce a repair plan.")
        raise SystemExit(1)

    #save the diagnostic part in Milestone 2's database
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

    #clear Milestone 2's test cache so this is a new test run
    reset_test_cache()
    test_output = run_python_tests()

    print(test_output)

    if "Pytest exit code: 0" in test_output:
        print("\nVerification successful: all tests passed.")
    else:
        print("\nSome tests are still failing.")
        print("Review the output carefully.")
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


def main() -> None:
    """Run the requested TestPilot operation."""

    parser = argparse.ArgumentParser(
        description="TestPilot AI"
    )

    operation = parser.add_mutually_exclusive_group()

    operation.add_argument(
        "--history",
        action="store_true",
        help="Display saved diagnostic runs.",
    )

    operation.add_argument(
        "--propose",
        action="store_true",
        help="Generate a safe repair proposal.",
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

    elif arguments.apply:
        apply_saved_proposal(arguments.apply)

    elif arguments.rollback:
        rollback_saved_proposal(arguments.rollback)

    else:
        #preserve Milestone 2's normal diagnostic mode.
        run_diagnostic()


if __name__ == "__main__":
    main()