"""Restore wizard dialog (RestoreWizardDialog).

Wraps an AdwNavigationView with up to three pages:
  classify → check PPAs (optional) → confirm + apply.
Uses Gtk.Window so the WM draws the titlebar with the user's own theme.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, GObject, Gtk

from ...models import Repository, RestoreWizardState
from ..position import center_on_parent
from .restore_classify_page import RestoreClassifyPage


class RestoreWizardDialog(Gtk.Window):
    """
    Restore wizard — modal Gtk.Window wrapping AdwNavigationView.

    Emits:
        repos-updated — after polkit writes succeed; caller must reload repo list
        closing       — immediately before destruction; caller should clear its reference
    """

    __gtype_name__ = "RestoreWizardDialog"
    __gsignals__ = {
        "repos-updated": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "closing": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        saved: list[dict],
        actions: list[str],
        saved_codename: str,
        current_codename: str,
        live_repos: list[Repository],
        on_complete: Callable[[list[dict]], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            title="Restore repositories",
            modal=True,
            default_width=480,
            default_height=560,
            **kwargs,
        )
        self.set_icon_name("net.tecktron.repoman")
        center_on_parent(self)
        self._closing = False

        self._state = RestoreWizardState(
            saved=saved,
            actions=actions,
            saved_codename=saved_codename,
            current_codename=current_codename,
            live_repos=live_repos,
            on_complete=on_complete,
        )

        self._nav_view = Adw.NavigationView()
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._nav_view)
        self.set_child(self._toast_overlay)

        first_page = RestoreClassifyPage(state=self._state, nav_view=self._nav_view)
        self._nav_view.push(first_page)

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
        self.emit("closing")
        self.set_visible(False)
        GLib.idle_add(self.destroy)

    def add_toast(self, toast: Adw.Toast) -> None:
        self._toast_overlay.add_toast(toast)

    def emit_repos_updated(self) -> None:
        self.emit("repos-updated")
