#Tests for the Milestone 7 release evaluator

from evaluation import (
    EvaluationCase,
    EvaluationResult,
    build_report,
    run_case,
)


def test_run_case_passes_for_a_passing_test(tmp_path):
    """A passing test should produce a passing evaluation."""

    tests_directory = tmp_path / "tests"
    tests_directory.mkdir()

    test_file = tests_directory / "test_pass.py"

    test_file.write_text(
        "def test_pass():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    case = EvaluationCase(
        name="sample",
        description="A small passing example.",
        targets=("tests/test_pass.py",),
    )

    result = run_case(
        case,
        root=tmp_path,
    )

    assert result.passed is True
    assert result.return_code == 0


def test_run_case_fails_when_target_is_missing(tmp_path):
    """A missing required test must fail instead of being skipped."""

    case = EvaluationCase(
        name="missing",
        description="A deliberately missing test.",
        targets=("tests/test_missing.py",),
    )

    result = run_case(
        case,
        root=tmp_path,
    )

    assert result.passed is False
    assert result.return_code == 2
    assert "Missing evaluation target" in result.output


def test_build_report_calculates_the_pass_rate():
    """The report should accurately summarize all evaluations."""

    passing = EvaluationResult(
        name="passing",
        description="Passes.",
        passed=True,
        return_code=0,
        duration_seconds=0.1,
        command=["python", "-m", "pytest"],
        output="1 passed",
    )

    failing = EvaluationResult(
        name="failing",
        description="Fails.",
        passed=False,
        return_code=1,
        duration_seconds=0.1,
        command=["python", "-m", "pytest"],
        output="1 failed",
    )

    report = build_report([passing, failing])

    assert report["overall_passed"] is False
    assert report["passed_cases"] == 1
    assert report["total_cases"] == 2
    assert report["pass_rate"] == 0.5