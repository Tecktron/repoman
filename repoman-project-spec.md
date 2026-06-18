# repoman — project specification & development handoff

> **Context for Claude Code:** This document is the complete design record for
> `repoman`, a GTK4/libadwaita APT repository manager for Ubuntu/Xubuntu.
> Everything here was designed in a planning session. Your job is to materialise
> what is missing, wire it together, debug it on a live Xubuntu 24.04 system,
> and produce a fully working installable `.deb` package.

---

## 1. Project overview

`repoman` solves a specific pain point: Ubuntu/Xubuntu upgrades disable all
third-party APT repositories (PPAs and others), wipe any comments the user
added to identify them, and leave no easy path to reviewing and re-enabling
them for the new release. Existing tools (Y PPA Manager, Aptik) are abandoned
and non-functional on modern Ubuntu.

**The name is intentional.** "Repo Man" as in repossessing your repos after an
upgrade. Also the 1984 film.

---

## 2. Design goals

- Manage all APT third-party repositories (PPAs and non-Launchpad) from a
  single GTK4 GUI.
- Persist human-readable descriptions for each repo using the DEB822
  `Description:` field — no sidecar database.
- Auto-convert legacy `.list` format repos to DEB822 `.sources` on first
  description save.
- On startup, detect repos that were disabled or have a stale codename after an
  upgrade and surface a non-intrusive banner.
- Provide an upgrade assistant wizard that checks availability of disabled repos
  against the new release and re-enables them in bulk via a single polkit prompt.
- Never run the GUI as root. A minimal privileged helper handles all file writes.
- Minimum platform: **Xubuntu 24.04 LTS** (libadwaita 1.4.2).
- Written to be open-source-releasable from day one (clean code, separate
  classes, base classes to reduce boilerplate).

---

## 3. Tech stack

| Concern | Choice | Package |
|---|---|---|
| Language | Python 3.12 | pre-installed |
| UI toolkit | GTK4 + libadwaita 1.4 | `python3-gi`, `gir1.2-adw-1` |
| APT source parsing | python-apt | `python3-apt` |
| DEB822 format r/w | python-debian | `python3-debian` |
| Launchpad PPA checks | launchpadlib | `python3-launchpadlib` |
| Non-PPA HTTP checks | requests | `python3-requests` |
| Privileged writes | pkexec + polkit policy | `policykit-1` |
| Threading / UI safety | `threading` + `GLib.idle_add()` | built-in |
| Build / packaging | setuptools + debhelper | `python3-setuptools`, `debhelper` |

---

## 4. Minimum platform requirements

| Ubuntu | libadwaita | `AdwNavigationView` | `AdwBanner` | Status |
|---|---|---|---|---|
| 22.04 LTS | 1.0–1.1 | ✗ | ✗ | Out |
| 22.10 | 1.2.x | ✗ | ✗ | Out |
| 23.04 | 1.3.x | ✗ | ✓ | Out |
| 23.10 | 1.4.x | ✓ | ✓ | Technical min (EOL) |
| **24.04 LTS** | **1.4.2** | **✓** | **✓** | **Practical minimum** |

**Critical:** `Adw.Dialog` (introduced in libadwaita 1.5) is **not used**.
The upgrade wizard uses `Adw.Window(modal=True)` instead, which works on 1.4.x.

---

## 5. Architecture

```
┌─────────────────────────────────────────────┐
│              GTK4 / libadwaita UI           │
│  MainWindow  │  DetailPane  │  WizardDialog │
└──────────────┬──────────────┬───────────────┘
               │              │
    ┌──────────▼──────────────▼──────────┐
    │           Service layer            │
    │  Parser  │  Checker  │  Writer     │
    └──────────┬──────────────┬──────────┘
               │              │ (via pkexec)
    ┌──────────▼──────────────▼──────────┐
    │           Data / external          │
    │ sources.list.d │ Launchpad + HTTP  │
    │ update-manager │                   │
    └────────────────────────────────────┘
```

**Threading rule:** The GTK main thread owns all widget state. Background
threads (checker, polkit subprocess) communicate back exclusively via
`GLib.idle_add()`. Violating this causes silent corruption or crashes.

---

## 6. Full project structure

