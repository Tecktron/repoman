from __future__ import annotations

import argparse
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio

from .paths import check_required_tools
from .ui.main_window import RepomanWindow


class RepomanApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.Tecktron.repoman",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)

    def _on_activate(self, app: Adw.Application) -> None:
        missing = check_required_tools()
        if missing:
            dialog = Adw.AlertDialog.new(
                "Missing required tools",
                "repoman cannot start because the following are not available:\n\n"
                + "\n".join(f"• {m}" for m in missing),
            )
            dialog.add_response("quit", "Quit")
            dialog.connect("response", lambda _d, _r: app.quit())
            # Create a temporary window so the dialog has a parent to attach to
            tmp = Adw.ApplicationWindow(application=app)
            dialog.present(tmp)
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
    _args, remaining = parser.parse_known_args()
    app = RepomanApplication()
    app.run([sys.argv[0]] + remaining)


if __name__ == "__main__":
    main()
