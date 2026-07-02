"""APT sources.list.d parser for DEB822 (.sources) and one-line (.list) formats."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from debian.deb822 import Deb822

from .models import AvailabilityStatus, FileFormat, Repository

_SOURCES_DIR = Path("/etc/apt/sources.list.d")

# XDG user config override, then system default shipped with the package
_USER_AGNOSTIC_CONF = Path.home() / ".config" / "repoman" / "suite-agnostic.conf"
_SYSTEM_AGNOSTIC_CONF = Path("/usr/share/repoman/suite-agnostic.conf")
# Development fallback: config bundled alongside this source tree
_DEV_AGNOSTIC_CONF = Path(__file__).parent.parent.parent / "data" / "suite-agnostic.conf"

# URIs from these hostnames are managed by Ubuntu/Canonical directly and
# should never be shown, edited, or disabled by repoman.
_OFFICIAL_UBUNTU_HOSTS = frozenset(
    [
        "archive.ubuntu.com",
        "security.ubuntu.com",
        "ports.ubuntu.com",  # non-x86 arch mirror
        "esm.ubuntu.com",  # Ubuntu Pro / ESM — managed by ubuntu-advantage-tools
    ]
)

_BUILTIN_AGNOSTIC = frozenset(
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


def _load_agnostic_names() -> frozenset[str]:
    """Load suite-agnostic names from config, falling back to built-ins."""
    for candidate in (_USER_AGNOSTIC_CONF, _SYSTEM_AGNOSTIC_CONF, _DEV_AGNOSTIC_CONF):
        if candidate.exists():
            names = set()
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    names.add(line)
            return frozenset(names) if names else _BUILTIN_AGNOSTIC
    return _BUILTIN_AGNOSTIC


def _is_official_ubuntu(uris: list[str]) -> bool:
    """Return True if all URIs point at Ubuntu/Canonical official infrastructure."""
    return bool(uris) and all(urlparse(u).hostname in _OFFICIAL_UBUNTU_HOSTS for u in uris)


def _is_suite_agnostic(suites: list[str], agnostic_names: frozenset[str]) -> bool:
    """
    Return True if all suites indicate a version-agnostic repo.
    A suite is agnostic if it's in the known-agnostic list OR if it contains
    non-alpha characters (e.g. 'focal-security', 'noble/updates') — these are
    component-style paths, not release codenames.
    """
    if not suites:
        return False
    return all(s in agnostic_names or not (s.isalpha() and s.islower()) for s in suites)


def _deb822_leading_comments(text: str) -> list[str | None]:
    """
    For each DEB822 paragraph, return the first # comment line that appears
    immediately before it (or None).  This is how repolib / software-properties-gtk
    stores a human-readable name: a bare "#Name" line at the top of the stanza,
    not as a proper DEB822 field.
    """
    comments: list[str | None] = []
    current_comment: str | None = None
    in_paragraph = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if in_paragraph:
                in_paragraph = False
                current_comment = None
        elif stripped.startswith("#") and not in_paragraph:
            if current_comment is None:
                candidate = stripped.lstrip("#").strip()
                if candidate:
                    current_comment = candidate
        elif not in_paragraph:
            # First key:value line of a new paragraph
            comments.append(current_comment)
            in_paragraph = True

    return comments


class Parser:
    """Scans sources.list.d and parses DEB822 and one-line format repo files."""

    def __init__(self, sources_dir: Path = _SOURCES_DIR) -> None:
        self._sources_dir = sources_dir
        self._agnostic_names = _load_agnostic_names()

    def load_all(self) -> list[Repository]:
        """Scan sources_dir and return all repos sorted by display_name."""
        repos: list[Repository] = []
        if not self._sources_dir.exists():
            return repos
        for entry in sorted(self._sources_dir.iterdir()):
            if entry.suffix == ".sources":
                repos.extend(self._parse_deb822(entry))
            elif entry.suffix == ".list":
                repos.extend(self._parse_one_line(entry))
        repos.sort(key=lambda r: r.display_name.lower())
        return repos

    # ------------------------------------------------------------------
    # DEB822 (.sources)
    # ------------------------------------------------------------------

    def _parse_deb822(self, path: Path) -> list[Repository]:
        """Parse a DEB822 .sources file and return all non-official repos found.

        :param path: Absolute path to the .sources file.
        :type path: Path
        :returns: Parsed repositories (may be empty if file is unreadable or
            contains only official Ubuntu entries).
        :rtype: list[Repository]
        """
        repos = []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return repos

        # Extract leading # comments per paragraph (e.g. "#Gimp" written by repolib)
        leading = _deb822_leading_comments(text)
        for i, stanza in enumerate(Deb822.iter_paragraphs(text)):
            repo = self._deb822_stanza_to_repo(stanza, path)
            if repo is not None:
                if repo.description is None and i < len(leading) and leading[i]:
                    repo.description = leading[i]
                repos.append(repo)
        return repos

    def _deb822_stanza_to_repo(self, stanza: Deb822, path: Path) -> Repository | None:
        """Convert one parsed DEB822 stanza into a Repository, or None to skip it.

        Returns None for stanzas that are missing required fields or whose URIs
        point at official Ubuntu infrastructure.

        :param stanza: A single parsed DEB822 paragraph.
        :type stanza: Deb822
        :param path: Source file path (stored on the returned Repository).
        :type path: Path
        :returns: Populated Repository, or None if the stanza should be ignored.
        :rtype: Repository | None
        """
        types_raw = stanza.get("Types", "").split()
        uris_raw = stanza.get("URIs", "").split()
        suites = stanza.get("Suites", "").split()
        components = stanza.get("Components", "").split()

        if not types_raw or not uris_raw or not suites:
            return None
        if _is_official_ubuntu(uris_raw):
            return None

        enabled_val = stanza.get("Enabled", "yes").strip().lower()
        enabled = enabled_val not in ("no", "false", "0")

        # X-Repolib-Name is what software-properties-gtk writes; fall back to Description
        description = stanza.get("X-Repolib-Name", "").strip() or stanza.get("Description", "").strip() or None
        signed_by = stanza.get("Signed-By", "").strip() or None

        # Preserve architecture restriction — apt accepts both singular and plural field names
        archs_raw = (stanza.get("Architectures") or stanza.get("Architecture") or "").split()

        agnostic = _is_suite_agnostic(suites, self._agnostic_names)

        repo = Repository(
            source_file=path,
            file_format=FileFormat.DEB822,
            types=types_raw,
            uris=uris_raw,
            suites=suites,
            components=components,
            enabled=enabled,
            description=description,
            signed_by=signed_by,
            architectures=archs_raw,
        )
        if agnostic:
            repo.availability = AvailabilityStatus.SUITE_AGNOSTIC
        return repo

    # ------------------------------------------------------------------
    # One-line (.list)
    # ------------------------------------------------------------------

    def _parse_one_line(self, path: Path) -> list[Repository]:
        """Parse a one-line .list file and return all non-official repos found.

        Lines beginning with ``# deb`` or ``#deb`` are surfaced as disabled repos.
        All other comment lines are skipped.

        :param path: Absolute path to the .list file.
        :type path: Path
        :returns: Parsed repositories (may be empty).
        :rtype: list[Repository]
        """
        repos = []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return repos

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            enabled = True
            if stripped.startswith("# deb") or stripped.startswith("#deb"):
                # Commented-out repo — still surface it as disabled
                stripped = stripped.lstrip("#").strip()
                enabled = False
            elif stripped.startswith("#"):
                continue

            repo = self._one_line_to_repo(stripped, path, enabled)
            if repo is not None:
                repos.append(repo)
        return repos

    def _one_line_to_repo(self, line: str, path: Path, enabled: bool) -> Repository | None:
        """Parse a single one-line entry into a Repository, or None to skip it.

        :param line: The source line with any leading ``#`` comment marker already stripped.
        :type line: str
        :param path: Source file path (stored on the returned Repository).
        :type path: Path
        :param enabled: Whether the original line was uncommented (active).
        :type enabled: bool
        :returns: Populated Repository, or None if the line is malformed or official.
        :rtype: Repository | None
        """
        # Format: deb[-src] [options] uri suite [component...]
        parts = line.split()
        if len(parts) < 3:
            return None

        idx = 0
        types = []
        if parts[idx] in ("deb", "deb-src"):
            types.append(parts[idx])
            idx += 1
        else:
            return None

        # Extract signed-by= and arch= from optional [options] block before skipping it
        signed_by: str | None = None
        architectures: list[str] = []
        if idx < len(parts) and parts[idx].startswith("["):
            opts_parts: list[str] = []
            while idx < len(parts):
                token = parts[idx]
                idx += 1
                opts_parts.append(token)
                if token.endswith("]"):
                    break
            opts_str = " ".join(opts_parts).strip("[]")
            for opt in opts_str.split():
                key, _, val = opt.partition("=")
                key_lower = key.lower()
                if key_lower == "signed-by" and val:
                    signed_by = val
                elif key_lower == "arch" and val:
                    architectures = [a.strip() for a in val.split(",") if a.strip()]

        if idx + 2 > len(parts):
            return None

        uri = parts[idx]
        idx += 1
        suite = parts[idx]
        idx += 1
        components = parts[idx:]

        suites = [suite]
        if _is_official_ubuntu([uri]):
            return None
        agnostic = _is_suite_agnostic(suites, self._agnostic_names)

        repo = Repository(
            source_file=path,
            file_format=FileFormat.ONE_LINE,
            types=types,
            uris=[uri],
            suites=suites,
            components=components,
            enabled=enabled,
            description=None,
            signed_by=signed_by,
            architectures=architectures,
        )
        if agnostic:
            repo.availability = AvailabilityStatus.SUITE_AGNOSTIC
        return repo