```
repoman/
├── src/
│   └── repoman/
│       ├── __init__.py
│       ├── main.py                  # Adw.Application entry point
│       ├── models.py                # Repository, WizardState, enums  ✓ WRITTEN
│       ├── parser.py                # Reads /etc/apt/sources.list.d/   ✗ NEEDED
│       ├── converter.py             # .list → DEB822 .sources           ✗ NEEDED
│       ├── checker.py               # Launchpad API + HTTP InRelease    ✗ NEEDED
│       ├── writer.py                # Builds DEB822 content (no I/O)   ✗ NEEDED
│       ├── utils.py                 # get_current_codename(), etc.      ✗ NEEDED
│       └── ui/
│           ├── __init__.py
│           ├── main_window.py       # AdwApplicationWindow              ✗ NEEDED
│           ├── repo_row.py          # AdwActionRow subclass             ✗ NEEDED
│           ├── detail_pane.py       # Right-hand edit panel             ✗ NEEDED
│           └── wizard/
│               ├── __init__.py
│               ├── dialog.py        # RepomanWizardDialog               ✓ WRITTEN
│               ├── base_page.py     # RepomanWizardPage base class      ✓ WRITTEN
│               ├── select_page.py   # Step 1 — select repos             ✓ WRITTEN
│               ├── check_page.py    # Step 2 — check availability       ✓ WRITTEN
│               └── confirm_page.py  # Step 3 — confirm + apply          ✓ WRITTEN
├── data/
│   ├── io.github.Tecktron.repoman.desktop    ✗ NEEDED
│   ├── io.github.Tecktron.repoman.policy     ✓ WRITTEN
│   ├── io.github.Tecktron.repoman.gschema.xml ✗ NEEDED
│   └── icons/
│       └── hicolor/
│           └── scalable/
│               └── apps/
│                   └── io.github.Tecktron.repoman.svg  ✗ NEEDED
├── tests/
│   ├── fixtures/
│   │   ├── sample_ppa.sources       # DEB822 PPA example
│   │   ├── sample_third_party.sources
│   │   └── sample_legacy.list       # Old .list format
│   ├── test_parser.py               ✗ NEEDED
│   ├── test_converter.py            ✗ NEEDED
│   └── test_checker.py              ✗ NEEDED
├── polkit-helper                    # The privileged writer             ✓ WRITTEN
├── pyproject.toml                   ✗ NEEDED
├── MANIFEST.in                      ✗ NEEDED
├── LICENSE                          # GPL-3.0
├── README.md
└── debian/
    ├── control                      ✗ NEEDED
    ├── rules                        ✗ NEEDED
    ├── changelog                    ✗ NEEDED
    ├── copyright                    ✗ NEEDED
    ├── install                      ✗ NEEDED
    └── postinst                     ✗ NEEDED
```

**App ID:** `io.github.Tecktron.repoman`, matching the GitHub account at
github.com/Tecktron. This ID is used consistently across the polkit policy,
GSettings schema, desktop file, and icon name — they must all match exactly.

---

## 7. Data models (`src/repoman/models.py`) ✓

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable


class FileFormat(Enum):
    DEB822   = auto()   # .sources
    ONE_LINE = auto()   # .list — auto-converted on first description save


class AvailabilityStatus(Enum):
    UNKNOWN         = auto()   # not yet checked
    CHECKING        = auto()   # in progress
    AVAILABLE       = auto()   # confirmed for target release
    UNAVAILABLE     = auto()   # confirmed not available
    SUITE_AGNOSTIC  = auto()   # "stable"-style URL, always passes


@dataclass
class Repository:
    source_file:  Path
    file_format:  FileFormat
    types:        list[str]        # ["deb"] or ["deb", "deb-src"]
    uris:         list[str]
    suites:       list[str]        # ["noble"] or ["stable"] for suite-agnostic
    components:   list[str]
    enabled:      bool
    description:  str | None       # Description: field; None → show URI as fallback
    signed_by:    str | None

    # Derived — not stored in file
    is_ppa:       bool = field(init=False)
    ppa_owner:    str | None = field(init=False)
    ppa_name:     str | None = field(init=False)
    availability: AvailabilityStatus = AvailabilityStatus.UNKNOWN

    def __post_init__(self) -> None:
        uri = self.uris[0] if self.uris else ""
        self.is_ppa = (
            "ppa.launchpadcontent.net" in uri
            or "ppa.launchpad.net" in uri
        )
        if self.is_ppa:
            # https://ppa.launchpadcontent.net/{owner}/{ppa}/ubuntu
            parts = uri.rstrip("/").split("/")
            self.ppa_owner = parts[-3] if len(parts) >= 3 else None
            self.ppa_name  = parts[-2] if len(parts) >= 2 else None
        else:
            self.ppa_owner = self.ppa_name = None

    @property
    def display_name(self) -> str:
        if self.description:
            return self.description
        return self.uris[0] if self.uris else "(unknown)"


@dataclass
class WizardState:
    candidate_repos: list[Repository]
    target_codename: str
    selected:        list[Repository] = field(default_factory=list)
    on_complete:     Callable[[], None] | None = None
```

---

## 8. Components — specifications for Claude Code to implement

### 8.1 `utils.py` ✗

```python
import subprocess
from .models import Repository, AvailabilityStatus


def get_current_codename() -> str:
    """Return the running Ubuntu codename, e.g. 'noble'."""
    r = subprocess.run(["lsb_release", "-cs"], capture_output=True, text=True)
    return r.stdout.strip()


def repos_needing_attention(repos: list[Repository]) -> list[Repository]:
    """
    Return repos that need review. Catches two cases:
      1. Disabled repos (Enabled: no).
      2. Enabled repos pointing at a stale codename — these appear healthy
         but silently 404 on every `apt update`. This is the case most
         tools miss.

    Excludes suite-agnostic repos ('stable', 'main', anything non-alphabetic
    like 'focal-security') — those don't need a codename update.
    """
    current = get_current_codename()
    flagged = []
    for repo in repos:
        if not repo.enabled:
            flagged.append(repo)
            continue
        for suite in repo.suites:
            is_release_codename = suite.isalpha() and suite.islower()
            if is_release_codename and suite != current:
                flagged.append(repo)
                break
    return flagged
