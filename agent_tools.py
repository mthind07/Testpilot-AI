#read-only project inspection and pytest tools used by TestPilot

import subprocess
import sys
from pathlib import Path

from strands import tool


PROJECT_ROOT = Path(__file__).resolve().parent

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".testpilot_backups",
    ".testpilot_proposals",
}

IGNORED_FILES = {
    ".env",
    "testpilot.db",
    "evaluation_results.json",
}

ALLOWED_EXTENSIONS = {
    ".py",
    ".toml",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
}

_cached_test_output: str | None = None


def reset_test_cache() -> None:
    """Clear cached pytest output before a new diagnostic run."""

    global _cached_test_output
    _cached_test_output = None


def _safe_project_path(
    relative_path: str,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    """Return a safe path located inside project_root."""

    root = project_root.resolve()
    requested_path = (root / relative_path).resolve()

    try:
        relative_to_project = requested_path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Access denied: path is outside the project."
        ) from error

    if any(
        part in IGNORED_DIRECTORIES
        for part in relative_to_project.parts
    ):
        raise ValueError(
            "Access denied: this directory cannot be inspected."
        )

    if requested_path.name in IGNORED_FILES:
        raise ValueError(
            "Access denied: this file cannot be inspected."
        )

    return requested_path


def collect_project_files(
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    """Return readable project paths for any supplied project root."""

    root = project_root.resolve()
    project_files: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(root)
        if any(
            part in IGNORED_DIRECTORIES
            for part in relative_path.parts
        ):
            continue
        if path.name in IGNORED_FILES:
            continue
        if path.suffix not in ALLOWED_EXTENSIONS:
            continue

        project_files.append(relative_path.as_posix())

    return project_files


def read_project_text(
    relative_path: str,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Read one safe UTF-8 project file."""

    path = _safe_project_path(relative_path, project_root)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {relative_path}")
    if path.suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {relative_path}")
    if path.stat().st_size > 100_000:
        raise ValueError(f"File is too large to read: {relative_path}")

    return path.read_text(encoding="utf-8")


def execute_python_tests(
    project_root: Path = PROJECT_ROOT,
    timeout_seconds: int = 30,
) -> tuple[int, str]:
    """Run pytest once and return its exit code and complete output."""

    root = project_root.resolve()

    try:
        completed_process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            124,
            f"Pytest timed out after {timeout_seconds} seconds.",
        )
    except Exception as error:
        return (
            125,
            f"Unable to run pytest: {type(error).__name__}: {error}",
        )

    output_parts = [
        completed_process.stdout.strip(),
        completed_process.stderr.strip(),
    ]
    output = "\n\n".join(part for part in output_parts if part)
    return completed_process.returncode, output


@tool
def list_project_files() -> str:
    """List readable files inside the current TestPilot project."""

    paths = collect_project_files(PROJECT_ROOT)
    if not paths:
        return "No readable project files were found."
    return "\n".join(paths)


@tool
def read_project_file(relative_path: str) -> str:
    """Read one safe text file relative to the project root."""

    try:
        return read_project_text(relative_path, PROJECT_ROOT)
    except (FileNotFoundError, UnicodeDecodeError, ValueError) as error:
        return str(error)


@tool
def run_python_tests() -> str:
    """Run the current project's pytest suite once."""

    global _cached_test_output

    if _cached_test_output is not None:
        return (
            "Tests were already run during this diagnostic session.\n\n"
            + _cached_test_output
        )

    exit_code, output = execute_python_tests(PROJECT_ROOT)
    _cached_test_output = (
        f"Pytest exit code: {exit_code}\n\n{output}".rstrip()
    )
    return _cached_test_output