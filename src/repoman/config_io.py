"""Save and load .repoman state files (pure JSON, no GTK, fully unit-testable).

File format v1: JSON with version, saved_at, and a repos list.
Each entry captures enough to reconstruct a Repository and detect drift
when the same config is loaded on a different machine or after a reinstall.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import FileFormat, Repository


def save_config(repos: list[Repository]) -> str:
    """Serialise repo list to a JSON string for writing to a .repoman file."""
    return json.dumps(
        {
            "version": 1,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "repos": [
                {
                    "types": r.types,
                    "uris": r.uris,
                    "suites": r.suites,
                    "components": r.components,
                    "enabled": r.enabled,
                    "description": r.description,
                    "signed_by": r.signed_by,
                    "architectures": r.architectures,
                    "source_file": str(r.source_file),
                }
                for r in repos
            ],
        },
        indent=2,
    )


def load_config(path: Path) -> list[dict]:
    """Parse a .repoman JSON file and return the list of repo entries.

    :param path: Path to the .repoman file to read.
    :type path: Path
    :returns: List of raw repo dicts from the ``repos`` key.
    :rtype: list[dict]
    :raises json.JSONDecodeError: File is not valid JSON.
    :raises ValueError: ``version`` field is missing or not ``1``.
    :raises KeyError: Required top-level key is absent.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError(f"Unsupported config version: {data.get('version')!r}")
    return data["repos"]


def match_repos(
    saved: list[dict],
    live: list[Repository],
) -> tuple[list[tuple[dict, Repository]], list[dict]]:
    """Match saved config entries to live repos by primary URI.

    :param saved: List of raw repo dicts from a loaded .repoman file.
    :type saved: list[dict]
    :param live: Currently loaded repositories from the system.
    :type live: list[Repository]
    :returns: A 2-tuple of ``(matched, missing)``, where ``matched`` is a list
        of ``(saved_entry, live_repo)`` pairs for repos found on the system,
        and ``missing`` is a list of saved entries whose URI was not found.
    :rtype: tuple[list[tuple[dict, Repository]], list[dict]]
    """
    live_by_uri = {r.uris[0]: r for r in live if r.uris}
    matched: list[tuple[dict, Repository]] = []
    missing: list[dict] = []
    for entry in saved:
        uris = entry.get("uris") or []
        uri = uris[0] if uris else None
        if uri and uri in live_by_uri:
            matched.append((entry, live_by_uri[uri]))
        else:
            missing.append(entry)
    return matched, missing


def entry_to_repository(entry: dict) -> Repository:
    """Reconstruct a Repository from a saved config entry.

    Used when creating repos that exist in the config but not on the system.
    Always produces DEB822 format; source_file is taken from the saved entry.
    """
    return Repository(
        source_file=Path(entry["source_file"]),
        file_format=FileFormat.DEB822,
        types=entry.get("types") or ["deb"],
        uris=entry["uris"],
        suites=entry.get("suites") or [],
        components=entry.get("components") or [],
        enabled=entry.get("enabled", True),
        description=entry.get("description"),
        signed_by=entry.get("signed_by"),
        architectures=entry.get("architectures") or [],
    )