```

### 8.2 `parser.py` ✗

Must handle **both** DEB822 (`.sources`) and one-line (`.list`) formats.
Use `python3-apt`'s `aptsources.sourceslist` for `.list` files and
`python3-debian`'s `debian.deb822.Deb822` for `.sources` files.

Key behaviours:
- Scan `/etc/apt/sources.list.d/` only (not `/etc/apt/sources.list` — that is
  managed by the OS and should not be touched).
- Skip files that are not `.sources` or `.list` (e.g. `.list.save`, `.bak`).
- Parse the `Description:` field if present; set to `None` if absent.
- Detect suite-agnostic repos: if all suites are non-alphabetic or are
  known fixed strings like `stable`, `main`, `testing`, set
  `availability = AvailabilityStatus.SUITE_AGNOSTIC`.
- Return a `list[Repository]` sorted by `display_name`.

### 8.3 `converter.py` ✗

Converts a `.list` format `Repository` to a DEB822 `.sources` file.

Behaviour:
- Called when the user saves a description on a `.list`-format repo.
- Constructs the DEB822 stanza as a string using `debian.deb822.Deb822`.
- The new `.sources` filename mirrors the old `.list` filename
  (e.g. `docker.list` → `docker.sources`).
- Does NOT write to disk itself — returns `(new_path, content)` for the
  polkit helper to write.
- After successful write, the original `.list` file must be deleted (also
  via the helper — it's in the same privileged directory).
- Updates the in-memory `Repository` object: `source_file`, `file_format`.

### 8.4 `checker.py` ✗

Checks whether a repo has packages available for a given Ubuntu codename.
Called from a background thread — must not touch GTK.

```python
class Checker:
    def check(self, repo: Repository, codename: str) -> AvailabilityStatus:
        if repo.availability == AvailabilityStatus.SUITE_AGNOSTIC:
            return AvailabilityStatus.SUITE_AGNOSTIC
        if repo.is_ppa:
            return self._check_launchpad(repo, codename)
        return self._check_http(repo, codename)

    def _check_launchpad(self, repo: Repository, codename: str) -> AvailabilityStatus:
        """
        Use launchpadlib to query whether the PPA has published sources
        for the given distro series.
        API: https://api.launchpad.net/1.0/~{owner}/+archive/{ppa}
        Check for published sources with distro_series matching codename.
        """
        ...

    def _check_http(self, repo: Repository, codename: str) -> AvailabilityStatus:
        """
        HEAD request to {uri}/dists/{codename}/InRelease.
        200 → AVAILABLE, 404 → UNAVAILABLE, timeout/error → UNKNOWN.
        Timeout: 10 seconds. Do not follow redirects blindly.
        Watch for repos using suite names other than codenames ('stable' etc.)
        — those should already be SUITE_AGNOSTIC before reaching here.
        """
        ...
```

### 8.5 `writer.py` ✗

Pure functions — no I/O, no root, fully unit-testable.

```python
from debian.deb822 import Deb822
from .models import Repository


def repo_to_deb822(repo: Repository) -> str:
    """
    Serialise a Repository back to a DEB822 string.
    Called by the polkit helper — never directly.
    Preserves all existing fields; updates Enabled:, Suites:, Description:.
    """
    ...


def enable_patch(repo: Repository, codename: str) -> dict:
    """
    Return a dict of field updates needed to re-enable a repo for `codename`.
    {"Enabled": "yes", "Suites": codename}
    """
    ...
```

### 8.6 `main.py` ✗

```python
import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio
from .ui.main_window import RepomanWindow


class RepomanApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.Tecktron.repoman",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)

    def _on_activate(self, app: Adw.Application) -> None:
        win = RepomanWindow(application=app)
        win.present()


def main() -> None:
    app = RepomanApplication()
    app.run()


if __name__ == "__main__":
    main()
```

---

## 9. UI components — specifications for Claude Code to implement

### 9.1 `ui/main_window.py` ✗

`RepomanWindow(Adw.ApplicationWindow)`:

- Left panel: `AdwNavigationSidebar` or plain `Gtk.ListBox` showing
  `RepoRow` items (one per `Repository`).
- Right panel: `DetailPane` — shows the selected repo's fields for editing.
- Top: `AdwHeaderBar` with title "repoman", a search button, and a menu
  button (`Gio.Menu`) with entries:
  - "Upgrade assistant…" → `open_upgrade_wizard()`
  - separator
  - "About repoman" → `Adw.AboutDialog`
- Below header: `AdwBanner` (initially hidden, revealed when
  `repos_needing_attention()` returns results on startup).
- Banner button label: "Review" → calls `open_upgrade_wizard()`.

Startup sequence:
```python
def _on_startup(self) -> None:
    self._repos = self._parser.load_all()
    attention = repos_needing_attention(self._repos)
    if attention:
        n = len(attention)
        self._banner.set_title(
            f"{n} {'repository' if n == 1 else 'repositories'} "
            f"need review after upgrade"
        )
        self._banner.set_button_label("Review")
        self._banner.set_revealed(True)

def open_upgrade_wizard(self) -> None:
    if self._wizard and self._wizard.get_visible():
        self._wizard.present()
        return

    attention = repos_needing_attention(self._repos)
    if not attention:
        dialog = Adw.AlertDialog.new(
            "All repositories are current",
            "Every repository is enabled and pointing at the correct release.",
        )
        dialog.add_response("ok", "OK")
        dialog.present(self)
        return

    self._wizard = RepomanWizardDialog(repos=attention, parent=self)
    self._wizard.connect("repos-updated", self._on_repos_updated)
    self._wizard.connect("closed", lambda _: setattr(self, "_wizard", None))
    self._wizard.present()

