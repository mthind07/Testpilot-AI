#Milestone 7: Deterministic release evaluations for TestPilot AI, these evaluations intentionally run without Gemini
#The agent behaviour is already tested using mocked agents, release evaluations must be repeatable, free to run, and safe to execute inside GitHub Actions


from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


#the root directory of the TestPilot project
ROOT = Path(__file__).resolve().parent

#this generated file will be uploaded by GitHub Actions
OUTPUT_PATH = ROOT / "evaluation_results.json"


@dataclass(frozen=True)
class EvaluationCase:
    """One named release gate and the pytest paths that it runs."""

    name: str
    description: str
    targets: tuple[str, ...]


@dataclass
class EvaluationResult:
    """The saved result from one release evaluation."""

    name: str
    description: str
    passed: bool
    return_code: int
    duration_seconds: float
    command: list[str]
    output: str


#these four evaluations cover the important layers of TestPilot
EVALUATION_CASES = (
    EvaluationCase(
        name="proposal_safety",
        description=(
            "Proposal creation, approval, application, and rollback are safe."
        ),
        targets=("tests/test_proposals.py",),
    ),
    EvaluationCase(
        name="multi_agent_safety",
        description=(
            "Planner, debugger, validator, and reviewer cooperate safely."
        ),
        targets=("tests/test_multi_agent_workflow.py",),
    ),
    EvaluationCase(
        name="dashboard_controls",
        description=(
            "Dashboard actions preserve the same safety rules as the CLI."
        ),
        targets=("tests/test_dashboard.py",),
    ),
    EvaluationCase(
        name="full_regression",
        description="The complete TestPilot test suite passes.",
        targets=("tests",),
    ),
)


def run_case(
    case: EvaluationCase,
    *,
    root: Path = ROOT,
    timeout_seconds: int = 180,
) -> EvaluationResult:
    """Run one evaluation and return a machine-readable result."""

    command = [
        sys.executable,
        "-m",
        "pytest",
        *case.targets,
        "-q",
    ]

    #missing safety test must fail the release instead of being skipped
    missing_targets = [
        target
        for target in case.targets
        if not (root / target).exists()
    ]

    if missing_targets:
        return EvaluationResult(
            name=case.name,
            description=case.description,
            passed=False,
            return_code=2,
            duration_seconds=0.0,
            command=command,
            output=(
                "Missing evaluation target(s): "
                + ", ".join(missing_targets)
            ),
        )

    started_at = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        duration = time.perf_counter() - started_at

        #combine stdout and stderr into one useful diagnostic message
        combined_output = "\n".join(
            part.strip()
            for part in (completed.stdout, completed.stderr)
            if part.strip()
        )

        return EvaluationResult(
            name=case.name,
            description=case.description,
            passed=completed.returncode == 0,
            return_code=completed.returncode,
            duration_seconds=round(duration, 3),
            command=command,
            output=combined_output,
        )

    except subprocess.TimeoutExpired as error:
        duration = time.perf_counter() - started_at

        return EvaluationResult(
            name=case.name,
            description=case.description,
            passed=False,
            return_code=124,
            duration_seconds=round(duration, 3),
            command=command,
            output=(
                f"Evaluation timed out after "
                f"{timeout_seconds} seconds: {error}"
            ),
        )


def build_report(results: list[EvaluationResult]) -> dict:
    """Combine every result into the final release report."""

    passed_cases = sum(result.passed for result in results)
    total_cases = len(results)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_passed": passed_cases == total_cases,
        "passed_cases": passed_cases,
        "total_cases": total_cases,
        "pass_rate": (
            round(passed_cases / total_cases, 4)
            if total_cases
            else 0.0
        ),
        "results": [
            asdict(result)
            for result in results
        ],
    }


def write_report(
    report: dict,
    output_path: Path = OUTPUT_PATH,
) -> None:
    """Save the report for developers and GitHub Actions."""

    output_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Run every release gate and return a shell-friendly exit code."""

    print(
        "\n"
        "========== TESTPILOT RELEASE EVALUATION =========="
        "\n"
    )

    results: list[EvaluationResult] = []

    for case in EVALUATION_CASES:
        result = run_case(case)
        results.append(result)

        status = "PASS" if result.passed else "FAIL"

        print(
            f"[{status}] {result.name} "
            f"({result.duration_seconds:.3f}s)"
        )

        #immediately show why a failed evaluation failed
        if not result.passed and result.output:
            print(result.output)

    report = build_report(results)
    write_report(report)

    print(
        f"\nResult: {report['passed_cases']}/"
        f"{report['total_cases']} evaluation gates passed."
    )
    print(f"Report: {OUTPUT_PATH}")

    #a non-zero exit code makes GitHub Actions stop a bad release
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())