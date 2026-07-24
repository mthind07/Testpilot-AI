#Gemini configuration and validated TestPilot data models

import os
from typing import Literal

from pydantic import BaseModel, Field
from strands.models.gemini import GeminiModel


class DiagnosticReport(BaseModel):
    """Evidence-backed report produced by TestPilot."""

    summary: str = Field(
        description="A short summary of the testing results."
    )
    test_status: Literal["passed", "failed", "error"] = Field(
        description="Overall status of the test run."
    )
    problems: list[str] = Field(
        description="Problems discovered in the source code or tests."
    )
    evidence: list[str] = Field(
        description="Test failures, file locations, and supporting evidence."
    )
    root_causes: list[str] = Field(
        description="Likely technical causes of the discovered problems."
    )
    proposed_fixes: list[str] = Field(
        description="Recommended changes. These are suggestions only."
    )
    risk: Literal["low", "medium", "high"] = Field(
        description="Estimated risk of applying the proposed changes."
    )
    tests_to_rerun: list[str] = Field(
        description="Tests that should be rerun after correction."
    )


class FileChange(BaseModel):
    """One exact change proposed for a project file."""

    file_path: str = Field(
        description="Path to the file relative to the project root."
    )
    reason: str = Field(
        description="Why this change is necessary."
    )
    original_text: str = Field(
        min_length=1,
        description=(
            "Exact text currently inside the file. "
            "It must match the file exactly."
        ),
    )
    replacement_text: str = Field(
        description="Text that should replace original_text."
    )


class RepairPlan(BaseModel):
    """A structured repair plan that requires human approval."""

    diagnostic: DiagnosticReport = Field(
        description="The diagnostic report supporting these changes."
    )
    changes: list[FileChange] = Field(
        min_length=1,
        description="Exact proposed file changes."
    )


class ProjectEvidence(BaseModel):
    """Facts collected by Python before any agent is called."""

    project_files: list[str] = Field(
        description="Readable files that actually exist in the project."
    )
    pytest_exit_code: int = Field(
        description="Exit code returned by pytest."
    )
    pytest_output: str = Field(
        description="Captured stdout and stderr from pytest."
    )
    file_contents: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Exact contents of editable Python files supplied to the agents."
        ),
    )


class InvestigationPlan(BaseModel):
    """Plan created by TestPilot's planner agent."""

    objective: str = Field(
        description="The main problem the debugger should investigate."
    )
    suspected_files: list[str] = Field(
        default_factory=list,
        description="Existing project files connected to the failures."
    )
    investigation_steps: list[str] = Field(
        default_factory=list,
        description="Ordered steps the debugger should follow."
    )
    tests_to_examine: list[str] = Field(
        default_factory=list,
        description="Existing tests related to the suspected problem."
    )
    evidence_used: list[str] = Field(
        default_factory=list,
        description="Specific pytest evidence used to create the plan."
    )
    risk: Literal["low", "medium", "high"] = Field(
        description="Estimated risk of the investigation."
    )


class ValidationResult(BaseModel):
    """Deterministic Python validation of a debugger repair plan."""

    valid: bool = Field(
        description="Whether every proposed change passed validation."
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Blocking safety or accuracy problems."
    )
    proposed_diff: str = Field(
        default="",
        description="Validated diff preview. No file is changed."
    )


class ReviewDecision(BaseModel):
    """Safety decision created by TestPilot's reviewer agent."""

    approved: bool = Field(
        description="Whether the repair is safe enough to save."
    )
    summary: str = Field(
        description="Short explanation of the review decision."
    )
    verified_changes: list[str] = Field(
        default_factory=list,
        description="Changes supported by the supplied evidence."
    )
    concerns: list[str] = Field(
        default_factory=list,
        description="Unsafe, unsupported, or unnecessary changes."
    )
    required_changes: list[str] = Field(
        default_factory=list,
        description="Corrections needed before approval."
    )


class MultiAgentWorkflowResult(BaseModel):
    """Complete result of one Milestone 4 workflow."""

    status: Literal["no_failures", "approved", "rejected", "error"]
    message: str
    evidence: ProjectEvidence
    investigation_plan: InvestigationPlan | None = None
    repair_plan: RepairPlan | None = None
    validation_result: ValidationResult | None = None
    review_decision: ReviewDecision | None = None
    proposed_diff: str = ""


def create_model() -> GeminiModel:
    """Create the Gemini model shared by TestPilot agents."""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Export it in this terminal first."
        )

    return GeminiModel(
        client_args={"api_key": api_key},
        model_id="gemini-3.1-flash-lite",
        params={"temperature": 0.1},
    )