from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GObject

from ...models import Repository, WizardState
from ...utils import get_current_codename
from .select_page import SelectReposPage


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
