from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

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
        subtitle.add_css_class("dim-label")
        self._content_box.append(subtitle)

        group = Adw.PreferencesGroup()
        self._content_box.append(group)

        for repo in self._state.candidate_repos:
            row = Adw.ActionRow(
                title=repo.display_name,
                subtitle=repo.uris[0] if repo.uris else "",
            )
            check = Gtk.CheckButton(active=(repo.availability != AvailabilityStatus.UNAVAILABLE))
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
            AvailabilityStatus.AVAILABLE: ("emblem-ok-symbolic", "success"),
            AvailabilityStatus.UNAVAILABLE: ("dialog-warning-symbolic", "warning"),
            AvailabilityStatus.SUITE_AGNOSTIC: ("emblem-synchronizing-symbolic", ""),
        }.get(repo.availability, ("dialog-question-symbolic", ""))
        icon = Gtk.Image.new_from_icon_name(icon_name)
        if css:
            icon.add_css_class(css)
        return icon
