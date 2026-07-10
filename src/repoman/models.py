"""Data models: Repository, WizardState, FileFormat, and AvailabilityStatus."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


class FileFormat(Enum):
    """On-disk format of an APT source file.

    ONE_LINE repos are automatically converted to DEB822 on the first save
    that sets a description, because the one-line format has no description field.
    """

    DEB822 = auto()  # .sources
    ONE_LINE = auto()  # .list — auto-converted on first description save


class AvailabilityStatus(Enum):
    """Availability of a repository for a target Ubuntu codename.

    CHECKING is an in-progress sentinel used only by the wizard UI — it is
    never written back to the Repository object. The background thread transitions
    directly from UNKNOWN to AVAILABLE, UNAVAILABLE, or (on network failure) UNKNOWN.
    """

    UNKNOWN = auto()  # not yet checked
    CHECKING = auto()  # in progress (wizard UI only — never stored on repo)
    AVAILABLE = auto()  # confirmed for target release
    UNAVAILABLE = auto()  # confirmed not available
    SUITE_AGNOSTIC = auto()  # "stable"-style URL, always passes


# Maps each AvailabilityStatus to (icon_name, css_class) for UI badges.
# UNKNOWN and CHECKING have no badge (handled separately by callers).
AVAILABILITY_ICONS: dict[AvailabilityStatus, tuple[str, str]] = {
    AvailabilityStatus.AVAILABLE: ("tecktron-repoman-available", "success"),
    AvailabilityStatus.UNAVAILABLE: ("dialog-warning-symbolic", "warning"),
    AvailabilityStatus.SUITE_AGNOSTIC: ("locked-symbolic", ""),
}


@dataclass
class Repository:
    """APT source entry parsed from a .sources or .list file."""

    source_file: Path
    file_format: FileFormat
    types: list[str]  # ["deb"] or ["deb", "deb-src"]
    uris: list[str]
    suites: list[str]  # ["noble"] or ["stable"] for suite-agnostic
    components: list[str]
    enabled: bool
    description: str | None  # Description: field; None → show URI as fallback
    signed_by: str | None
    architectures: list[str] = field(default_factory=list)  # Architectures: amd64 arm64 …

    # Derived — not stored in file
    is_ppa: bool = field(init=False)
    ppa_owner: str | None = field(init=False)
    ppa_name: str | None = field(init=False)
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN

    def __post_init__(self) -> None:
        uri = self.uris[0] if self.uris else ""
        self.is_ppa = "ppa.launchpadcontent.net" in uri or "ppa.launchpad.net" in uri
        if self.is_ppa:
            # https://ppa.launchpadcontent.net/{owner}/{ppa}/ubuntu
            parts = uri.rstrip("/").split("/")
            self.ppa_owner = parts[-3] if len(parts) >= 3 else None
            self.ppa_name = parts[-2] if len(parts) >= 2 else None
        else:
            self.ppa_owner = self.ppa_name = None

    @property
    def display_name(self) -> str:
        """Human-readable label: description if set, otherwise the primary URI.

        :returns: Description string, or first URI, or the literal ``(unknown)``
            if the repo has no URIs.
        :rtype: str
        """
        if self.description:
            return self.description
        return self.uris[0] if self.uris else "(unknown)"


@dataclass
class WizardState:
    """Shared state threaded through all upgrade wizard pages."""

    candidate_repos: list[Repository]
    target_codename: str
    selected: list[Repository] = field(default_factory=list)
    on_complete: Callable[[], None] | None = None


@dataclass
class RestoreWizardState:
    """Shared state threaded through all restore wizard pages."""

    saved: list[dict]
    actions: list[str]
    saved_codename: str
    current_codename: str
    live_repos: list[Repository]
    on_complete: Callable[[list[dict]], None] | None = None
