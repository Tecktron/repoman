from __future__ import annotations

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ...checker import Checker, get_network_error
from ...models import AvailabilityStatus, Repository, WizardState
from .base_page import RepomanWizardPage


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

        self._nav_view.push(ConfirmChangesPage(state=self._state, nav_view=self._nav_view))

    def _build_ui(self) -> None:
        self._group = Adw.PreferencesGroup(
            title="Repositories",
            description=(f"Checking {len(self._state.selected)} repos against {self._state.target_codename}"),
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
            AvailabilityStatus.AVAILABLE: ("emblem-ok-symbolic", "success"),
            AvailabilityStatus.UNAVAILABLE: ("dialog-warning-symbolic", "warning"),
            AvailabilityStatus.SUITE_AGNOSTIC: ("emblem-synchronizing-symbolic", ""),
        }.get(status, ("dialog-question-symbolic", ""))
        icon = Gtk.Image.new_from_icon_name(icon_name)
        if css:
            icon.add_css_class(css)
        row.add_suffix(icon)
        self._pending -= 1
        if self._pending == 0:
            available = sum(1 for r in self._state.selected if r.availability == AvailabilityStatus.AVAILABLE)
            self._group.set_description(
                f"{available} of {len(self._state.selected)} available for {self._state.target_codename}"
            )
            err = get_network_error()
            if err:
                self._content_box.append(
                    Gtk.Label(
                        label=f"Network error — some results may be incomplete: {err}",
                        wrap=True,
                        xalign=0,
                        css_classes=["warning"],
                    )
                )
            self.refresh_proceed()
        return GLib.SOURCE_REMOVE
