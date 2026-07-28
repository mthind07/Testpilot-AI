#elease-readiness checks for TestPilot AI v1.0.0

from pathlib import Path
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_required_release_files_exist():
    """The release needs code, automation, and documentation."""

    required_files = (
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "SECURITY.md",
        ".env.example",
        "evaluation.py",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    )

    missing_files = [
        file_name
        for file_name in required_files
        if not (ROOT / file_name).is_file()
    ]

    assert missing_files == [], (
        f"Missing release files: {missing_files}"
    )


def test_project_version_is_1_0_0():
    """The project version and GitHub tag must agree."""

    pyproject_data = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert pyproject_data["project"]["version"] == "1.0.0"


def test_secret_and_generated_files_are_ignored_and_untracked():
    """API keys and generated reports must never enter Git history."""

    protected_paths = {
        ".env",
        ".streamlit/secrets.toml",
        "evaluation_results.json",
    }

    ignore_entries = {
        line.strip()
        for line in (
            ROOT / ".gitignore"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
    }

    #confirm all three paths are present in .gitignore
    assert protected_paths <= ignore_entries

    #confirm none of them were committed before being ignored
    tracked_check = subprocess.run(
        [
            "git",
            "ls-files",
            "--",
            *sorted(protected_paths),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert tracked_check.returncode == 0
    assert tracked_check.stdout.strip() == ""