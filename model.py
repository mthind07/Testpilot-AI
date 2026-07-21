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