def _on_repos_updated(self, _dialog) -> None:
    self._repos = self._parser.load_all()
    self._repo_list.refresh(self._repos)
    if not repos_needing_attention(self._repos):
        self._banner.set_revealed(False)
```

### 9.2 `ui/repo_row.py` ✗

`RepoRow(Adw.ActionRow)` — one row in the sidebar list.

- Title: `repo.display_name`
- Subtitle: `repo.uris[0]` (always show URI as subtitle even when
  description is set, for identification)
- Suffix: availability badge (`Gtk.Label` with CSS class `success`/`warning`)
- Prefix: `Gtk.Switch` for enable/disable (triggers polkit write on toggle)
- Rows for disabled repos should have a visual indicator — add CSS class
  `dim-label` to the subtitle, or a left-side warning icon.

### 9.3 `ui/detail_pane.py` ✗

`DetailPane(Gtk.Box)` — right-hand editing panel.

Fields displayed (all editable):
- Description (`Gtk.Entry`) — the `Description:` field
- URI (read-only `Gtk.Label` — changing URIs is out of scope for MVP)
- Suite / codename (`Gtk.Entry`)
- Components (`Gtk.Entry`)
- Enabled (`Gtk.Switch`)
- Format (read-only: "DEB822 (.sources)" or "One-line (.list) — will convert
  on save")
- File path (read-only `Gtk.Label`, small/dim)

"Save changes" button:
- Calls `writer.repo_to_deb822()` to get new file content.
- If `file_format == FileFormat.ONE_LINE`, calls `converter` first, then
  queues a delete of the old `.list` file.
- Invokes polkit helper with the write payload.
- On success, refreshes the row in the list.

---

## 10. Wizard — all pages written ✓

### `wizard/base_page.py` ✓

```python
from __future__ import annotations
import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk
from ..models import WizardState


