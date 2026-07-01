"""Upgrade assistant wizard dialog (RepomanWizardDialog).

Wraps an AdwNavigationView with three pages (select → check → confirm).
Uses Gtk.Window so the WM draws the titlebar with the user's own theme.
"""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, GObject, Gtk

from ...models import Repository, WizardState
from ...utils import get_current_codename
from ..position import center_on_parent
from .select_page import SelectReposPage


class RepomanWizardDialog(Gtk.Window):
    """
    Upgrade assistant — modal Gtk.Window wrapping AdwNavigationView.

    Uses Gtk.Window so the system window manager (Xfwm4, etc.) draws the
    titlebar with the user's own theme, consistent with the main window.

    Emits:
        repos-updated — after polkit writes succeed; caller must reload repo list
    """

    __gtype_name__ = "RepomanWizardDialog"
    __gsignals__ = {
        "repos-updated": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "closing": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        repos: list[Repository],
        parent: Gtk.Window,
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
        self.set_icon_name("io.github.Tecktron.repoman")
        center_on_parent(self)
        self._closing = False
        self._state = WizardState(
            candidate_repos=repos,
            target_codename=get_current_codename(),
            on_complete=self._handle_complete,
        )
        self._nav_view = Adw.NavigationView()
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._nav_view)
        self.set_child(self._toast_overlay)

        first_page = SelectReposPage(state=self._state, nav_view=self._nav_view)
        self._nav_view.push(first_page)

        # Belt-and-suspenders: connect_after runs even when an earlier handler
        # (e.g. AdwNavigationView) returns True and stops normal propagation.
        self.connect_after("close-request", self._on_close_after)

    def do_close_request(self) -> bool:
        self._schedule_close()
        return True

    def _on_close_after(self, _win: Gtk.Window) -> bool:
        self._schedule_close()
        return True

    def _schedule_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        # Notify owner immediately so it clears its reference before any idle fires.
        self.emit("closing")
        self.set_visible(False)
        GLib.idle_add(self.destroy)

    def add_toast(self, toast: Adw.Toast) -> None:
        self._toast_overlay.add_toast(toast)

    def _handle_complete(self) -> None:
        self.emit("repos-updated")
        self._schedule_close()
