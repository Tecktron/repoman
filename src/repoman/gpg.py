"""GPG key fetch and verification helpers. No GTK — fully unit-testable."""

from __future__ import annotations

import logging
import subprocess
from base64 import b64encode
from pathlib import Path

import requests

_log = logging.getLogger(__name__)

_PPA_HOSTS = {"ppa.launchpadcontent.net", "ppa.launchpad.net"}
_KEYSERVER_FETCH = "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x{fingerprint}"


def is_ppa_uri(uri: str) -> bool:
    from urllib.parse import urlparse

    return urlparse(uri).netloc in _PPA_HOSTS


def fetch_key(url: str) -> tuple[bytes | None, str | None]:
    """Download a GPG key from a URL. Returns (key_bytes, error_str)."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content, None
    except requests.RequestException as exc:
        _log.debug("fetch_key failed for %s", url, exc_info=True)
        return None, str(exc)


def fetch_ppa_key(owner: str, ppa: str) -> tuple[bytes | None, str | None]:
    """Fetch a PPA signing key via launchpadlib. Returns (key_bytes, error_str)."""
    try:
        from launchpadlib.launchpad import Launchpad

        lp = Launchpad.login_anonymously("repoman", "production", version="devel")
        archive = lp.people[owner].getPPAByName(name=ppa)
        fingerprint = archive.signing_key_fingerprint
        if not fingerprint:
            return None, "No signing key found on Launchpad"
        url = _KEYSERVER_FETCH.format(fingerprint=fingerprint)
        return fetch_key(url)
    except Exception as exc:
        _log.debug("fetch_ppa_key failed for %s/%s", owner, ppa, exc_info=True)
        return None, str(exc)


def verify_key(content: str | bytes) -> tuple[bool, str]:
    """Verify GPG key via gpg --import-options show-only. Returns (valid, error)."""
    data = content.encode() if isinstance(content, str) else content
    try:
        result = subprocess.run(
            ["/usr/bin/gpg", "--batch", "--import-options", "show-only", "--import"],
            input=data,
            capture_output=True,
        )
        if result.returncode != 0:
            return False, result.stderr.decode(errors="replace").strip()
        return True, ""
    except OSError as exc:
        return False, str(exc)


def key_to_b64(key_bytes: bytes) -> str:
    """Base64-encode key bytes for transmission in a JSON polkit payload."""
    return b64encode(key_bytes).decode("ascii")


def read_key_text(path: Path) -> str | None:
    """Read a key file as ASCII-armored text, or None if binary/missing."""
    try:
        text = path.read_text(encoding="ascii")
        if "BEGIN PGP" in text:
            return text
    except (OSError, UnicodeDecodeError):
        pass
    return None


def read_key_content(path: Path) -> str | None:
    """Read a keyring file as displayable ASCII text.

    ASCII-armored files are returned directly. Binary (dearmored) files
    are converted via gpg --enarmor so they can be shown in the editor.
    Returns None if the file is missing, empty, or conversion fails.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    if raw.lstrip().startswith(b"-----BEGIN PGP"):
        return raw.decode("ascii", errors="replace")
    try:
        result = subprocess.run(
            ["/usr/bin/gpg", "--batch", "--enarmor"],
            input=raw,
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("ascii", errors="replace")
    except OSError:
        pass
    return None
