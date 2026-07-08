"""Shared info-button factory used by all wizard pages."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


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


def make_info_button(
    icon_name: str,
    css_class: str,
    tooltip: str,
    *,
    headline: str,
    suites: list[str] | None = None,
    target_label: str | None = None,
    ppa_owner: str | None = None,
    ppa_name: str | None = None,
    icon_opacity: float = 1.0,
) -> Gtk.MenuButton:
    """Flat circular MenuButton with icon + popover showing repo status details."""
    icon = Gtk.Image.new_from_icon_name(icon_name)
    if css_class:
        icon.add_css_class(css_class)
    if icon_opacity != 1.0:
        icon.set_opacity(icon_opacity)

    btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
    btn.set_child(icon)
    btn.add_css_class("flat")
    btn.add_css_class("circular")
    btn.set_tooltip_text(tooltip)

    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=6,
        margin_top=10,
        margin_bottom=10,
        margin_start=12,
        margin_end=12,
    )

    headline_lbl = Gtk.Label(label=headline, wrap=True, max_width_chars=36, xalign=0)
    headline_lbl.add_css_class("body")
    box.append(headline_lbl)
    box.append(Gtk.Separator())

    if suites:
        suite_text = f"Suite: {suites[0]}" if len(suites) == 1 else f"Suites: {', '.join(suites)}"
        suite_lbl = Gtk.Label(label=suite_text, xalign=0, selectable=True)
        suite_lbl.add_css_class("caption")
        box.append(suite_lbl)

    if target_label is not None:
        target_lbl = Gtk.Label(label=target_label, xalign=0, selectable=True)
        target_lbl.add_css_class("caption")
        box.append(target_lbl)

    if ppa_owner and ppa_name:
        box.append(Gtk.Separator())
        lp_lbl = Gtk.Label(
            label=f'<a href="https://launchpad.net/~{ppa_owner}/{ppa_name}">View on Launchpad</a>',
            use_markup=True,
            xalign=0,
        )
        box.append(lp_lbl)

    popover = Gtk.Popover(child=box)
    popover.connect("show", _clear_label_selections)
    btn.set_popover(popover)
    return btn
