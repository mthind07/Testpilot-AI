#Milestone 6: dashboard for operating TestPilot AI
#dashboard is only an interface, workflow.py still runs the Milestone 5 agent workflow, proposal_manager.py still applies and rolls back proposals & no source file changes without an exact APPLY confirmation


from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

#Milestone 1 tool: runs pytest and returns trusted terminal evidence
from agent_tools import execute_python_tests

#Milestone 4 constant: points to the root folder of this TestPilot project
from multi_agent_workflow import PROJECT_ROOT

#Milestone 3 safety functions: proposals are reviewed before changing code
from proposal_manager import (
    PROPOSAL_ID_PATTERN,
    apply_proposal,
    get_proposal_diff,
    load_proposal,
    rollback_proposal,
)

#Milestone 2 storage functions: save and display diagnostic history
from storage import initialize_database, list_recent_runs

#Milestone 5 entry point: runs the complete agent workflow
from workflow import run_workflow


def run_test_suite(
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    """Run pytest without calling Gemini."""

    #it does not use AI and cannot modify project files
    exit_code, output = execute_python_tests(project_root)

    #convert the result into named values that the dashboard can display
    return {
        "exit_code": exit_code,
        "passed": exit_code == 0,
        "output": output,
    }


def list_saved_proposals(
    project_root: Path = PROJECT_ROOT,
) -> list[dict[str, str]]:
    """Return safe proposal metadata for the dashboard selector."""

    #Milestone 3 stores one JSON file per proposal in this folder
    proposal_directory = project_root / ".testpilot_proposals"

    if not proposal_directory.exists():
        return []

    proposals: list[dict[str, str]] = []

    for proposal_file in proposal_directory.glob("proposal-*.json"):
        proposal_id = proposal_file.stem

        #ignore filenames that are not valid TestPilot proposal IDs
        if not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
            continue

        try:
            envelope = json.loads(
                proposal_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            #1 damaged proposal should not crash the dashboard
            continue

        #only expose the small amount of information needed by the UI
        diagnostic = envelope.get("plan", {}).get("diagnostic", {})

        proposals.append(
            {
                "proposal_id": proposal_id,
                "status": str(envelope.get("status", "unknown")),
                "created_at": str(envelope.get("created_at", "")),
                "summary": str(
                    diagnostic.get(
                        "summary",
                        "No summary available.",
                    )
                ),
                "risk": str(
                    diagnostic.get("risk", "unknown")
                ),
            }
        )

    #display the newest proposals first
    return sorted(
        proposals,
        key=lambda proposal: proposal["created_at"],
        reverse=True,
    )


def apply_from_dashboard(
    proposal_id: str,
    confirmation: str,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    """Apply a proposal only when the user types APPLY exactly."""

    #lowercase or incomplete confirmation is rejected
    if confirmation != "APPLY":
        raise ValueError(
            "Type APPLY exactly to approve this proposal."
        )

    #proposal_manager creates backups before changing project files
    changed_files = apply_proposal(
        proposal_id,
        project_root=project_root,
    )

    #always rerun pytest after an applied repair
    return {
        "action": "applied",
        "proposal_id": proposal_id,
        "files": changed_files,
        "test_result": run_test_suite(project_root),
    }


def rollback_from_dashboard(
    proposal_id: str,
    confirmation: str,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    """Restore a backup only when ROLLBACK is typed exactly."""

    #rollback has a separate confirmation so it cannot happen accidentally
    if confirmation != "ROLLBACK":
        raise ValueError(
            "Type ROLLBACK exactly to restore the backup."
        )

    #restore the backup created when the proposal was applied
    restored_files = rollback_proposal(
        proposal_id,
        project_root=project_root,
    )

    #rerun pytest after restoring the files too
    return {
        "action": "rolled_back",
        "proposal_id": proposal_id,
        "files": restored_files,
        "test_result": run_test_suite(project_root),
    }


def show_test_result(result: dict[str, object]) -> None:
    """Display one pytest result."""

    #exit code 0 means pytest passed
    if result["passed"]:
        st.success("All tests passed.")
    else:
        st.error(
            f"Pytest finished with exit code "
            f"{result['exit_code']}."
        )

    #display the complete pytest terminal output
    st.code(
        str(result["output"]) or "Pytest produced no output.",
        language="text",
    )


def show_workflow_outcome(
    outcome: dict[str, object],
) -> None:
    """Display the dictionary returned by Milestone 5."""

    status = str(outcome["status"])

    #translate the workflow status into a clear dashboard message
    if status in {"approved", "no_failures"}:
        st.success(str(outcome["message"]))
    elif status == "rejected":
        st.warning(str(outcome["message"]))
    else:
        st.error(str(outcome["message"]))

    #show the main workflow information side by side
    status_column, run_column = st.columns(2)

    status_column.metric(
        "Workflow status",
        status,
    )

    run_column.metric(
        "Diagnostic run",
        str(
            outcome.get("diagnostic_run_id")
            or "Not saved"
        ),
    )

    #explain why validation or review rejected a proposed repair
    for heading, key in [
        (
            "Python validation issues",
            "validation_issues",
        ),
        (
            "Reviewer concerns",
            "reviewer_concerns",
        ),
    ]:
        items = outcome.get(key, [])

        if items:
            st.subheader(heading)

            for item in items:
                st.write(f"- {item}")

    #displaying it does not modify project files
    if outcome.get("proposed_diff"):
        st.subheader("Validated diff")

        st.code(
            str(outcome["proposed_diff"]),
            language="diff",
        )

    #does not automatically modify the source code
    if outcome.get("proposal_id"):
        st.subheader("Pending proposal")

        st.code(
            str(outcome["proposal_id"]),
            language="text",
        )

        st.info(
            "Open the Proposals tab to review it. "
            "No code changed yet."
        )


def main() -> None:
    """Create the Streamlit dashboard."""

    #this must be the first Streamlit command in the app
    st.set_page_config(
        page_title="TestPilot AI",
        page_icon="🧪",
        layout="wide",
    )

    #make sure the Milestone 2 SQLite database tables exist
    initialize_database()

    st.title("TestPilot AI")

    st.caption(
        "Agentic software testing and debugging control centre"
    )

    st.info(
        "TestPilot analyzes first. It changes source files only "
        "after you review a validated diff and type APPLY exactly."
    )

    #load information for the three summary cards
    recent_runs = list_recent_runs(limit=20)
    proposals = list_saved_proposals()

    first, second, third = st.columns(3)

    first.metric(
        "Saved runs",
        len(recent_runs),
    )

    second.metric(
        "Pending proposals",
        sum(
            proposal["status"] == "pending"
            for proposal in proposals
        ),
    )

    third.metric(
        "Gemini key",
        (
            "Configured"
            if os.environ.get("GEMINI_API_KEY")
            else "Missing"
        ),
    )

    #divide the dashboard into three main sections
    run_tab, proposal_tab, history_tab = st.tabs(
        [
            "Run TestPilot",
            "Proposals",
            "History",
        ]
    )

    #RUN TESTPILOT TAB

    with run_tab:
        st.header("Run TestPilot")

        st.write(
            "Use the quick check for pytest only. "
            "Use the full workflow for planner → debugger → "
            "validator → reviewer."
        )

        test_column, workflow_column = st.columns(2)

        with test_column:
            if st.button("Run tests only"):
                with st.spinner("Running pytest..."):
                    #session State preserves the result when the page refreshes
                    st.session_state["test_result"] = (
                        run_test_suite()
                    )

        with workflow_column:
            if st.button(
                "Run full TestPilot workflow",
                type="primary",
            ):
                try:
                    with st.spinner(
                        "Running the TestPilot agent team..."
                    ):
                        # planner -> debugger -> validator -> reviewer
                        st.session_state["workflow_outcome"] = (
                            run_workflow()
                        )

                except Exception as error:
                    #display the error instead of crashing the page
                    st.error(
                        f"{type(error).__name__}: {error}"
                    )

        #redisplay the latest pytest result after Streamlit refreshes
        if st.session_state.get("test_result"):
            st.subheader("Latest test run")

            show_test_result(
                st.session_state["test_result"]
            )

        #redisplay the latest agent workflow result
        if st.session_state.get("workflow_outcome"):
            st.subheader("Latest TestPilot workflow")

            show_workflow_outcome(
                st.session_state["workflow_outcome"]
            )

    #PROPOSALS TAB

    with proposal_tab:
        st.header("Review proposals")

        #reload proposals so newly created proposals appear immediately
        proposals = list_saved_proposals()

        if not proposals:
            st.info(
                "No proposals exist. A failing test and an "
                "approved TestPilot workflow are required first."
            )

        else:
            #create readable labels for the proposal selector
            labels = {
                (
                    f"{proposal['proposal_id']} "
                    f"({proposal['status']})"
                ): proposal["proposal_id"]
                for proposal in proposals
            }

            selected_label = st.selectbox(
                "Select a proposal",
                options=list(labels),
            )

            proposal_id = labels[selected_label]

            #read the complete proposal only after it is selected
            plan, envelope = load_proposal(proposal_id)

            status_column, risk_column = st.columns(2)

            status_column.metric(
                "Status",
                str(envelope["status"]),
            )

            risk_column.metric(
                "Risk",
                plan.diagnostic.risk,
            )

            st.write(plan.diagnostic.summary)

            st.subheader("Validated diff")

            st.code(
                get_proposal_diff(proposal_id),
                language="diff",
            )

            #display the latest APPLY or ROLLBACK result
            previous_action = st.session_state.get(
                "proposal_action"
            )

            if (
                previous_action
                and previous_action["proposal_id"]
                == proposal_id
            ):
                action_name = previous_action["action"]

                if action_name == "applied":
                    st.success(
                        "The proposal was applied."
                    )
                else:
                    st.warning(
                        "The proposal was rolled back."
                    )

                st.write("Affected files:")

                for file_path in previous_action["files"]:
                    st.write(f"- {file_path}")

                show_test_result(
                    previous_action["test_result"]
                )

            #pending proposal may be applied after human approval
            if envelope["status"] == "pending":
                st.warning(
                    "Applying creates a backup, changes the files "
                    "in the diff, and reruns pytest."
                )

                confirmation = st.text_input(
                    "Type APPLY exactly",
                    key=f"apply-{proposal_id}",
                )

                if st.button(
                    "Apply proposal",
                    type="primary",
                ):
                    try:
                        with st.spinner(
                            "Applying and testing..."
                        ):
                            #this is the dashboard's only apply path
                            result = apply_from_dashboard(
                                proposal_id,
                                confirmation,
                            )

                        st.session_state[
                            "proposal_action"
                        ] = result

                        #refresh pending -> applied
                        st.rerun()

                    except Exception as error:
                        st.error(
                            f"{type(error).__name__}: "
                            f"{error}"
                        )

            #applied proposal may be rolled back if the repair was bad
            elif envelope["status"] == "applied":
                st.warning(
                    "Do not roll back when the repair passes. "
                    "Rollback is only for recovering from a bad "
                    "applied repair."
                )

                confirmation = st.text_input(
                    "Type ROLLBACK exactly",
                    key=f"rollback-{proposal_id}",
                )

                if st.button("Rollback proposal"):
                    try:
                        with st.spinner(
                            "Restoring the backup..."
                        ):
                            #only use this when an applied repair was bad
                            result = rollback_from_dashboard(
                                proposal_id,
                                confirmation,
                            )

                        st.session_state[
                            "proposal_action"
                        ] = result

                        #refresh applied -> rolled_back
                        st.rerun()

                    except Exception as error:
                        st.error(
                            f"{type(error).__name__}: "
                            f"{error}"
                        )

            else:
                st.info(
                    "This proposal has already been rolled back."
                )

    #HISTORY TAB

    with history_tab:
        st.header("Diagnostic history")

        #read the newest 20 Milestone 2 diagnostic records
        recent_runs = list_recent_runs(limit=20)

        if recent_runs:
            st.dataframe(
                recent_runs,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info(
                "No diagnostic runs have been saved yet."
            )


#start the dashboard when Streamlit runs this file
if __name__ == "__main__":
    main()