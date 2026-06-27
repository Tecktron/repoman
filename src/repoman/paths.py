from __future__ import annotations

import shutil
from pathlib import Path


def _find(name: str) -> str:
    """Return the full path of a system binary, or the bare name as fallback."""
    return shutil.which(name) or name


# System binaries — resolved at import time so tests can monkeypatch shutil.which
PKEXEC = _find("pkexec")
LSB_RELEASE = _find("lsb_release")

# Optional companion tools — None if not installed on this system
UPDATE_MANAGER = shutil.which("update-manager")
SOFTWARE_PROPERTIES = shutil.which("software-properties-gtk")

POLKIT_HELPER = "/usr/lib/repoman/polkit-helper"


def check_required_tools() -> list[str]:
    """
    Return a list of missing required tools.
    An empty list means everything needed to run is present.
    """
    missing = []
    if not shutil.which("pkexec"):
        missing.append("pkexec (package: policykit-1)")
    if not shutil.which("lsb_release"):
        missing.append("lsb_release (package: lsb-release)")
    if not Path(POLKIT_HELPER).exists():
        missing.append(f"polkit helper not found at {POLKIT_HELPER}")
    return missing
