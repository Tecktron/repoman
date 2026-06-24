from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


class FileFormat(Enum):
    DEB822 = auto()  # .sources
    ONE_LINE = auto()  # .list — auto-converted on first description save


class AvailabilityStatus(Enum):
    UNKNOWN = auto()  # not yet checked
    CHECKING = auto()  # in progress
    AVAILABLE = auto()  # confirmed for target release
    UNAVAILABLE = auto()  # confirmed not available
    SUITE_AGNOSTIC = auto()  # "stable"-style URL, always passes


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
