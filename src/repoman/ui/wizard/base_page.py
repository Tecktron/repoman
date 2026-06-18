from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from ...models import WizardState


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
        inner_header = Adw.HeaderBar()
        inner_header.set_show_start_title_buttons(False)
        inner_header.set_show_end_title_buttons(False)
        toolbar_view.add_top_bar(inner_header)

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
