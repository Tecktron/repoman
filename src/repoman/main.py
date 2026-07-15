"""Application entry point and RepomanApplication (Adw.Application) class."""

from __future__ import annotations

import argparse
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, Gtk

from .paths import check_required_tools
from .ui.main_window import RepomanWindow


class RepomanApplication(Adw.Application):
    """GTK4 APT repository manager application. Singleton — second launch activates the existing window."""

    def __init__(self) -> None:
        super().__init__(
            application_id="net.tecktron.repoman",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def _on_activate(self, app: Adw.Application) -> None:
        missing = check_required_tools()
        if missing:
            tmp = Gtk.ApplicationWindow(application=app)
            dlg = Gtk.Window(
                title="Missing required tools",
                transient_for=tmp,
                modal=True,
                resizable=False,
                default_width=400,
            )
            dlg.set_icon_name("net.tecktron.repoman")
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=12,
                margin_top=18,
                margin_bottom=18,
                margin_start=18,
                margin_end=18,
            )
            box.append(
                Gtk.Label(
                    label=(
                        "repoman cannot start because the following are not available:\n\n"
                        + "\n".join(f"• {m}" for m in missing)
                    ),
                    wrap=True,
                    xalign=0,
                    max_width_chars=45,
                )
            )
            btn_row = Gtk.Box(halign=Gtk.Align.END, margin_top=6)
            quit_btn = Gtk.Button(label="Quit")
            quit_btn.add_css_class("destructive-action")
            quit_btn.connect("clicked", lambda _: app.quit())
            btn_row.append(quit_btn)
            box.append(btn_row)
            dlg.set_child(box)
            dlg.present()
            return

        win = RepomanWindow(application=app)
        win.present()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="repoman",
        description="GTK4 APT repository manager for Ubuntu/Xubuntu.",
    )
    parser.add_argument("--version", action="version", version="repoman 0.1.0")
    # Pass unknown args to GTK (e.g. --display)
    _, remaining = parser.parse_known_args()
    app = RepomanApplication()
    app.run([sys.argv[0]] + remaining)


if __name__ == "__main__":
    main()
