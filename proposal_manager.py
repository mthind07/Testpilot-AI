#proposal storage, application, and rollback safety

import difflib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from model import RepairPlan


PROJECT_ROOT = Path(__file__).resolve().parent
PROPOSALS_DIRECTORY = PROJECT_ROOT / ".testpilot_proposals"
BACKUPS_DIRECTORY = PROJECT_ROOT / ".testpilot_backups"

EDITABLE_TOP_LEVEL_DIRECTORIES = {
    "sample_app",
    "tests",
}

PROTECTED_FILES = {
    "tests/test_storage.py",
    "tests/test_proposals.py",
    "tests/test_multi_agent_workflow.py",
}

PROPOSAL_ID_PATTERN = re.compile(
    r"^proposal-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$"
)


def _utc_now() -> str:
    """Return the current UTC time in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def _directories(project_root: Path) -> tuple[Path, Path]:
    """Return proposal and backup folders for a project."""

    return (
        project_root / ".testpilot_proposals",
        project_root / ".testpilot_backups",
    )


def _proposal_path(
    proposal_id: str,
    proposals_directory: Path,
) -> Path:
    """Return a validated proposal JSON path."""

    if not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
        raise ValueError("Invalid proposal ID.")
    return proposals_directory / f"{proposal_id}.json"


def _validate_target(
    file_path: str,
    project_root: Path,
) -> Path:
    """Validate that a proposed file may be changed."""

    supplied_path = Path(file_path)
    if supplied_path.is_absolute():
        raise ValueError("Absolute file paths are not allowed.")

    target = (project_root / supplied_path).resolve()
    try:
        relative_path = target.relative_to(project_root.resolve())
    except ValueError as error:
        raise ValueError(
            f"Path escapes the project: {file_path}"
        ) from error

    if not relative_path.parts:
        raise ValueError("A project file must be selected.")
    if (
        relative_path.parts[0]
        not in EDITABLE_TOP_LEVEL_DIRECTORIES
    ):
        raise ValueError(
            f"Milestone 3 cannot modify: {file_path}"
        )

    normalized_path = relative_path.as_posix()
    if normalized_path in PROTECTED_FILES:
        raise ValueError(
            f"Protected TestPilot file: {file_path}"
        )
    if target.suffix != ".py":
        raise ValueError(
            "Milestone 3 can only change Python files."
        )
    if not target.exists() or not target.is_file():
        raise ValueError(
            f"Target file does not exist: {file_path}"
        )

    return target


def _build_updated_files(
    plan: RepairPlan,
    project_root: Path,
) -> dict[Path, tuple[str, str]]:
    """Validate all changes and build updated content in memory."""

    original_files: dict[Path, str] = {}
    updated_files: dict[Path, str] = {}

    for change in plan.changes:
        target = _validate_target(change.file_path, project_root)

        if target not in original_files:
            original_content = target.read_text(encoding="utf-8")
            original_files[target] = original_content
            updated_files[target] = original_content

        current_content = updated_files[target]
        match_count = current_content.count(change.original_text)

        if match_count == 0:
            raise ValueError(
                f"Original text was not found in {change.file_path}. "
                "The proposal may be stale or inaccurate."
            )
        if match_count > 1:
            raise ValueError(
                f"Original text appears more than once in "
                f"{change.file_path}. Refusing an ambiguous replacement."
            )
        if change.original_text == change.replacement_text:
            raise ValueError(
                f"Proposal does not change anything in "
                f"{change.file_path}."
            )

        updated_files[target] = current_content.replace(
            change.original_text,
            change.replacement_text,
            1,
        )

    return {
        target: (original_files[target], updated_files[target])
        for target in updated_files
    }


def _render_diff(
    updates: dict[Path, tuple[str, str]],
    project_root: Path,
) -> str:
    """Create a Git-style diff for human review."""

    sections: list[str] = []

    for target, (original, replacement) in updates.items():
        relative_path = target.relative_to(project_root).as_posix()
        difference = difflib.unified_diff(
            original.splitlines(),
            replacement.splitlines(),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
        section = "\n".join(difference)
        if section:
            sections.append(section)

    return "\n\n".join(sections)


def _write_json(path: Path, information: dict) -> None:
    """Write formatted JSON to disk."""

    path.write_text(
        json.dumps(information, indent=2),
        encoding="utf-8",
    )


def _atomic_write(target: Path, content: str) -> None:
    """Replace a file atomically while preserving its permissions."""

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".testpilot-temp",
        dir=target.parent,
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as temporary_file:
            temporary_file.write(content)

        shutil.copymode(target, temporary_name)
        os.replace(temporary_name, target)
    except Exception:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def save_proposal(
    plan: RepairPlan,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Validate and save a pending repair proposal."""

    project_root = project_root.resolve()
    proposals_directory, _ = _directories(project_root)
    updates = _build_updated_files(plan, project_root)
    proposal_diff = _render_diff(updates, project_root)

    proposal_id = (
        datetime.now(timezone.utc).strftime(
            "proposal-%Y%m%d-%H%M%S-"
        )
        + uuid.uuid4().hex[:8]
    )

    proposals_directory.mkdir(parents=True, exist_ok=True)
    envelope = {
        "proposal_id": proposal_id,
        "status": "pending",
        "created_at": _utc_now(),
        "applied_at": None,
        "rolled_back_at": None,
        "plan": plan.model_dump(),
    }

    proposal_file = _proposal_path(
        proposal_id,
        proposals_directory,
    )
    _write_json(proposal_file, envelope)

    diff_file = proposals_directory / f"{proposal_id}.diff"
    diff_file.write_text(proposal_diff, encoding="utf-8")
    return proposal_id


