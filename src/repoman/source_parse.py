"""Pure helpers for parsing APT source text blocks. No GTK — fully unit-testable."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from debian.deb822 import Deb822

_log = logging.getLogger(__name__)

# One-line format: deb[-src] [opts] URI suite [components...]
_ONELINE_RE = re.compile(
    r"^(deb(?:-src)?)\s+(?:\[([^\]]*)\]\s+)?(\S+)\s+(\S+)(?:\s+(.+))?$",
    re.IGNORECASE,
)


def parse_source_block(text: str) -> dict | None:
    """Parse a deb one-liner or DEB822 block into a field dict. Returns None on failure."""
    text = text.strip()
    if not text:
        return None

    # Try DEB822 first (has colons in field names)
    if ":" in text:
        try:
            stanza = Deb822(text)
            uris = stanza.get("URIs", "").split() or stanza.get("URI", "").split()
            types = stanza.get("Types", "deb").split()
            suites = stanza.get("Suites", "").split() or stanza.get("Suite", "").split()
            components = stanza.get("Components", "").split() or stanza.get("Component", "").split()
            enabled_str = stanza.get("Enabled", "yes").lower()
            signed_by = stanza.get("Signed-By", "").strip() or None
            description = stanza.get("X-Repolib-Name") or stanza.get("Description") or None
            if uris:
                return {
                    "types": types,
                    "uris": uris,
                    "suites": suites,
                    "components": components,
                    "enabled": enabled_str not in ("no", "false", "0"),
                    "signed_by": signed_by,
                    "description": description,
                }
        except Exception:
            _log.debug("DEB822 parse failed", exc_info=True)

    # Try one-line format
    m = _ONELINE_RE.match(text)
    if m:
        type_str, options_str, uri, suite, components_str = m.groups()
        types = [type_str.lower()]
        components = components_str.split() if components_str else []
        signed_by = None
        if options_str:
            for opt in options_str.split():
                if opt.startswith("signed-by="):
                    signed_by = opt[len("signed-by=") :]
        return {
            "types": types,
            "uris": [uri],
            "suites": [suite],
            "components": components,
            "enabled": True,
            "signed_by": signed_by,
            "description": None,
        }

    return None


def uri_to_source_filename(uri: str) -> str:
    """Derive a .sources filename from a URI's hostname."""
    host = urlparse(uri).netloc or uri
    sanitized = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    return f"{sanitized}.sources"


def uri_to_key_filename(uri: str) -> str:
    """Derive a .gpg keyring filename from a URI's hostname."""
    host = urlparse(uri).netloc or uri
    sanitized = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    return f"{sanitized}.gpg"
