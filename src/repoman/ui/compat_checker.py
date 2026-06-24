from __future__ import annotations

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..models import AvailabilityStatus, Repository
from ..upgrade_info import (
    get_all_known_codenames,
    get_current_codename_and_display,
    get_ppa_suites,
    get_upgrade_prompt,
    get_upgrade_targets,
)
from .position import center_on_parent


def _clear_label_selections(popover: Gtk.Popover) -> None:
    """Popover 'show' handler: defer-clear the auto-selection GTK applies on focus."""

    def _do_clear() -> bool:
        stack = [popover.get_child()]
        while stack:
            w = stack.pop()
            if isinstance(w, Gtk.Label) and w.get_selectable():
                w.select_region(0, 0)
            child = w.get_first_child() if hasattr(w, "get_first_child") else None
            while child:
                stack.append(child)
                child = child.get_next_sibling()
        return GLib.SOURCE_REMOVE

    GLib.idle_add(_do_clear)


class CompatCheckerWindow(Gtk.Window):
    """
    Modal window for checking pre-update PPA compatibility.
    Uses Gtk.Window (system titlebar) to match the main window and wizard.
    """

    __gtype_name__ = "CompatCheckerWindow"

    def __init__(self, repos: list[Repository], parent: Gtk.Window) -> None:
        super().__init__(
            title="Pre-update compatibility check",
            modal=True,
            transient_for=parent,
            default_width=520,
            default_height=560,
        )
        self._repos = repos
        self._targets: list[tuple[str, str]] = []
        self._ppa_repos: list[Repository] = []
        self._agnostic_repos: list[Repository] = []
        self._other_repos: list[Repository] = []
        self._pending: int = 0
        self._repo_statuses: dict[int, AvailabilityStatus] = {}
        self._network_error: str | None = None
        self._row_widgets: dict[int, tuple[Adw.ActionRow, Gtk.Widget]] = {}
        self._target_codename: str = ""
        self._current_codename: str = ""
        self._ordered_codenames: list[str] = []
        self._ppa_group: Adw.PreferencesGroup | None = None

        center_on_parent(self)
        self._categorize_repos()
        self._build_ui()
        GLib.idle_add(self._load_system_info)

    def _categorize_repos(self) -> None:
        self._agnostic_repos = [r for r in self._repos if r.availability == AvailabilityStatus.SUITE_AGNOSTIC]
        self._ppa_repos = [r for r in self._repos if r.is_ppa and r.availability != AvailabilityStatus.SUITE_AGNOSTIC]
        self._other_repos = [
            r for r in self._repos if not r.is_ppa and r.availability != AvailabilityStatus.SUITE_AGNOSTIC
        ]

    def _build_ui(self) -> None:
        self._toast_overlay = Adw.ToastOverlay()
        self.set_child(self._toast_overlay)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(outer_box)

        scroll = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        scroll.set_child(content_box)
        outer_box.append(scroll)

        # System info group
        system_group = Adw.PreferencesGroup(title="System")
        self._current_row = Adw.ActionRow(title="Current release", subtitle="Loading…")
        system_group.add(self._current_row)
        self._upgrade_path_row = Adw.ActionRow(title="Upgrade path", subtitle="Loading…")
        system_group.add(self._upgrade_path_row)
        content_box.append(system_group)

        # Target release group
        target_group = Adw.PreferencesGroup(title="Target release")
        self._combo_row = Adw.ComboRow(title="Check against")
        self._combo_row.connect("notify::selected", self._on_combo_changed)
        target_group.add(self._combo_row)
        content_box.append(target_group)

        # Results stack
        self._results_stack = Gtk.Stack()
        placeholder = Adw.StatusPage(
            icon_name="dialog-question-symbolic",
            title="Select a target release and click Check",
        )
        self._results_stack.add_named(placeholder, "placeholder")
        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._results_stack.add_named(self._results_box, "results")
        self._results_stack.set_visible_child_name("placeholder")
        content_box.append(self._results_stack)

        # Action bar
        outer_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        action_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            margin_top=10,
            margin_bottom=10,
            margin_start=10,
            margin_end=10,
            spacing=8,
        )
        self._check_button = Gtk.Button(
            label="Check compatibility",
            hexpand=True,
            sensitive=False,
        )
        self._check_button.add_css_class("suggested-action")
        self._check_button.connect("clicked", self._on_check_clicked)
        action_bar.append(self._check_button)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _: self.close())
        action_bar.append(close_button)
        outer_box.append(action_bar)

    def _load_system_info(self) -> bool:
        codename, display = get_current_codename_and_display()
        self._current_codename = codename
        self._ordered_codenames = get_all_known_codenames()
        self._current_row.set_subtitle(display)

        prompt = get_upgrade_prompt()
        path_label = {
            "lts": "LTS releases only",
            "normal": "All releases",
            "never": "Never (upgrades disabled)",
        }.get(prompt, prompt)
        self._upgrade_path_row.set_subtitle(path_label)

        self._targets = get_upgrade_targets(codename, prompt)
        if self._targets:
            self._combo_row.set_model(Gtk.StringList.new([t[1] for t in self._targets]))
            self._check_button.set_sensitive(True)
        else:
            tooltip = (
                "Upgrades are configured to never run on this system"
                if prompt == "never"
                else "Could not read Ubuntu version list"
            )
            self._check_button.set_tooltip_text(tooltip)

        return GLib.SOURCE_REMOVE

    def _on_combo_changed(self, _combo_row: Adw.ComboRow, _param) -> None:
        self._results_stack.set_visible_child_name("placeholder")
        self._clear_results()

    def _on_check_clicked(self, _button: Gtk.Button) -> None:
        idx = self._combo_row.get_selected()
        if not self._targets or idx >= len(self._targets):
            return
        target_codename = self._targets[idx][0]
        self._check_button.set_label("Checking…")
        self._check_button.set_sensitive(False)
        self._clear_results()
        self._build_result_groups(target_codename)
        self._results_stack.set_visible_child_name("results")
        self._start_checks(target_codename)

    def _clear_results(self) -> None:
        while child := self._results_box.get_first_child():
            self._results_box.remove(child)
        self._row_widgets = {}
        self._ppa_group = None

    def _make_repo_row(self, repo: Repository) -> Adw.ActionRow:
        """ActionRow for a repo — italic + dimmed when disabled."""
        name = GLib.markup_escape_text(repo.display_name)
        row = Adw.ActionRow(
            title=f"<i>{name}</i>" if not repo.enabled else name,
            subtitle=repo.uris[0] if repo.uris else "",
        )
        if not repo.enabled:
            row.add_css_class("dim-label")
        return row

    def _build_result_groups(self, target_codename: str) -> None:
        if self._ppa_repos:
            self._ppa_group = Adw.PreferencesGroup(
                title=f"PPA repositories ({len(self._ppa_repos)})",
                description=f"Checking against {target_codename}…",
            )
            for repo in self._ppa_repos:
                row = self._make_repo_row(repo)
                spinner = Gtk.Spinner(spinning=True)
                row.add_suffix(spinner)
                self._ppa_group.add(row)
                self._row_widgets[id(repo)] = (row, spinner)
            self._results_box.append(self._ppa_group)

        if self._agnostic_repos:
            agnostic_group = Adw.PreferencesGroup(
                title=f"Suite-agnostic — always compatible ({len(self._agnostic_repos)})",
            )
            for repo in self._agnostic_repos:
                row = self._make_repo_row(repo)
                row.add_suffix(Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic"))
                agnostic_group.add(row)
            self._results_box.append(agnostic_group)

        if self._other_repos:
            other_group = Adw.PreferencesGroup(
                title=f"Non-PPA repositories ({len(self._other_repos)})",
                description="Manual check recommended for non-PPA repositories",
            )
            for repo in self._other_repos:
                row = self._make_repo_row(repo)
                row.add_suffix(Gtk.Image.new_from_icon_name("dialog-question-symbolic"))
                other_group.add(row)
            self._results_box.append(other_group)

    def _start_checks(self, target_codename: str) -> None:
        self._target_codename = target_codename
        self._pending = len(self._ppa_repos)
        self._repo_statuses = {}
        self._network_error = None
        if self._pending == 0:
            self._on_all_checks_done(target_codename)
            return
        threading.Thread(target=self._run_checks, args=(target_codename,), daemon=True).start()

    def _run_checks(self, target_codename: str) -> None:
        for repo in self._ppa_repos:
            if not repo.ppa_owner or not repo.ppa_name:
                GLib.idle_add(
                    self._on_row_checked,
                    repo,
                    AvailabilityStatus.UNKNOWN,
                    "Could not parse PPA from URI",
                    None,
                )
                continue
            suites, error = get_ppa_suites(repo.ppa_owner, repo.ppa_name)
            if suites is None:
                status = AvailabilityStatus.UNKNOWN
            elif target_codename in suites:
                status = AvailabilityStatus.AVAILABLE
            else:
                status = AvailabilityStatus.UNAVAILABLE
            GLib.idle_add(self._on_row_checked, repo, status, error, suites)

    def _on_row_checked(
        self,
        repo: Repository,
        status: AvailabilityStatus,
        error: str | None,
        suites: frozenset[str] | None,
    ) -> bool:
        row_widget = self._row_widgets.get(id(repo))
        if row_widget is not None:
            row, spinner = row_widget
            row.remove(spinner)
            row.add_suffix(self._make_status_button(repo, status, error, self._target_codename, suites))

        if error and not self._network_error:
            self._network_error = error
        self._repo_statuses[id(repo)] = status
        self._pending -= 1
        if self._pending == 0:
            self._on_all_checks_done(self._target_codename)
        return GLib.SOURCE_REMOVE

    def _make_status_button(
        self,
        repo: Repository,
        status: AvailabilityStatus,
        error: str | None,
        target_codename: str,
        suites: frozenset[str] | None,
    ) -> Gtk.MenuButton:
        """Clickable status icon that opens a detail popover."""
        icon_name, css = {
            AvailabilityStatus.AVAILABLE: ("emblem-ok-symbolic", "success"),
            AvailabilityStatus.UNAVAILABLE: ("dialog-warning-symbolic", "warning"),
        }.get(status, ("dialog-question-symbolic", ""))

        icon = Gtk.Image.new_from_icon_name(icon_name)
        if css:
            icon.add_css_class(css)

        btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
        btn.set_child(icon)
        btn.add_css_class("flat")
        btn.add_css_class("circular")

        content = self._make_popover_content(repo, status, error, target_codename, suites)
        popover = Gtk.Popover(child=content)
        popover.connect("show", _clear_label_selections)
        btn.set_popover(popover)

        return btn

    def _make_popover_content(
        self,
        repo: Repository,
        status: AvailabilityStatus,
        error: str | None,
        target_codename: str,
        suites: frozenset[str] | None,
    ) -> Gtk.Box:
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=10,
            margin_bottom=10,
            margin_start=12,
            margin_end=12,
        )

        # Status headline
        if status == AvailabilityStatus.AVAILABLE:
            headline = f"Repo is ready for {target_codename}"
        elif status == AvailabilityStatus.UNAVAILABLE:
            headline = f"Not yet available for {target_codename}"
        else:
            headline = error or "Could not determine availability"

        msg = Gtk.Label(label=headline, xalign=0, wrap=True, max_width_chars=36)
        msg.add_css_class("body")
        box.append(msg)

        box.append(Gtk.Separator())

        # Suite detail
        current_suite = repo.suites[0] if repo.suites else "?"
        for label_text in (
            f"Current suite:  {current_suite}",
            f"Checking for:  {target_codename}",
        ):
            lbl = Gtk.Label(label=label_text, xalign=0, selectable=True, css_classes=["caption"])
            box.append(lbl)

        # Enrichment for UNAVAILABLE: show latest known available suite
        if status == AvailabilityStatus.UNAVAILABLE and suites is not None:
            known_available = [c for c in self._ordered_codenames if c in suites]
            if known_available:
                latest = known_available[-1]
                try:
                    current_idx = self._ordered_codenames.index(self._current_codename)
                    latest_idx = self._ordered_codenames.index(latest)
                    if latest_idx > current_idx:
                        detail = f"Latest available: {latest}"
                    else:
                        detail = f"Last available: {latest}"
                except ValueError:
                    detail = f"Latest available: {latest}"
            else:
                detail = "No packages found for any Ubuntu release"
            lbl = Gtk.Label(
                label=detail, xalign=0, wrap=True, max_width_chars=36, selectable=True, css_classes=["caption"]
            )
            box.append(lbl)

        # Launchpad link
        if repo.ppa_owner and repo.ppa_name:
            box.append(Gtk.Separator())
            url = f"https://launchpad.net/~{repo.ppa_owner}/+archive/ubuntu/{repo.ppa_name}"
            link = Gtk.Label(
                label=f'<a href="{url}">Open on Launchpad ↗</a>',
                use_markup=True,
                xalign=0,
            )
            box.append(link)

        return box

    def _on_all_checks_done(self, target_codename: str) -> None:
        if self._ppa_group and self._ppa_repos:
            available = sum(1 for s in self._repo_statuses.values() if s == AvailabilityStatus.AVAILABLE)
            self._ppa_group.set_description(f"{available} of {len(self._ppa_repos)} available for {target_codename}")
        self._check_button.set_label("Check compatibility")
        self._check_button.set_sensitive(True)
        if self._network_error:
            self._toast_overlay.add_toast(Adw.Toast(title=f"Network error: {self._network_error}", timeout=6))