def load_proposal(
    proposal_id: str,
    project_root: Path = PROJECT_ROOT,
) -> tuple[RepairPlan, dict]:
    """Load and validate a saved proposal."""

    project_root = project_root.resolve()
    proposals_directory, _ = _directories(project_root)
    proposal_file = _proposal_path(
        proposal_id,
        proposals_directory,
    )

    if not proposal_file.exists():
        raise FileNotFoundError(
            f"Proposal was not found: {proposal_id}"
        )

    envelope = json.loads(
        proposal_file.read_text(encoding="utf-8")
    )
    plan = RepairPlan.model_validate(envelope["plan"])
    return plan, envelope


def get_proposal_diff(
    proposal_id: str,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Return a saved human-readable proposal diff."""

    project_root = project_root.resolve()
    proposals_directory, _ = _directories(project_root)

    if not PROPOSAL_ID_PATTERN.fullmatch(proposal_id):
        raise ValueError("Invalid proposal ID.")

    diff_file = proposals_directory / f"{proposal_id}.diff"
    if not diff_file.exists():
        raise FileNotFoundError(
            f"Proposal diff was not found: {proposal_id}"
        )

    return diff_file.read_text(encoding="utf-8")


def apply_proposal(
    proposal_id: str,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    """Apply a pending proposal after explicit approval."""

    project_root = project_root.resolve()
    proposals_directory, backups_directory = _directories(
        project_root
    )
    plan, envelope = load_proposal(proposal_id, project_root)

    if envelope["status"] != "pending":
        raise ValueError(
            f"Proposal status is {envelope['status']}, not pending."
        )

    updates = _build_updated_files(plan, project_root)
    backup_root = backups_directory / proposal_id

    if backup_root.exists():
        raise ValueError(
            "A backup already exists for this proposal."
        )

    for target in updates:
        relative_path = target.relative_to(project_root)
        backup_path = backup_root / relative_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)

    changed_files: list[str] = []
    try:
        for target, (_, updated_content) in updates.items():
            _atomic_write(target, updated_content)
            changed_files.append(
                target.relative_to(project_root).as_posix()
            )
    except Exception:
        for target in updates:
            relative_path = target.relative_to(project_root)
            backup_path = backup_root / relative_path
            if backup_path.exists():
                shutil.copy2(backup_path, target)
        raise

    envelope["status"] = "applied"
    envelope["applied_at"] = _utc_now()
    proposal_file = _proposal_path(
        proposal_id,
        proposals_directory,
    )
    _write_json(proposal_file, envelope)
    return changed_files


def rollback_proposal(
    proposal_id: str,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    """Restore files from an applied proposal's backups."""

    project_root = project_root.resolve()
    proposals_directory, backups_directory = _directories(
        project_root
    )
    plan, envelope = load_proposal(proposal_id, project_root)

    if envelope["status"] != "applied":
        raise ValueError(
            "Only an applied proposal can be rolled back."
        )

    backup_root = backups_directory / proposal_id
    restored_files: list[str] = []
    visited_files: set[str] = set()

    for change in plan.changes:
        if change.file_path in visited_files:
            continue
        visited_files.add(change.file_path)

        target = _validate_target(change.file_path, project_root)
        relative_path = target.relative_to(project_root)
        backup_path = backup_root / relative_path

        if not backup_path.exists():
            raise FileNotFoundError(
                f"Backup is missing for {change.file_path}."
            )

        shutil.copy2(backup_path, target)
        restored_files.append(relative_path.as_posix())

    envelope["status"] = "rolled_back"
    envelope["rolled_back_at"] = _utc_now()
    proposal_file = _proposal_path(
        proposal_id,
        proposals_directory,
    )
    _write_json(proposal_file, envelope)
    return restored_files