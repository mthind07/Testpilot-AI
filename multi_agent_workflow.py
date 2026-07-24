#python collects the project evidence and validates every proposed change.


import difflib
from pathlib import Path
from typing import Any

from strands import Agent

from agent_tools import (
    collect_project_files,
    execute_python_tests,
    read_project_text,
)
from model import (
    InvestigationPlan,
    MultiAgentWorkflowResult,
    ProjectEvidence,
    RepairPlan,
    ReviewDecision,
    ValidationResult,
)


PROJECT_ROOT = Path(__file__).resolve().parent

#these match Milestone 3's deliberately narrow editing policy
ALLOWED_TOP_LEVEL_FOLDERS = {
    "sample_app",
    "tests",
}

PROTECTED_PROJECT_FILES = {
    "tests/test_proposals.py",
    "tests/test_storage.py",
    "tests/test_multi_agent_workflow.py",
}

#prevent a large repository from creating an enormous model prompt
MAX_FILE_CONTEXT_CHARACTERS = 80_000


PLANNER_SYSTEM_PROMPT = """
You are TestPilot AI's planning agent.

Python has already collected an authoritative evidence packet containing:
- the files that really exist;
- the exact pytest exit code and output;
- exact contents of the editable Python files.

Create an InvestigationPlan using only that packet.

Rules:
- Do not invent files, failures, test results, or source code.
- Every suspected file must appear in project_files.
- Every test must appear in project_files or in the pytest node IDs.
- evidence_used must identify concrete lines from pytest_output.
- Do not propose exact code replacements yet.
- You are read-only and cannot modify files.
"""


DEBUGGER_SYSTEM_PROMPT = """
You are TestPilot AI's debugging agent.

Use only the authoritative evidence packet and InvestigationPlan supplied
by Python. Produce the smallest evidence-backed RepairPlan.

Rules:
- Do not invent files, failures, test results, or source code.
- Every file_path must be a key in file_contents.
- original_text must be copied character-for-character from file_contents.
- Include enough surrounding text to make original_text unique.
- replacement_text must contain only the intended correction.
- Keep the repair minimal and related to a real pytest failure.
- Do not modify any files.

RepairPlan must contain:
- diagnostic: a complete DiagnosticReport;
- changes: one or more exact FileChange objects.
"""


REVIEWER_SYSTEM_PROMPT = """
You are TestPilot AI's independent review agent.

Review the evidence, investigation, repair, deterministic ValidationResult,
and proposed diff. Python validation is authoritative.

Rules:
- If validation.valid is false, you must reject the repair.
- Reject changes unsupported by the pytest evidence.
- Reject unnecessary, unsafe, broad, or unrelated changes.
- Approve only a minimal repair with tests capable of verifying it.
- Put every blocking problem in concerns or required_changes.
- You are read-only and cannot modify files.
"""


def create_planner_agent(model: Any) -> Agent:
    """Create the evidence-grounded planning agent."""

    return Agent(
        model=model,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        callback_handler=None,
    )


def create_debugger_agent(model: Any) -> Agent:
    """Create the evidence-grounded debugging agent."""

    return Agent(
        model=model,
        system_prompt=DEBUGGER_SYSTEM_PROMPT,
        callback_handler=None,
    )


def create_reviewer_agent(model: Any) -> Agent:
    """Create the independent review agent."""

    return Agent(
        model=model,
        system_prompt=REVIEWER_SYSTEM_PROMPT,
        callback_handler=None,
    )


def collect_project_evidence(
    project_root: Path = PROJECT_ROOT,
) -> ProjectEvidence:
    """Collect real files, contents, and pytest output before AI runs."""

    root = project_root.resolve()
    project_files = collect_project_files(root)
    pytest_exit_code, pytest_output = execute_python_tests(root)

    file_contents: dict[str, str] = {}
    used_characters = 0

    for relative_path_text in project_files:
        relative_path = Path(relative_path_text)

        if not relative_path.parts:
            continue
        if relative_path.parts[0] not in ALLOWED_TOP_LEVEL_FOLDERS:
            continue
        if relative_path.suffix != ".py":
            continue
        if relative_path_text in PROTECTED_PROJECT_FILES:
            continue

        try:
            content = read_project_text(relative_path_text, root)
        except (FileNotFoundError, UnicodeDecodeError, ValueError):
            continue

        if (
            used_characters + len(content)
            > MAX_FILE_CONTEXT_CHARACTERS
        ):
            continue

        file_contents[relative_path_text] = content
        used_characters += len(content)

    return ProjectEvidence(
        project_files=project_files,
        pytest_exit_code=pytest_exit_code,
        pytest_output=pytest_output,
        file_contents=file_contents,
    )


