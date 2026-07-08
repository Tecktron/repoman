"""Save and load .repoman state files (pure JSON, no GTK, fully unit-testable).

File format v2: JSON with version (2), saved_at, saved_codename, and a repos list.
Each repo entry captures enough to reconstruct it and adapt suites for a different
Ubuntu release. GPG key file bytes are embedded as base64 so the file is fully
self-contained for cross-machine migration.

Version 1 files (no saved_codename, no signed_by_content_b64) are accepted; the
cross-machine adaptation flow is skipped when saved_codename is absent.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from .models import FileFormat, Repository

# Suite names that indicate a version-agnostic repository (same set as parser.py).
# Duplicated here so config_io stays free of heavy parser.py imports.
_BUILTIN_AGNOSTIC_SUITES = frozenset(
    [
        "stable",
        "main",
        "testing",
        "sid",
        "unstable",
        "bookworm",
        "bullseye",
        "buster",
        "stretch",
        "oldstable",
        "oldoldstable",
    ]
)


def save_config(repos: list[Repository], current_codename: str = "") -> str:
    """Serialise repo list to a JSON string for writing to a .repoman file.

    :param repos: Repositories to serialise.
    :param current_codename: Running Ubuntu codename (e.g. ``'noble'``). Stored in the
        file so cross-machine restores can adapt suites automatically.
    """
    repo_entries = []
    for r in repos:
        entry: dict = {
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
        if r.signed_by and r.signed_by.startswith("/"):
            try:
                key_bytes = Path(r.signed_by).read_bytes()
                entry["signed_by_content_b64"] = base64.b64encode(key_bytes).decode("ascii")
            except OSError:
                pass  # key file unreadable — omit signed_by_content_b64; restore will warn
        repo_entries.append(entry)

    return json.dumps(
        {
            "version": 2,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "saved_codename": current_codename,
            "repos": repo_entries,
        },
        indent=2,
    )


def load_config(path: Path) -> tuple[list[dict], str | None]:
    """Parse a .repoman JSON file and return repo entries plus the saved codename.

    :param path: Path to the .repoman file to read.
    :returns: ``(repos, saved_codename)`` where ``saved_codename`` is ``None`` for v1 files.
    :raises json.JSONDecodeError: File is not valid JSON.
    :raises ValueError: ``version`` field is missing or not 1 or 2.
    :raises KeyError: Required top-level key is absent.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if version not in (1, 2):
        raise ValueError(f"Unsupported config version: {version!r}")
    saved_codename: str | None = data.get("saved_codename")
    return data["repos"], saved_codename


def classify_restore_entry(
    entry: dict,
    saved_codename: str,
    current_codename: str,
    all_known: list[str],
    agnostic_names: frozenset[str] | None = None,
) -> Literal["restore_as_is", "update_suite", "add_disabled", "ppa_check"]:
    """Classify what action to take for a saved entry during cross-machine restore.

    :param entry: A raw repo dict from a loaded .repoman file.
    :param saved_codename: Codename the file was saved on.
    :param current_codename: Codename of the current machine.
    :param all_known: All Ubuntu codenames in release-date order (oldest first).
    :param agnostic_names: Suite names treated as version-agnostic. Defaults to built-ins.
    :returns: ``"restore_as_is"`` — write unchanged; ``"update_suite"`` — swap suite to
        ``current_codename``; ``"add_disabled"`` — write with ``enabled=False``; or
        ``"ppa_check"`` — need a network check before deciding.
    """
    names = agnostic_names if agnostic_names is not None else _BUILTIN_AGNOSTIC_SUITES
    suites = entry.get("suites") or []

    def _agnostic(s: str) -> bool:
        return s in names or not (s.isalpha() and s.islower())

    # All suites are version-agnostic → restore as-is regardless of codename
    if suites and all(_agnostic(s) for s in suites):
        return "restore_as_is"

    # PPA: needs live availability check to determine correct action
    uris = entry.get("uris") or []
    uri = uris[0] if uris else ""
    if "ppa.launchpadcontent.net" in uri or "ppa.launchpad.net" in uri:
        return "ppa_check"

    # Non-PPA with release codename suite: compare age to current
    try:
        current_idx = all_known.index(current_codename)
    except ValueError:
        return "restore_as_is"

    found_known = False
    for suite in suites:
        if not (suite.isalpha() and suite.islower()):
            continue
        try:
            suite_idx = all_known.index(suite)
        except ValueError:
            continue
        found_known = True
        if suite_idx > current_idx:
            return "add_disabled"

    return "update_suite" if found_known else "restore_as_is"


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
