#Contains the safe tools available to the agent, the tools can read files and run tests & the tools cannot edit or delete anything

import subprocess
import sys
from pathlib import Path

from strands import tool


#folder containing this file is the project root
PROJECT_ROOT = Path(__file__).resolve().parent

#folders the agent shouldnt inspect
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".testpilot_backups",
    ".testpilot_proposals",
}

#files that should be ignored
IGNORED_FILES = {
    ".env",
    "testpilot.db",
    "evaluation_results.json",
}

#only allowed extensions
ALLOWED_EXTENSIONS = {
    ".py",
    ".toml",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
}

#stores the test output after the first test run
#prevents the agent from repeatedly running pytest
_cached_test_output: str | None = None


def reset_test_cache() -> None:
    """Clear the pytest cache before a new TestPilot diagnostic run."""

    global _cached_test_output
    _cached_test_output = None


def _safe_project_path(relative_path: str) -> Path:
    """Return a safe path located inside the project."""

    requested_path = (PROJECT_ROOT / relative_path).resolve()

    #confirm that the resolved path is still inside the project.
    try:
        relative_to_project = requested_path.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise ValueError(
            "Access denied: path is outside the project."
        ) from error

    #block ignored folders even if the agent requests one directly.
    if any(
        part in IGNORED_DIRECTORIES
        for part in relative_to_project.parts
    ):
        raise ValueError(
            "Access denied: this directory cannot be inspected."
        )

    #block ignored files.
    if requested_path.name in IGNORED_FILES:
        raise ValueError(
            "Access denied: this file cannot be inspected."
        )

    return requested_path


@tool
def list_project_files() -> str:
    """List the readable files inside the current project."""

    project_files: list[str] = []

    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(PROJECT_ROOT)

        if any(part in IGNORED_DIRECTORIES for part in relative_path.parts):
            continue

        if path.name in IGNORED_FILES:
            continue

        if path.suffix not in ALLOWED_EXTENSIONS:
            continue

        project_files.append(str(relative_path))

    if not project_files:
        return "No readable project files were found."

    return "\n".join(project_files)


@tool
def read_project_file(relative_path: str) -> str:
    """Read one safe text file from the project.

    Args:
        relative_path: File path relative to the project root.
    """

    path = _safe_project_path(relative_path)

    if not path.exists():
        return f"File not found: {relative_path}"

    if not path.is_file():
        return f"Not a file: {relative_path}"

    if path.name in IGNORED_FILES:
        return f"Access denied: {relative_path}"

    if path.suffix not in ALLOWED_EXTENSIONS:
        return f"Unsupported file type: {relative_path}"

    #avoids sending an extremely large file to Gemini
    if path.stat().st_size > 100_000:
        return f"File is too large to read: {relative_path}"

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Unable to decode file as UTF-8: {relative_path}"


@tool
def run_python_tests() -> str:
    """Run the Python test suite once and return the pytest evidence."""

    global _cached_test_output

    #if Gemini requests pytest again, return the previous result
    if _cached_test_output is not None:
        return (
            "Tests were already run during this diagnostic session.\n\n"
            + _cached_test_output
        )

    try:
        completed_process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        output_parts = [
            f"Pytest exit code: {completed_process.returncode}",
            completed_process.stdout.strip(),
        ]

        if completed_process.stderr.strip():
            output_parts.append(completed_process.stderr.strip())

        _cached_test_output = "\n\n".join(
            part for part in output_parts if part
        )

    except subprocess.TimeoutExpired:
        _cached_test_output = (
            "Pytest timed out after 30 seconds. "
            "The tests may be hanging."
        )

    except Exception as error:
        _cached_test_output = (
            f"Unable to run pytest: {type(error).__name__}: {error}"
        )

    return _cached_test_output