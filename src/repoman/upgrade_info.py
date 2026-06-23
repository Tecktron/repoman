from __future__ import annotations

import configparser
import csv
import platform
import re
from datetime import datetime
from pathlib import Path

import requests

from .models import AvailabilityStatus

_RELEASE_UPGRADES_PATH = Path("/etc/update-manager/release-upgrades")
_DISTRO_INFO_CSV = Path("/usr/share/distro-info/ubuntu.csv")
_PPA_URL_TEMPLATE = "https://ppa.launchpadcontent.net/{owner}/{ppa}/ubuntu/dists/{codename}/InRelease"
_DISTS_URL_TEMPLATE = "https://ppa.launchpadcontent.net/{owner}/{ppa}/ubuntu/dists/"


def get_current_codename_and_display() -> tuple[str, str]:
    """Return (codename, PRETTY_NAME) from /etc/os-release."""
    try:
        info = platform.freedesktop_os_release()
        codename = info.get("UBUNTU_CODENAME") or info.get("VERSION_CODENAME", "")
        display = info.get("PRETTY_NAME", "") or "Unknown Ubuntu release"
        return codename, display
    except OSError:
        return "", "Unknown Ubuntu release"


def get_upgrade_prompt() -> str:
    """Return 'lts', 'normal', or 'never' from /etc/update-manager/release-upgrades."""
    config = configparser.ConfigParser()
    try:
        config.read(_RELEASE_UPGRADES_PATH)
        return config.get("DEFAULT", "Prompt", fallback="lts").lower()
    except configparser.Error:
        return "lts"


def _parse_ubuntu_csv() -> list[dict]:
    """Parse /usr/share/distro-info/ubuntu.csv into release dicts sorted by date."""
    try:
        results = []
        with _DISTRO_INFO_CSV.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    series = row.get("series", "").strip()
                    version = row.get("version", "").strip()
                    release_str = row.get("release", "").strip()
                    if not series or not version or not release_str:
                        continue
                    release_date = datetime.strptime(release_str, "%Y-%m-%d").date()
                    results.append(
                        {
                            "series": series,
                            "version": version,
                            "date": release_date,
                            "is_lts": "LTS" in version,
                        }
                    )
                except (KeyError, ValueError):
                    continue
        results.sort(key=lambda r: r["date"])
        return results
    except (OSError, csv.Error):
        return []


def get_upgrade_targets(current_codename: str, prompt: str) -> list[tuple[str, str]]:
    """Return [(codename, display_label), ...] for releases newer than current_codename.

    prompt='lts' → LTS only; 'normal' → all; 'never' → [].
    Includes future/unreleased codenames — PPAs can pre-publish.
    """
    if prompt == "never":
        return []
    releases = _parse_ubuntu_csv()
    if not releases:
        return []
    current_idx = next((i for i, r in enumerate(releases) if r["series"] == current_codename), None)
    if current_idx is None:
        return []
    newer = releases[current_idx + 1 :]
    if prompt == "lts":
        newer = [r for r in newer if r["is_lts"]]
    return [(r["series"], f"{r['series']} ({r['version']})") for r in newer]


def get_all_known_codenames() -> list[str]:
    """Return all known Ubuntu codenames in release-date order (oldest first)."""
    return [r["series"] for r in _parse_ubuntu_csv()]


def get_ppa_suites(owner: str, ppa: str, *, timeout: int = 10) -> tuple[frozenset[str] | None, str | None]:
    """Return all Ubuntu suite names published by a Launchpad PPA.

    Fetches the dists/ directory listing in a single GET request.
    Returns (frozenset_of_codenames, None) on success,
    (frozenset(), None) on 404 (PPA exists but no packages),
    (None, error_str) on network failure.
    """
    url = _DISTS_URL_TEMPLATE.format(owner=owner, ppa=ppa)
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return frozenset(), None
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code} from {url}"
        return frozenset(re.findall(r'href="([^/"]+)/"', resp.text)), None
    except requests.exceptions.Timeout:
        return None, f"Connection timed out checking {url}"
    except requests.exceptions.ConnectionError as exc:
        return None, str(exc)
    except requests.exceptions.RequestException as exc:
        return None, str(exc)


def check_ppa_for_codename(
    ppa_owner: str, ppa_name: str, codename: str, *, timeout: int = 10
) -> tuple[AvailabilityStatus, str | None]:
    """HTTP HEAD to Launchpad PPA InRelease for the given codename.

    Returns (AVAILABLE, None) on 200, (UNAVAILABLE, None) on 404,
    (UNKNOWN, error_message) on anything else.
    Does not touch the global _network_failed state in checker.py.
    """
    url = _PPA_URL_TEMPLATE.format(owner=ppa_owner, ppa=ppa_name, codename=codename)
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return AvailabilityStatus.AVAILABLE, None
        if response.status_code == 404:
            return AvailabilityStatus.UNAVAILABLE, None
        return AvailabilityStatus.UNKNOWN, f"HTTP {response.status_code} from {url}"
    except requests.exceptions.Timeout:
        return AvailabilityStatus.UNKNOWN, f"Connection timed out checking {url}"
    except requests.exceptions.ConnectionError as exc:
        return AvailabilityStatus.UNKNOWN, str(exc)
    except requests.exceptions.RequestException as exc:
        return AvailabilityStatus.UNKNOWN, str(exc)
