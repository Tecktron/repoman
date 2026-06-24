from __future__ import annotations

import argparse
import sys
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio

from .paths import check_required_tools
from .ui.main_window import RepomanWindow


class RepomanApplication(Adw.Application):
    """GTK4 APT repository manager application. Singleton — second launch activates the existing window."""

    def __init__(self, sources_dir: Path | None = None) -> None:
        super().__init__(
            application_id="io.github.Tecktron.repoman",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._sources_dir = sources_dir
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

        win = RepomanWindow(application=app, sources_dir=self._sources_dir)
        win.present()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="repoman",
        description="GTK4 APT repository manager for Ubuntu/Xubuntu.",
    )
    parser.add_argument("--version", action="version", version="repoman 0.1.0")
    parser.add_argument(
        "--sources-dir",
        metavar="DIR",
        help="Read repositories from DIR instead of /etc/apt/sources.list.d/ (useful for testing)",
    )
    # Pass unknown args to GTK (e.g. --display)
    args, remaining = parser.parse_known_args()
    sources_dir = Path(args.sources_dir) if args.sources_dir else None
    app = RepomanApplication(sources_dir=sources_dir)
    app.run([sys.argv[0]] + remaining)


if __name__ == "__main__":
    main()
