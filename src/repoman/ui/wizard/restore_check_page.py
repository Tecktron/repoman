"""Restore wizard — page 2: per-PPA availability checks with live spinner updates."""

from __future__ import annotations

import concurrent.futures
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ... import config_io
from ...models import AVAILABILITY_ICONS, AvailabilityStatus, RestoreWizardState
from ...upgrade_info import check_ppa_for_codename
from .base_page import RepomanWizardPage


class RestoreCheckPpasPage(RepomanWizardPage):
    """
    Page 2 — background thread checks each PPA entry against Launchpad.
    Spinner per row → icon as each result arrives. Next locked until all done.
    Mutates state.actions[i] to "update_suite" or "add_disabled" on the GTK thread.
    _checks_started flag prevents re-running on back-navigation.
    """

    __gtype_name__ = "RestoreCheckPpasPage"

    def __init__(self, state: RestoreWizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Checking PPAs",
            tag="restore-check",
            **kwargs,
        )
        state_typed: RestoreWizardState = self._state
        self._ppa_indices = [i for i, a in enumerate(state_typed.actions) if a == "ppa_check"]
        self._row_widgets: dict[int, tuple[Adw.ActionRow, Gtk.Spinner]] = {}
        self._pending = len(self._ppa_indices)
        self._checks_started = False
        self._next_button.set_sensitive(False)
        self._build_ui()

    def can_proceed(self) -> bool:
        return self._pending == 0

    def _on_shown(self) -> None:
        if self._checks_started:
            return
        self._checks_started = True
        threading.Thread(target=self._run_checks, daemon=True).start()

    def _on_proceed(self) -> None:
        from .restore_confirm_page import RestoreConfirmPage

        self._nav_view.push(RestoreConfirmPage(state=self._state, nav_view=self._nav_view))

    def _build_ui(self) -> None:
        state: RestoreWizardState = self._state
        n = len(self._ppa_indices)
        self._group = Adw.PreferencesGroup(
            title="PPAs",
            description=f"Checking {n} PPA{'s' if n != 1 else ''} for {state.current_codename}",
        )
        self._content_box.append(self._group)

        for idx in self._ppa_indices:
            entry = state.saved[idx]
            name = entry.get("description") or (entry.get("uris") or [""])[0]
            uri = (entry.get("uris") or [""])[0]
            row = Adw.ActionRow(title=name, subtitle=uri if name != uri else "")
            spinner = Gtk.Spinner(spinning=True)
            row.add_suffix(spinner)
            self._group.add(row)
            self._row_widgets[idx] = (row, spinner)

    def _run_checks(self) -> None:
        state: RestoreWizardState = self._state

        def _check_one(idx: int) -> None:
            entry = state.saved[idx]
            repo = config_io.entry_to_repository(entry)
            if repo.ppa_owner and repo.ppa_name:
                status, _ = check_ppa_for_codename(repo.ppa_owner, repo.ppa_name, state.current_codename)
            else:
                status = AvailabilityStatus.UNAVAILABLE
            GLib.idle_add(self._on_row_checked, idx, status)

        n = len(self._ppa_indices)
        max_workers = max(1, min(n, 8))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            pool.map(_check_one, self._ppa_indices)

    def _on_row_checked(self, idx: int, status: AvailabilityStatus) -> bool:
        state: RestoreWizardState = self._state
        row, spinner = self._row_widgets.get(idx, (None, None))
        if row is not None:
            row.remove(spinner)
            icon_name, css = AVAILABILITY_ICONS.get(status, ("dialog-question-symbolic", ""))
            icon = Gtk.Image.new_from_icon_name(icon_name)
            if css:
                icon.add_css_class(css)
            cc = state.current_codename
            tooltip = {
                AvailabilityStatus.AVAILABLE: f"Available for {cc} — suite will be updated",
                AvailabilityStatus.UNAVAILABLE: f"Not available for {cc} — will be added as disabled",
            }.get(status, "Could not check — network error")
            icon.set_tooltip_text(tooltip)
            row.add_suffix(icon)

        # Mutate actions on the GTK thread
        state.actions[idx] = "update_suite" if status == AvailabilityStatus.AVAILABLE else "add_disabled"

        self._pending -= 1
        if self._pending == 0:
            available = sum(1 for i in self._ppa_indices if state.actions[i] == "update_suite")
            n = len(self._ppa_indices)
            self._group.set_description(f"{available} of {n} available for {state.current_codename}")
            self.refresh_proceed()
        return GLib.SOURCE_REMOVE