def _safe_change_target(
    path_text: str,
    project_root: Path,
) -> Path:
    """Resolve one proposed path and enforce Milestone 3's policy."""

    root = project_root.resolve()
    relative_path = Path(path_text)

    if relative_path.is_absolute():
        raise ValueError(
            f"Absolute paths are not allowed: {path_text}"
        )
    if ".." in relative_path.parts:
        raise ValueError(
            f"Path traversal is not allowed: {path_text}"
        )
    if not relative_path.parts:
        raise ValueError("The proposed path is empty.")
    if relative_path.parts[0] not in ALLOWED_TOP_LEVEL_FOLDERS:
        raise ValueError(
            "Changes are not allowed outside sample_app/ or tests/: "
            f"{path_text}"
        )

    normalized_path = relative_path.as_posix()
    if normalized_path in PROTECTED_PROJECT_FILES:
        raise ValueError(
            f"TestPilot safety file is protected: {path_text}"
        )

    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(
            f"Path escapes the project root: {path_text}"
        )
    if target.suffix != ".py":
        raise ValueError(
            f"Only Python files may be changed: {path_text}"
        )
    if not target.exists() or not target.is_file():
        raise ValueError(
            f"Proposed file does not exist: {path_text}"
        )

    return target


def validate_repair_plan(
    repair_plan: RepairPlan,
    evidence: ProjectEvidence,
    project_root: Path = PROJECT_ROOT,
) -> ValidationResult:
    """Validate all changes and build an in-memory diff.

    Unlike the previous version, this function returns validation issues
    instead of aborting the workflow before the reviewer can run.
    """

    root = project_root.resolve()
    issues: list[str] = []
    original_files: dict[Path, str] = {}
    updated_files: dict[Path, str] = {}

    if evidence.pytest_exit_code == 0:
        issues.append(
            "Pytest passed, so there is no failing test to repair."
        )

    if repair_plan.diagnostic.test_status == "passed":
        issues.append(
            "The debugger reported passing tests while proposing a repair."
        )

    if not repair_plan.diagnostic.evidence:
        issues.append(
            "The diagnostic contains no test evidence."
        )

    if not repair_plan.diagnostic.tests_to_rerun:
        issues.append(
            "The diagnostic does not identify tests to rerun."
        )

    for test_path in repair_plan.diagnostic.tests_to_rerun:
        file_part = test_path.split("::", 1)[0]
        if file_part not in evidence.project_files:
            issues.append(
                f"Test to rerun does not exist: {test_path}"
            )

    for index, change in enumerate(repair_plan.changes, start=1):
        try:
            target = _safe_change_target(
                change.file_path,
                root,
            )
        except ValueError as error:
            issues.append(f"Change #{index}: {error}")
            continue

        relative_path = target.relative_to(root).as_posix()
        supplied_content = evidence.file_contents.get(relative_path)
        if supplied_content is None:
            issues.append(
                f"Change #{index}: no trusted file snapshot exists for "
                f"{relative_path}."
            )
            continue

        if target not in original_files:
            current_disk_content = target.read_text(encoding="utf-8")
            if current_disk_content != supplied_content:
                issues.append(
                    f"Change #{index}: {relative_path} changed after "
                    "evidence collection."
                )
                continue

            original_files[target] = supplied_content
            updated_files[target] = supplied_content

        current_content = updated_files[target]

        if change.original_text == change.replacement_text:
            issues.append(
                f"Change #{index}: original_text and replacement_text "
                f"are identical in {relative_path}."
            )
            continue

        match_count = current_content.count(change.original_text)
        if match_count == 0:
            issues.append(
                f"Change #{index}: original_text was not found exactly "
                f"in {relative_path}."
            )
            continue
        if match_count > 1:
            issues.append(
                f"Change #{index}: original_text appears more than once "
                f"in {relative_path}."
            )
            continue

        updated_files[target] = current_content.replace(
            change.original_text,
            change.replacement_text,
            1,
        )

    diff_sections: list[str] = []
    for target, original_content in original_files.items():
        updated_content = updated_files[target]
        if original_content == updated_content:
            continue

        relative_path = target.relative_to(root).as_posix()
        difference = difflib.unified_diff(
            original_content.splitlines(),
            updated_content.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
        section = "\n".join(difference)
        if section:
            diff_sections.append(section)

    proposed_diff = "\n\n".join(diff_sections)
    if not proposed_diff:
        issues.append(
            "The RepairPlan did not produce a validated file difference."
        )

    return ValidationResult(
        valid=not issues,
        issues=issues,
        proposed_diff=proposed_diff,
    )


def build_review_diff(
    repair_plan: RepairPlan,
    project_root: Path = PROJECT_ROOT,
    evidence: ProjectEvidence | None = None,
) -> str:
    """Compatibility wrapper that returns a diff or raises ValueError."""

    trusted_evidence = evidence or collect_project_evidence(project_root)
    validation = validate_repair_plan(
        repair_plan,
        trusted_evidence,
        project_root,
    )
    if not validation.valid:
        raise ValueError("; ".join(validation.issues))
    return validation.proposed_diff


def _force_safe_review(
    review: ReviewDecision,
    validation: ValidationResult,
) -> ReviewDecision:
    """Make Python the final authority over an AI review decision."""

    blocking_concerns = list(review.concerns)
    required_changes = list(review.required_changes)

    if not validation.valid:
        for issue in validation.issues:
            if issue not in blocking_concerns:
                blocking_concerns.append(issue)

    if not review.verified_changes:
        missing_verification = (
            "The reviewer did not verify any proposed changes."
        )
        if missing_verification not in blocking_concerns:
            blocking_concerns.append(missing_verification)

    approved = review.approved
    if (
        not validation.valid
        or blocking_concerns
        or required_changes
        or not review.verified_changes
    ):
        approved = False

    if approved == review.approved and (
        blocking_concerns == review.concerns
        and required_changes == review.required_changes
    ):
        return review

    summary = review.summary
    if review.approved and not approved:
        summary = (
            "TestPilot rejected the repair because deterministic "
            "validation or reviewer concerns remain unresolved."
        )

    return review.model_copy(
        update={
            "approved": approved,
            "summary": summary,
            "concerns": blocking_concerns,
            "required_changes": required_changes,
        }
    )


def run_multi_agent_workflow(
    model: Any,
    project_root: Path = PROJECT_ROOT,
) -> MultiAgentWorkflowResult:
    """Run one grounded planner-debugger-reviewer workflow."""

    evidence = collect_project_evidence(project_root)

    print("\n========== TRUSTED PROJECT EVIDENCE ==========\n")
    print(f"Readable files: {len(evidence.project_files)}")
    print(f"Pytest exit code: {evidence.pytest_exit_code}")
    print(evidence.pytest_output)

    #debugging agent must never invent a failure when pytest passes
    if evidence.pytest_exit_code == 0:
        return MultiAgentWorkflowResult(
            status="no_failures",
            message=(
                "Pytest passed. TestPilot correctly created no repair "
                "proposal."
            ),
            evidence=evidence,
        )

    if evidence.pytest_exit_code in {5, 124, 125}:
        return MultiAgentWorkflowResult(
            status="error",
            message=(
                "TestPilot could not obtain a usable failing-test run. "
                "Review the pytest output."
            ),
            evidence=evidence,
        )

    evidence_json = evidence.model_dump_json(indent=2)

    print("\n========== PLANNER AGENT ==========\n")
    planner = create_planner_agent(model)
    investigation_plan = planner.structured_output(
        InvestigationPlan,
        (
            "Create an investigation plan from this authoritative "
            f"evidence packet:\n\n{evidence_json}"
        ),
    )
    print(investigation_plan.model_dump_json(indent=2))

    print("\n========== DEBUGGER AGENT ==========\n")
    debugger = create_debugger_agent(model)
    repair_plan = debugger.structured_output(
        RepairPlan,
        (
            "Create an exact RepairPlan from the authoritative evidence "
            "and planner output below.\n\n"
            f"EVIDENCE:\n{evidence_json}\n\n"
            "INVESTIGATION PLAN:\n"
            f"{investigation_plan.model_dump_json(indent=2)}"
        ),
    )
    print(repair_plan.model_dump_json(indent=2))

    validation = validate_repair_plan(
        repair_plan,
        evidence,
        project_root,
    )

    print("\n========== PYTHON VALIDATION ==========\n")
    print(validation.model_dump_json(indent=2))

    print("\n========== REVIEWER AGENT ==========\n")
    reviewer = create_reviewer_agent(model)
    review = reviewer.structured_output(
        ReviewDecision,
        (
            "Review the complete workflow record below.\n\n"
            f"EVIDENCE:\n{evidence_json}\n\n"
            "INVESTIGATION PLAN:\n"
            f"{investigation_plan.model_dump_json(indent=2)}\n\n"
            "REPAIR PLAN:\n"
            f"{repair_plan.model_dump_json(indent=2)}\n\n"
            "PYTHON VALIDATION:\n"
            f"{validation.model_dump_json(indent=2)}"
        ),
    )
    review = _force_safe_review(review, validation)
    print(review.model_dump_json(indent=2))

    status = (
        "approved"
        if validation.valid and review.approved
        else "rejected"
    )
    message = (
        "The repair passed Python validation and independent review."
        if status == "approved"
        else "The repair was rejected safely. No proposal was saved."
    )

    return MultiAgentWorkflowResult(
        status=status,
        message=message,
        evidence=evidence,
        investigation_plan=investigation_plan,
        repair_plan=repair_plan,
        validation_result=validation,
        review_decision=review,
        proposed_diff=validation.proposed_diff,
    )