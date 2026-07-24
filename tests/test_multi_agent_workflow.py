#tests for the grounded Milestone 4 multi-agent workflow

from pathlib import Path

import pytest

import multi_agent_workflow as workflow
from model import (
    DiagnosticReport,
    FileChange,
    InvestigationPlan,
    ProjectEvidence,
    RepairPlan,
    ReviewDecision,
)


class FakeAgent:
    """Return one prepared structured response and record the prompt."""

    def __init__(
        self,
        name: str,
        response,
        call_order: list[str],
    ):
        self.name = name
        self.response = response
        self.call_order = call_order
        self.received_prompt: str | None = None

    def structured_output(self, output_model, prompt):
        self.call_order.append(self.name)
        self.received_prompt = prompt
        assert isinstance(self.response, output_model)
        return self.response


def create_sample_project(project_root: Path) -> Path:
    """Create a real, failing Python project for a workflow test."""

    sample_app = project_root / "sample_app"
    tests_folder = project_root / "tests"
    sample_app.mkdir()
    tests_folder.mkdir()

    (sample_app / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    calculator = sample_app / "calculator.py"
    calculator.write_text(
        (
            "def divide(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )

    (tests_folder / "test_calculator.py").write_text(
        (
            "from sample_app.calculator import divide\n\n"
            "def test_divide():\n"
            "    assert divide(10, 2) == 5\n"
        ),
        encoding="utf-8",
    )
    return calculator


def make_evidence(
    project_root: Path,
    *,
    pytest_exit_code: int = 1,
) -> ProjectEvidence:
    """Create trusted evidence matching the sample project."""

    calculator = project_root / "sample_app" / "calculator.py"
    test_file = project_root / "tests" / "test_calculator.py"

    return ProjectEvidence(
        project_files=[
            "sample_app/__init__.py",
            "sample_app/calculator.py",
            "tests/test_calculator.py",
        ],
        pytest_exit_code=pytest_exit_code,
        pytest_output=(
            "FAILED tests/test_calculator.py::test_divide "
            "- assert 12 == 5"
            if pytest_exit_code != 0
            else "1 passed"
        ),
        file_contents={
            "sample_app/calculator.py": calculator.read_text(
                encoding="utf-8"
            ),
            "tests/test_calculator.py": test_file.read_text(
                encoding="utf-8"
            ),
        },
    )


def make_investigation_plan() -> InvestigationPlan:
    """Create an evidence-grounded planner response."""

    return InvestigationPlan(
        objective="Diagnose the failing divide test.",
        suspected_files=[
            "sample_app/calculator.py",
            "tests/test_calculator.py",
        ],
        investigation_steps=[
            "Compare divide() with test_divide().",
        ],
        tests_to_examine=[
            "tests/test_calculator.py::test_divide",
        ],
        evidence_used=[
            "FAILED tests/test_calculator.py::test_divide",
        ],
        risk="low",
    )


def make_repair_plan(
    path: str = "sample_app/calculator.py",
    original_text: str = "    return a + b",
) -> RepairPlan:
    """Create an exact debugger response."""

    diagnostic = DiagnosticReport(
        summary="divide() adds instead of dividing.",
        test_status="failed",
        problems=[
            "divide(10, 2) returns 12 instead of 5.",
        ],
        evidence=[
            "FAILED tests/test_calculator.py::test_divide",
        ],
        root_causes=[
            "divide() uses + instead of /.",
        ],
        proposed_fixes=[
            "Replace addition with division.",
        ],
        risk="low",
        tests_to_rerun=[
            "tests/test_calculator.py",
        ],
    )

    return RepairPlan(
        diagnostic=diagnostic,
        changes=[
            FileChange(
                file_path=path,
                reason="The failing test requires division.",
                original_text=original_text,
                replacement_text="    return a / b",
            )
        ],
    )


def make_approved_review() -> ReviewDecision:
    """Create an independent approval."""

    return ReviewDecision(
        approved=True,
        summary="The exact minimal repair is supported by pytest.",
        verified_changes=[
            "divide() changes from addition to division.",
        ],
        concerns=[],
        required_changes=[],
    )


def make_rejected_review() -> ReviewDecision:
    """Create an independent rejection."""

    return ReviewDecision(
        approved=False,
        summary="The proposed repair failed validation.",
        verified_changes=[],
        concerns=[
            "The proposed replacement is not grounded in the file.",
        ],
        required_changes=[
            "Use exact current source text.",
        ],
    )


def install_fake_agents(
    monkeypatch,
    repair_plan: RepairPlan,
    review: ReviewDecision,
) -> tuple[list[str], dict[str, FakeAgent]]:
    """Install predictable agents while retaining real orchestration."""

    call_order: list[str] = []
    agents = {
        "planner": FakeAgent(
            "planner",
            make_investigation_plan(),
            call_order,
        ),
        "debugger": FakeAgent(
            "debugger",
            repair_plan,
            call_order,
        ),
        "reviewer": FakeAgent(
            "reviewer",
            review,
            call_order,
        ),
    }

    monkeypatch.setattr(
        workflow,
        "create_planner_agent",
        lambda model: agents["planner"],
    )
    monkeypatch.setattr(
        workflow,
        "create_debugger_agent",
        lambda model: agents["debugger"],
    )
    monkeypatch.setattr(
        workflow,
        "create_reviewer_agent",
        lambda model: agents["reviewer"],
    )
    return call_order, agents


def test_collect_project_evidence_uses_real_files_and_pytest(
    tmp_path,
):
    """Python, rather than Gemini, collects the authoritative facts."""

    create_sample_project(tmp_path)
    evidence = workflow.collect_project_evidence(tmp_path)

    assert evidence.pytest_exit_code == 1
    assert (
        "tests/test_calculator.py::test_divide"
        in evidence.pytest_output
    )
    assert (
        evidence.file_contents["sample_app/calculator.py"]
        == "def divide(a, b):\n    return a + b\n"
    )


def test_no_failures_creates_no_agents_or_repair(
    tmp_path,
    monkeypatch,
):
    """Passing tests end cleanly instead of causing an invented defect."""

    calculator = create_sample_project(tmp_path)
    calculator.write_text(
        (
            "def divide(a, b):\n"
            "    return a / b\n"
        ),
        encoding="utf-8",
    )

    def unexpected_agent(_model):
        raise AssertionError("No agent should run when pytest passes.")

    monkeypatch.setattr(
        workflow,
        "create_planner_agent",
        unexpected_agent,
    )

    result = workflow.run_multi_agent_workflow(
        model=object(),
        project_root=tmp_path,
    )

    assert result.status == "no_failures"
    assert result.repair_plan is None
    assert result.review_decision is None


def test_valid_workflow_is_grounded_and_read_only(
    tmp_path,
    monkeypatch,
):
    """All three agents receive trusted evidence and files stay unchanged."""

    calculator = create_sample_project(tmp_path)
    original_file = calculator.read_text(encoding="utf-8")
    evidence = make_evidence(tmp_path)
    monkeypatch.setattr(
        workflow,
        "collect_project_evidence",
        lambda project_root: evidence,
    )
    call_order, agents = install_fake_agents(
        monkeypatch,
        make_repair_plan(),
        make_approved_review(),
    )

    result = workflow.run_multi_agent_workflow(
        model=object(),
        project_root=tmp_path,
    )

    assert call_order == ["planner", "debugger", "reviewer"]
    assert result.status == "approved"
    assert result.validation_result is not None
    assert result.validation_result.valid is True
    assert "return a / b" in result.proposed_diff
    assert calculator.read_text(encoding="utf-8") == original_file

    planner_prompt = agents["planner"].received_prompt or ""
    debugger_prompt = agents["debugger"].received_prompt or ""
    reviewer_prompt = agents["reviewer"].received_prompt or ""

    assert "pytest_exit_code" in planner_prompt
    assert "return a + b" in debugger_prompt
    assert '"valid": true' in reviewer_prompt


def test_invalid_original_text_still_reaches_reviewer(
    tmp_path,
    monkeypatch,
):
    """Validation issues become reviewer input instead of an exception."""

    calculator = create_sample_project(tmp_path)
    original_file = calculator.read_text(encoding="utf-8")
    evidence = make_evidence(tmp_path)
    monkeypatch.setattr(
        workflow,
        "collect_project_evidence",
        lambda project_root: evidence,
    )
    call_order, agents = install_fake_agents(
        monkeypatch,
        make_repair_plan(original_text="    return a - b"),
        make_rejected_review(),
    )

    result = workflow.run_multi_agent_workflow(
        model=object(),
        project_root=tmp_path,
    )

    assert call_order == ["planner", "debugger", "reviewer"]
    assert result.status == "rejected"
    assert result.validation_result is not None
    assert result.validation_result.valid is False
    assert any(
        "was not found exactly" in issue
        for issue in result.validation_result.issues
    )
    assert '"valid": false' in (
        agents["reviewer"].received_prompt or ""
    )
    assert calculator.read_text(encoding="utf-8") == original_file


def test_hallucinated_path_is_reviewed_and_rejected(
    tmp_path,
    monkeypatch,
):
    """A nonexistent path cannot bypass Python or skip review."""

    create_sample_project(tmp_path)
    evidence = make_evidence(tmp_path)
    monkeypatch.setattr(
        workflow,
        "collect_project_evidence",
        lambda project_root: evidence,
    )
    call_order, _ = install_fake_agents(
        monkeypatch,
        make_repair_plan(path="src/core.py"),
        make_approved_review(),
    )

    result = workflow.run_multi_agent_workflow(
        model=object(),
        project_root=tmp_path,
    )

    assert call_order == ["planner", "debugger", "reviewer"]
    assert result.status == "rejected"
    assert result.review_decision is not None
    assert result.review_decision.approved is False
    assert any(
        "outside sample_app/ or tests/" in issue
        for issue in result.validation_result.issues
    )


def test_duplicate_original_text_is_rejected(
    tmp_path,
):
    """An ambiguous replacement cannot become a valid diff."""

    calculator = create_sample_project(tmp_path)
    calculator.write_text(
        (
            "def first(a, b):\n"
            "    return a + b\n\n"
            "def second(a, b):\n"
            "    return a + b\n"
        ),
        encoding="utf-8",
    )
    evidence = make_evidence(tmp_path)

    validation = workflow.validate_repair_plan(
        make_repair_plan(),
        evidence,
        tmp_path,
    )

    assert validation.valid is False
    assert any(
        "appears more than once" in issue
        for issue in validation.issues
    )


def test_protected_testpilot_file_is_rejected(
    tmp_path,
):
    """The workflow cannot rewrite its own Milestone 4 safety test."""

    create_sample_project(tmp_path)
    protected = tmp_path / "tests" / "test_multi_agent_workflow.py"
    protected.write_text(
        "    return a + b\n",
        encoding="utf-8",
    )
    evidence = make_evidence(tmp_path)
    evidence.project_files.append(
        "tests/test_multi_agent_workflow.py"
    )
    evidence.file_contents[
        "tests/test_multi_agent_workflow.py"
    ] = protected.read_text(encoding="utf-8")

    validation = workflow.validate_repair_plan(
        make_repair_plan(
            path="tests/test_multi_agent_workflow.py"
        ),
        evidence,
        tmp_path,
    )

    assert validation.valid is False
    assert any(
        "protected" in issue
        for issue in validation.issues
    )


def test_contradictory_approval_is_forced_to_rejection(
    tmp_path,
    monkeypatch,
):
    """Python rejects an approval containing unresolved concerns."""

    create_sample_project(tmp_path)
    evidence = make_evidence(tmp_path)
    monkeypatch.setattr(
        workflow,
        "collect_project_evidence",
        lambda project_root: evidence,
    )
    contradictory = ReviewDecision(
        approved=True,
        summary="Approved, but evidence remains incomplete.",
        verified_changes=[
            "divide() changes to division.",
        ],
        concerns=[
            "The evidence is incomplete.",
        ],
        required_changes=[],
    )
    install_fake_agents(
        monkeypatch,
        make_repair_plan(),
        contradictory,
    )

    result = workflow.run_multi_agent_workflow(
        model=object(),
        project_root=tmp_path,
    )

    assert result.status == "rejected"
    assert result.review_decision is not None
    assert result.review_decision.approved is False