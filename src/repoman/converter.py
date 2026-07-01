"""ONE_LINE (.list) to DEB822 (.sources) format converter. Pure — no I/O."""

from __future__ import annotations

from pathlib import Path

from .models import FileFormat, Repository
from .writer import repo_to_deb822


def convert_to_deb822(repo: Repository) -> tuple[Path, str]:
    """
    Convert a ONE_LINE format repo to a DEB822 .sources file.

    Returns (new_path, content) — does NOT write to disk. The caller passes
    both to the polkit helper, which also deletes the old .list file.

    Updates the in-memory Repository to reflect the new format and path.
    """
    if repo.file_format != FileFormat.ONE_LINE:
        raise ValueError(f"Expected ONE_LINE format, got {repo.file_format}")

    new_path = repo.source_file.with_suffix(".sources")
    content = repo_to_deb822(repo)

    # Update in-memory object so the UI reflects the change immediately
    repo.source_file = new_path
    repo.file_format = FileFormat.DEB822

    return new_path, content
