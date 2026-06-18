from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GObject, Gtk

from ..models import AvailabilityStatus, Repository


class RepoRow(Adw.ActionRow):
    """One row in the repo sidebar list."""

    __gtype_name__ = "RepoRow"

    repo_toggled = GObject.Signal("repo-toggled", arg_types=(object,))

    def __init__(self, repo: Repository, **kwargs) -> None:
        super().__init__(
            title=repo.display_name,
            subtitle=repo.uris[0] if repo.uris else "",
            **kwargs,
        )
        self._repo = repo
        self._updating = False

        # Enable/disable switch on the left
        self._switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._switch.set_active(repo.enabled)
        self._switch.connect("state-set", self._on_switch_toggled)
        self.add_prefix(self._switch)
        self.set_activatable_widget(self._switch)

        self._update_style()
        self._badge = self._make_badge()
        if self._badge:
            self.add_suffix(self._badge)

    @property
    def repo(self) -> Repository:
        return self._repo

    def refresh(self, repo: Repository) -> None:
        """Refresh display after the repo model changes."""
        self._repo = repo
        self._updating = True
        self.set_title(repo.display_name)
        self.set_subtitle(repo.uris[0] if repo.uris else "")
        self._switch.set_active(repo.enabled)
        self._updating = False
        self._update_style()
        self._refresh_badge()

    def _on_switch_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        if self._updating:
            return False
        self._repo.enabled = state
        self._update_style()
        self.emit("repo-toggled", self._repo)
        return False  # allow GTK to update switch visual state

    def _update_style(self) -> None:
        if self._repo.enabled:
            self.remove_css_class("dim-label")
        else:
            self.add_css_class("dim-label")

    def _make_badge(self) -> Gtk.Widget | None:
        return _availability_icon(self._repo.availability)

    def _refresh_badge(self) -> None:
        if self._badge:
            self.remove(self._badge)
        self._badge = _make_badge(self._repo.availability)
        if self._badge:
            self.add_suffix(self._badge)


def _availability_icon(status: AvailabilityStatus) -> Gtk.Widget | None:
    if status == AvailabilityStatus.UNKNOWN:
        return None
    if status in (AvailabilityStatus.CHECKING,):
        return Gtk.Spinner(spinning=True)
    mapping = {
        AvailabilityStatus.AVAILABLE: ("emblem-ok-symbolic", "success"),
        AvailabilityStatus.UNAVAILABLE: ("dialog-warning-symbolic", "warning"),
        AvailabilityStatus.SUITE_AGNOSTIC: ("emblem-synchronizing-symbolic", ""),
    }
    icon_name, css = mapping.get(status, ("dialog-question-symbolic", ""))
    icon = Gtk.Image.new_from_icon_name(icon_name)
    if css:
        icon.add_css_class(css)
    return icon


def _make_badge(status: AvailabilityStatus) -> Gtk.Widget | None:
    return _availability_icon(status)
