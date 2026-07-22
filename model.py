#Configures Gemini and defines the exact structure of a TestPilot report

import os
from typing import Literal

from pydantic import BaseModel, Field
from strands.models.gemini import GeminiModel


class DiagnosticReport(BaseModel):
    """A validated report produced by the TestPilot agent."""

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
        description="Test failures, file locations, and other supporting evidence."
    )

    root_causes: list[str] = Field(
        description="The likely technical causes of the discovered problems."
    )

    proposed_fixes: list[str] = Field(
        description="Recommended changes. These are suggestions only."
    )

    risk: Literal["low", "medium", "high"] = Field(
        description="Estimated risk of applying the proposed changes."
    )

    tests_to_rerun: list[str] = Field(
        description="Tests that should be rerun after the problems are corrected."
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

def create_model() -> GeminiModel:
    """Create and return the Gemini model used by TestPilot."""

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Export it in this terminal first."
        )

    return GeminiModel(
        client_args={
            "api_key": api_key
        },

        #keep the exact model ID that already worked in Milestone 1
        model_id="gemini-3.1-flash-lite",

        #low temperature makes debugging reports more consistent
        params={
            "temperature": 0.1
        },
    )