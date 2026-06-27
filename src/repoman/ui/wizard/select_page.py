from __future__ import annotations

import json
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from ... import config_io
from ...models import AvailabilityStatus, Repository, WizardState
from .base_page import RepomanWizardPage


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

    def _on_check_toggled(self) -> None:
        self._update_select_all_btn()
        self.refresh_proceed()

    def _update_select_all_btn(self) -> None:
        all_checked = all(cb.get_active() for _, cb in self._checks.values())
        self._select_all_label.set_label("Deselect all" if all_checked else "Select all")

    def _on_select_all(self, _btn: Gtk.Button) -> None:
        all_checked = all(cb.get_active() for _, cb in self._checks.values())
        for _, cb in self._checks.values():
            cb.set_active(not all_checked)
        self._update_select_all_btn()
        self.refresh_proceed()

    def _on_load_from_file(self, _btn: Gtk.Button) -> None:
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Load selection from state file")
        f = Gtk.FileFilter()
        f.add_pattern("*.repoman")
        f.set_name("Repoman configs (*.repoman)")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dialog.set_filters(store)
        dialog.open(self.get_root(), None, self._on_file_chosen)

    def _on_file_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        path = Path(gfile.get_path())
        try:
            saved = config_io.load_config(path)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            err = Adw.AlertDialog.new("Could not load file", str(exc))
            err.add_response("ok", "OK")
            err.present(self.get_root())
            return
        matched, _ = config_io.match_repos(saved, list(self._state.candidate_repos))
        enabled_uris = {entry["uris"][0] for entry, _ in matched if entry.get("enabled") and entry.get("uris")}
        for repo, cb in self._checks.values():
            cb.set_active(bool(repo.uris) and repo.uris[0] in enabled_uris)
        self._update_select_all_btn()
        self.refresh_proceed()

    def _on_proceed(self) -> None:
        self._state.selected = [repo for repo, cb in self._checks.values() if cb.get_active()]
        from .check_page import CheckAvailabilityPage

        self._nav_view.push(CheckAvailabilityPage(state=self._state, nav_view=self._nav_view))

    def _build_ui(self) -> None:
        subtitle = Gtk.Label(
            label=(f"{len(self._state.candidate_repos)} repositories need review for {self._state.target_codename}"),
            wrap=True,
            xalign=0,
        )
        subtitle.set_opacity(0.55)
        self._content_box.append(subtitle)

        self._load_btn = Gtk.Button(label="Select from state file…", valign=Gtk.Align.CENTER)
        self._load_btn.add_css_class("flat")
        self._load_btn.connect("clicked", self._on_load_from_file)

        # Fixed-width label so the button never shrinks when text toggles between
        # "Select all" (10 chars) and "Deselect all" (12 chars), keeping the load
        # button anchored in place.
        self._select_all_label = Gtk.Label(width_chars=12)
        self._select_all_btn = Gtk.Button(child=self._select_all_label, valign=Gtk.Align.CENTER)
        self._select_all_btn.add_css_class("flat")
        self._select_all_btn.connect("clicked", self._on_select_all)

        header_box = Gtk.Box(valign=Gtk.Align.CENTER)
        header_box.append(self._load_btn)
        header_box.append(Gtk.Box(hexpand=True))
        header_box.append(self._select_all_btn)
        self._content_box.append(header_box)

        group = Adw.PreferencesGroup()
        self._content_box.append(group)

        for repo in self._state.candidate_repos:
            row = Adw.ActionRow(
                title=repo.display_name,
                subtitle=repo.uris[0] if repo.uris else "",
            )
            check = Gtk.CheckButton(active=(repo.availability != AvailabilityStatus.UNAVAILABLE))
            check.connect("toggled", lambda _cb: self._on_check_toggled())
            row.add_prefix(check)
            row.set_activatable_widget(check)
            row.add_suffix(self._status_icon(repo))
            group.add(row)
            self._checks[id(repo)] = (repo, check)

        self._update_select_all_btn()

    @staticmethod
    def _status_icon(repo: Repository) -> Gtk.Widget:
        icon_name, css = {
            AvailabilityStatus.AVAILABLE: ("emblem-ok-symbolic", "success"),
            AvailabilityStatus.UNAVAILABLE: ("dialog-warning-symbolic", "warning"),
            AvailabilityStatus.SUITE_AGNOSTIC: ("emblem-synchronizing-symbolic", ""),
        }.get(repo.availability, ("dialog-question-symbolic", ""))
        icon = Gtk.Image.new_from_icon_name(icon_name)
        if css:
            icon.add_css_class(css)
        if repo.availability not in (
            AvailabilityStatus.AVAILABLE,
            AvailabilityStatus.UNAVAILABLE,
            AvailabilityStatus.SUITE_AGNOSTIC,
        ):
            icon.set_opacity(0.55)
        return icon