class RepomanWizardPage(Adw.NavigationPage):
    """
    Base class for all repoman upgrade wizard pages.

    Subclasses must implement:
        _on_proceed()  — called when Next is clicked and can_proceed() is True
        can_proceed()  — controls Next button sensitivity (default: True)

    Subclasses may override:
        _on_shown()    — called when page is pushed onto the nav stack

    Subclasses use:
        self._content_box   — Gtk.Box to append page-specific widgets into
        self._next_button   — Gtk.Button; call set_label() to relabel
        self.refresh_proceed() — call when can_proceed() state changes
    """

    __gtype_name__ = "RepomanWizardPage"

    def __init__(
        self,
        state: WizardState,
        nav_view: Adw.NavigationView,
        title: str,
        tag: str,
        next_label: str = "Next",
        **kwargs,
    ) -> None:
        super().__init__(title=title, tag=tag, **kwargs)
        self._state = state
        self._nav_view = nav_view

        toolbar_view = Adw.ToolbarView()
        self.set_child(toolbar_view)
        toolbar_view.add_top_bar(Adw.HeaderBar())

        scroll = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        self._content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        scroll.set_child(self._content_box)
        toolbar_view.set_content(scroll)

        action_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=8,
        )
        self._next_button = Gtk.Button(label=next_label, hexpand=True)
        self._next_button.add_css_class("suggested-action")
        self._next_button.connect("clicked", self._handle_next_clicked)
        action_bar.append(self._next_button)
        toolbar_view.add_bottom_bar(action_bar)

        self.connect("shown", lambda _: self._on_shown())

    def can_proceed(self) -> bool:
        return True

    def _on_proceed(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement _on_proceed()")

    def _on_shown(self) -> None:
        pass

    def refresh_proceed(self) -> None:
        self._next_button.set_sensitive(self.can_proceed())

    def _handle_next_clicked(self, _button: Gtk.Button) -> None:
        if self.can_proceed():
            self._on_proceed()
```

### `wizard/select_page.py` ✓

```python
from __future__ import annotations
from gi.repository import Adw, Gtk
from .base_page import RepomanWizardPage
from ..models import Repository, AvailabilityStatus, WizardState


class SelectReposPage(RepomanWizardPage):
    """
    Step 1 — user selects which repos to re-enable.
    Pre-ticks everything except confirmed UNAVAILABLE.
    Unavailable repos stay visible and tickable — user may know better.
    """

    __gtype_name__ = "RepomanSelectReposPage"

    def __init__(self, state: WizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Select repositories",
            tag="select",
            next_label="Check availability",
            **kwargs,
        )
        self._checks: dict[int, tuple[Repository, Gtk.CheckButton]] = {}
        self._build_ui()
        self.refresh_proceed()

    def can_proceed(self) -> bool:
        return any(cb.get_active() for _, cb in self._checks.values())

    def _on_proceed(self) -> None:
        self._state.selected = [
            repo for repo, cb in self._checks.values() if cb.get_active()
        ]
        from .check_page import CheckAvailabilityPage
        self._nav_view.push(
            CheckAvailabilityPage(state=self._state, nav_view=self._nav_view)
        )

    def _build_ui(self) -> None:
        subtitle = Gtk.Label(
            label=(
                f"{len(self._state.candidate_repos)} repositories need review "
                f"for {self._state.target_codename}"
            ),
            wrap=True,
            xalign=0,
        )
        subtitle.add_css_class("dim-label")
        self._content_box.append(subtitle)

        group = Adw.PreferencesGroup()
        self._content_box.append(group)

        for repo in self._state.candidate_repos:
            row = Adw.ActionRow(
                title=repo.display_name,
                subtitle=repo.uris[0] if repo.uris else "",
            )
            check = Gtk.CheckButton(
                active=(repo.availability != AvailabilityStatus.UNAVAILABLE)
            )
            check.connect("toggled", lambda _cb: self.refresh_proceed())
            row.add_prefix(check)
            row.set_activatable_widget(check)
            row.add_suffix(self._status_icon(repo))
            group.add(row)
            self._checks[id(repo)] = (repo, check)

    @staticmethod
    def _status_icon(repo: Repository) -> Gtk.Widget:
        if repo.availability in (AvailabilityStatus.UNKNOWN, AvailabilityStatus.CHECKING):
            return Gtk.Spinner(spinning=True)
        icon_name, css = {
            AvailabilityStatus.AVAILABLE:      ("emblem-ok-symbolic",            "success"),
            AvailabilityStatus.UNAVAILABLE:    ("dialog-warning-symbolic",       "warning"),
            AvailabilityStatus.SUITE_AGNOSTIC: ("emblem-synchronizing-symbolic", ""),
        }.get(repo.availability, ("dialog-question-symbolic", ""))
        icon = Gtk.Image.new_from_icon_name(icon_name)
        if css:
            icon.add_css_class(css)
        return icon
```

### `wizard/check_page.py` ✓

```python
from __future__ import annotations
import threading
from gi.repository import Adw, Gtk, GLib
from .base_page import RepomanWizardPage
from ..models import Repository, AvailabilityStatus, WizardState
from ..checker import Checker


class CheckAvailabilityPage(RepomanWizardPage):
    """
    Step 2 — background thread runs availability checks; rows update live.
    Next is locked until all checks resolve.
    Checks start in _on_shown() so the spinner renders before work begins.
    """

    __gtype_name__ = "RepomanCheckAvailabilityPage"

    def __init__(self, state: WizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Checking availability",
            tag="check",
            **kwargs,
        )
        self._checker = Checker()
        self._row_widgets: dict[int, tuple[Adw.ActionRow, Gtk.Spinner]] = {}
        self._pending = len(self._state.selected)
        self._next_button.set_sensitive(False)
        self._build_ui()

    def can_proceed(self) -> bool:
        return self._pending == 0

    def _on_shown(self) -> None:
        threading.Thread(target=self._run_checks, daemon=True).start()

    def _on_proceed(self) -> None:
        from .confirm_page import ConfirmChangesPage
        self._nav_view.push(
            ConfirmChangesPage(state=self._state, nav_view=self._nav_view)
        )

    def _build_ui(self) -> None:
        self._group = Adw.PreferencesGroup(
            title="Repositories",
            description=(
                f"Checking {len(self._state.selected)} repos "
                f"against {self._state.target_codename}"
            ),
        )
        self._content_box.append(self._group)
        for repo in self._state.selected:
            row = Adw.ActionRow(
                title=repo.display_name,
                subtitle=repo.uris[0] if repo.uris else "",
            )
            spinner = Gtk.Spinner(spinning=True)
            row.add_suffix(spinner)
            self._group.add(row)
            self._row_widgets[id(repo)] = (row, spinner)

    def _run_checks(self) -> None:
        """Background thread only. Never touch GTK widgets here."""
        for repo in self._state.selected:
            status = self._checker.check(repo, self._state.target_codename)
            repo.availability = status
            GLib.idle_add(self._update_row, repo, status)

    def _update_row(self, repo: Repository, status: AvailabilityStatus) -> bool:
        """GTK main thread — called via idle_add. Must return GLib.SOURCE_REMOVE."""
        row, spinner = self._row_widgets.get(id(repo), (None, None))
        if row is None:
            return GLib.SOURCE_REMOVE
        row.remove(spinner)
        icon_name, css = {
            AvailabilityStatus.AVAILABLE:      ("emblem-ok-symbolic",            "success"),
            AvailabilityStatus.UNAVAILABLE:    ("dialog-warning-symbolic",       "warning"),
            AvailabilityStatus.SUITE_AGNOSTIC: ("emblem-synchronizing-symbolic", ""),
        }.get(status, ("dialog-question-symbolic", ""))
        icon = Gtk.Image.new_from_icon_name(icon_name)
        if css:
            icon.add_css_class(css)
        row.add_suffix(icon)
        self._pending -= 1
        if self._pending == 0:
            available = sum(
                1 for r in self._state.selected
                if r.availability == AvailabilityStatus.AVAILABLE
            )
            self._group.set_description(
                f"{available} of {len(self._state.selected)} "
                f"available for {self._state.target_codename}"
            )
            self.refresh_proceed()
        return GLib.SOURCE_REMOVE
```

### `wizard/confirm_page.py` ✓

```python
from __future__ import annotations
import json
import subprocess
import threading
from gi.repository import Adw, Gtk, GLib
from .base_page import RepomanWizardPage
from ..models import Repository, AvailabilityStatus, WizardState


class ConfirmChangesPage(RepomanWizardPage):
    """
    Step 3 — summary and polkit-guarded apply.
    UNAVAILABLE repos are excluded from the write payload even if the user
    ticked them in step 1 — safety net against enabling broken repos.
    """

    __gtype_name__ = "RepomanConfirmChangesPage"
    _HELPER_PATH = "/usr/lib/repoman/polkit-helper"

    def __init__(self, state: WizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Confirm changes",
            tag="confirm",
            next_label="Apply changes",
            **kwargs,
        )
        self._to_apply = [
            r for r in self._state.selected
            if r.availability != AvailabilityStatus.UNAVAILABLE
        ]
        self._build_ui()

    def can_proceed(self) -> bool:
        return bool(self._to_apply)

    def _on_proceed(self) -> None:
        self._next_button.set_sensitive(False)
        self._next_button.set_label("Applying…")
        threading.Thread(target=self._apply, daemon=True).start()

    def _build_ui(self) -> None:
        will_apply_group = Adw.PreferencesGroup(
            title="Will be re-enabled",
            description=f"Suite field updated to {self._state.target_codename}",
        )
        for repo in self._to_apply:
            will_apply_group.add(self._make_row(repo, success=True))
        self._content_box.append(will_apply_group)

        skipped = [
            r for r in self._state.selected
            if r.availability == AvailabilityStatus.UNAVAILABLE
        ]
        if skipped:
            skipped_group = Adw.PreferencesGroup(
                title="Skipped — not yet available for this release"
            )
            for repo in skipped:
                skipped_group.add(self._make_row(repo, success=False))
            self._content_box.append(skipped_group)

        auth_group = Adw.PreferencesGroup()
        auth_row = Adw.ActionRow(
            title="Administrator password required",
            subtitle="Writes to /etc/apt/sources.list.d/",
        )
        auth_row.add_prefix(
            Gtk.Image.new_from_icon_name("system-lock-screen-symbolic")
        )
        auth_group.add(auth_row)
        self._content_box.append(auth_group)

    @staticmethod
    def _make_row(repo: Repository, *, success: bool) -> Adw.ActionRow:
        row = Adw.ActionRow(
            title=repo.display_name,
            subtitle=repo.uris[0] if repo.uris else "",
        )
        icon = Gtk.Image.new_from_icon_name(
            "emblem-ok-symbolic" if success else "dialog-warning-symbolic"
        )
        icon.add_css_class("success" if success else "warning")
        row.add_suffix(icon)
        return row

    def _apply(self) -> None:
        """Background thread. Calls pkexec — blocks until auth resolves."""
        payload = json.dumps({
            "action": "enable_repos",
            "target_codename": self._state.target_codename,
            "repos": [
                {
                    "source_file": str(repo.source_file),
                    "suites": [self._state.target_codename],
                    "enabled": True,
                }
                for repo in self._to_apply
            ],
        })
        result = subprocess.run(
            ["pkexec", self._HELPER_PATH],
            input=payload,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            GLib.idle_add(self._on_success)
        else:
            GLib.idle_add(self._on_failure, result.stderr.strip())

    def _on_success(self) -> bool:
        if self._state.on_complete:
            self._state.on_complete()
        return GLib.SOURCE_REMOVE

    def _on_failure(self, message: str) -> bool:
        toast = Adw.Toast(title=f"Failed to apply: {message}", timeout=5)
        root = self.get_root()
        if hasattr(root, "add_toast"):
            root.add_toast(toast)
        self._next_button.set_label("Apply changes")
        self._next_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE
```

### `wizard/dialog.py` ✓

```python
from __future__ import annotations
from gi.repository import Adw, GObject
from .select_page import SelectReposPage
from ..models import Repository, WizardState
from ..utils import get_current_codename


class RepomanWizardDialog(Adw.Window):
    """
    Upgrade assistant — modal window wrapping AdwNavigationView.

    Uses Adw.Window(modal=True) rather than Adw.Dialog, which requires
    libadwaita 1.5. Adw.Window(modal=True) works on libadwaita 1.4 (24.04).

    Emits:
        repos-updated — after polkit writes succeed; caller must reload repo list
    """

    __gtype_name__ = "RepomanWizardDialog"
    __gsignals__ = {
        "repos-updated": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        repos: list[Repository],
        parent: Adw.ApplicationWindow,
        **kwargs,
    ) -> None:
        super().__init__(
            title="Upgrade assistant",
            modal=True,
            transient_for=parent,
            default_width=480,
            default_height=560,
            **kwargs,
        )
        self._state = WizardState(
            candidate_repos=repos,
            target_codename=get_current_codename(),
            on_complete=self._handle_complete,
        )
        self._nav_view = Adw.NavigationView()
        wrapper = Adw.ToolbarView()
        wrapper.set_content(self._nav_view)
        self.set_content(wrapper)

        first_page = SelectReposPage(state=self._state, nav_view=self._nav_view)
        self._nav_view.add(first_page)
        self._nav_view.push(first_page)

    def _handle_complete(self) -> None:
        self.emit("repos-updated")
        self.close()
```

---

## 11. Polkit helper (`polkit-helper`) ✓

Install to `/usr/lib/repoman/polkit-helper`, mode `0755`.

```python
#!/usr/bin/env python3
"""
Repoman polkit helper.
Reads JSON payload from stdin. Writes only within allowed directories.
Run via pkexec — never call directly as root.
"""
import json
import sys
from pathlib import Path
from debian.deb822 import Deb822

_ALLOWED = frozenset([
    Path("/etc/apt/sources.list.d"),
    Path("/etc/update-manager/release-upgrades.d"),
])


def _safe(path: Path) -> bool:
    try:
        return path.resolve().parent in {p.resolve() for p in _ALLOWED}
    except Exception:
        return False


def _apply(payload: dict) -> None:
    for entry in payload["repos"]:
        path = Path(entry["source_file"])

        if not _safe(path):
            print(f"ERROR: rejected path: {path}", file=sys.stderr)
            sys.exit(1)

        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            sys.exit(1)

        # Write atomically: temp file → validate → rename
        text = path.read_text(encoding="utf-8")
        stanza = Deb822(text)

        if "suites" in entry:
            stanza["Suites"] = " ".join(entry["suites"])
        if "enabled" in entry:
            stanza["Enabled"] = "yes" if entry["enabled"] else "no"
        if "description" in entry:
            stanza["Description"] = entry["description"]

        new_content = str(stanza)

        # Validate before committing
        try:
            Deb822(new_content)
        except Exception as exc:
            print(f"ERROR: invalid DEB822 after edit: {exc}", file=sys.stderr)
            sys.exit(1)

        tmp = path.with_suffix(".tmp")
        tmp.write_text(new_content, encoding="utf-8")
        tmp.rename(path)   # atomic on same filesystem
        print(f"OK: {path}")


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if payload.get("action") != "enable_repos":
        print(f"ERROR: unknown action: {payload.get('action')}", file=sys.stderr)
        sys.exit(1)

    _apply(payload)
```

---

## 12. Polkit policy (`data/io.github.Tecktron.repoman.policy`) ✓

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
  "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
  "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <action id="io.github.Tecktron.repoman.apply">
    <description>Modify APT repository configuration</description>
    <message>Authentication is required to modify repository settings</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/lib/repoman/polkit-helper</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
```

`auth_admin_keep` caches the password for the desktop session — the user is
not reprompted if they open the wizard a second time.

---

## 13. Key behaviours and edge cases

- **Suite-agnostic repos** (Docker, Google Chrome, 1Password): URIs serve all
  Ubuntu versions under a fixed suite name (`stable`, `main`). These should be
  detected at parse time and marked `SUITE_AGNOSTIC`. They never appear in the
  upgrade assistant. Detection heuristic: all suites in the file are
  non-alphabetic-only strings or known fixed names.

- **The silent broken state**: A repo can have `Enabled: yes` in its file but
  still have the old codename (`noble` instead of `plucky`). APT will emit 404s
  on every `apt update`. `repos_needing_attention()` catches this by checking
  enabled repos too, not just disabled ones.

- **`.list` format conversion**: Only triggered when the user saves a
  description on a `.list`-format repo. The conversion produces a `.sources`
  file alongside the old `.list` file, then the helper deletes the `.list`
  file. Both operations are in a single polkit prompt.

- **Threading**: `Checker._run_checks()` runs in a daemon thread. All GTK
  widget mutations go through `GLib.idle_add()`. `subprocess.run(pkexec...)`
  blocks until polkit resolves — also in a daemon thread. The UI remains
  responsive throughout.

- **Wizard re-entry**: If `RepomanWizardDialog` is already open when
  `open_upgrade_wizard()` is called (e.g. user clicks menu while wizard is
  open), `present()` raises the existing window rather than opening a second.

- **Post-apply refresh**: After `_on_success()` is called, the main window
  reloads repos from disk and re-evaluates `repos_needing_attention()`. If the
  list is now empty, the banner is dismissed.

---

## 14. Build configuration

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "repoman"
version = "0.1.0"
description = "GTK4 APT repository manager for Ubuntu/Xubuntu"
readme = "README.md"
license = {text = "GPL-3.0-or-later"}
requires-python = ">=3.10"
dependencies = [
    "PyGObject",
]

[project.scripts]
repoman = "repoman.main:main"

[tool.setuptools.packages.find]
where = ["src"]
```

Runtime dependencies that are system packages (not pip-installable in context):
`python3-apt`, `python3-debian`, `python3-launchpadlib`, `python3-requests`,
`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`.

### GSettings schema (`data/io.github.Tecktron.repoman.gschema.xml`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <schema id="io.github.Tecktron.repoman" path="/io/github/Tecktron/repoman/">
    <key name="window-width" type="i">
      <default>900</default>
    </key>
    <key name="window-height" type="i">
      <default>600</default>
    </key>
    <key name="window-maximized" type="b">
      <default>false</default>
    </key>
  </schema>
</schemalist>
```

### Desktop file (`data/io.github.Tecktron.repoman.desktop`)

```ini
[Desktop Entry]
Name=repoman
Comment=Manage APT repositories
Exec=repoman
Icon=io.github.Tecktron.repoman
Terminal=false
Type=Application
Categories=System;PackageManager;
Keywords=apt;repository;ppa;upgrade;
```

---

## 15. Debian packaging (`debian/`)

### `debian/control`

```
Source: repoman
Section: admin
Priority: optional
Maintainer: Tecktron <software@tecktron.net>
Build-Depends:
 debhelper-compat (= 13),
 dh-python,
 python3-all,
 python3-setuptools
Standards-Version: 4.6.2
Homepage: https://github.com/Tecktron/repoman
Rules-Requires-Root: no

Package: repoman
Architecture: all
Depends:
 ${misc:Depends},
 ${python3:Depends},
 python3-gi,
 python3-gi-cairo,
 gir1.2-gtk-4.0,
 gir1.2-adw-1 (>= 1.4),
 python3-apt,
 python3-debian,
 python3-launchpadlib,
 python3-requests,
 policykit-1
Description: GTK4 APT repository manager for Ubuntu/Xubuntu
 repoman provides a graphical interface for managing third-party APT
 repositories (PPAs and others). It is designed to make the post-upgrade
 workflow of reviewing, updating, and re-enabling repositories painless.
 .
 Features include: DEB822 format annotations that survive upgrades,
 automatic availability checking via the Launchpad API and HTTP,
 and a polkit-guarded bulk re-enable wizard.
```

### `debian/rules`

```makefile
#!/usr/bin/make -f
%:
	dh $@ --with python3 --buildsystem=pybuild
```

### `debian/install`

```
polkit-helper  usr/lib/repoman/
data/*.policy  usr/share/polkit-1/actions/
data/*.desktop usr/share/applications/
data/*.gschema.xml usr/share/glib-2.0/schemas/
data/icons/    usr/share/icons/
```

### `debian/postinst`

```bash
#!/bin/sh
set -e
case "$1" in
  configure)
    # Compile GSettings schemas
    glib-compile-schemas /usr/share/glib-2.0/schemas/ || true
    # Update icon cache
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor/ || true
    # Make helper executable
    chmod 0755 /usr/lib/repoman/polkit-helper
    ;;
esac
#DEBHELPER#
exit 0
```

### `debian/changelog` (initial entry)

```
repoman (0.1.0-1) noble; urgency=low

  * Initial release.

 -- Tecktron <software@tecktron.net>  Sat, 01 Jan 2025 00:00:00 +0000
```

---

## 16. Build order for Claude Code

Follow this sequence to avoid integration problems:

1. Set up project skeleton — create all `__init__.py` files and directory
   structure.
2. `models.py` — already written, just materialise it.
3. `utils.py` — small, no dependencies, needed everywhere.
4. `parser.py` — core, needed before any UI work. Write test fixtures first.
5. `converter.py` — depends on parser understanding of `.list` format.
6. `writer.py` — pure functions, fully unit-testable.
7. `checker.py` — needs internet access during testing; mock in unit tests.
8. `polkit-helper` — materialise, install to correct path, set permissions.
9. Install polkit `.policy` file and restart polkit (`systemctl restart polkit`).
10. `main.py` — entry point.
11. `ui/main_window.py` — skeleton first (empty window that loads and parses).
12. `ui/repo_row.py` — needed by main window.
13. Wire parser into main window, verify repos display correctly.
14. `ui/detail_pane.py` — add after list is working.
15. Wire wizard (already written) into main window's `open_upgrade_wizard()`.
16. End-to-end test: upgrade assistant banner → wizard → apply → verify file
    on disk.
17. `.desktop` file + icon (SVG required, any reasonable package icon).
18. GSettings schema — install and compile.
19. `pyproject.toml` — verify `pip install -e .` works.
20. `debian/` — build with `dpkg-buildpackage -us -uc`, install with `dpkg -i`.
21. Smoke test the installed `.deb` from a clean state.

---

## 17. Testing strategy

**Unit tests** (no root, no GTK, no network):
- `test_parser.py`: parse fixture files; verify `Repository` fields.
- `test_converter.py`: `.list` → `.sources` conversion round-trips.
- `test_writer.py`: `repo_to_deb822()` produces valid DEB822.
- `test_checker.py`: mock `launchpadlib` and `requests`; test all
  `AvailabilityStatus` paths.

**Integration tests** (require real system, run as non-root):
- Parser reads actual `/etc/apt/sources.list.d/` without error.
- `get_current_codename()` returns a non-empty string.
- `repos_needing_attention()` returns sane results.

**Manual tests**:
- Polkit helper rejects paths outside allowed directories.
- Wizard completes end-to-end on a repo with a stale codename.
- Toggle enable/disable in detail pane → verify file change on disk.
- `.list` format repo → save description → verify `.sources` created,
  `.list` deleted.

---

## 18. Future: PPA and main repository

*(To be planned in a follow-up session after the deb package is working.)*

**PPA route:**
- PPA hosted at launchpad.net/~tecktron-studios — create the
  `repoman` archive under `launchpad.net/~tecktron-studios/+archive/ubuntu/repoman`.
- Sign the package with a GPG key registered to the tecktron-studios
  Launchpad identity.
- Upload source package with `dput`.
- Users install via `add-apt-repository ppa:tecktron-studios/repoman`.

**Ubuntu main / universe route:**
- Requires the package to meet Ubuntu packaging standards (lintian clean).
- File an inclusion request via Launchpad.
- A MOTU (Master of the Universe) sponsor reviews and uploads.
- Realistic target: Ubuntu 26.10 or 27.04 universe.

**Xubuntu-specific route:**
- Xubuntu Extras PPA (`ppa:xubuntu-dev/extras`) for semi-official inclusion.
- Requires coordination with the Xubuntu team.
- Potentially bundled as a recommended package in future Xubuntu releases.

---

*End of specification. Everything above `## 16` is the complete design record.
Everything in `## 16` and below is the build roadmap.*
