from __future__ import annotations

import json
import subprocess
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, GObject, Gtk

from ..converter import convert_to_deb822
from ..models import FileFormat, Repository
from ..paths import PKEXEC, POLKIT_HELPER
from ..writer import repo_to_deb822


class DetailPane(Gtk.Box):
    """Right-hand editing panel for a selected Repository."""

    __gtype_name__ = "RepomanDetailPane"

    repo_saved = GObject.Signal("repo-saved", arg_types=(object,))

    def __init__(self, **kwargs) -> None:
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            **kwargs,
        )
        self._repo: Repository | None = None
        self._build_ui()
        self._show_empty_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_repo(self, repo: Repository) -> None:
        self._repo = repo
        self._populate(repo)
        self._stack.set_visible_child_name("detail")

    def clear(self) -> None:
        self._repo = None
        self._show_empty_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._stack = Gtk.Stack()

        # Empty state
        empty = Adw.StatusPage(
            title="No repository selected",
            description="Select a repository from the list to view its details.",
            icon_name="drive-multidisk-symbolic",
            vexpand=True,
        )
        self._stack.add_named(empty, "empty")

        # Detail view
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        detail_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        scroll.set_child(detail_box)
        self._stack.add_named(scroll, "detail")

        # Info group (read-only)
        info_group = Adw.PreferencesGroup(title="Repository")
        detail_box.append(info_group)

        self._uri_row = Adw.ActionRow(title="URI")
        info_group.add(self._uri_row)

        self._format_row = Adw.ActionRow(title="Format")
        info_group.add(self._format_row)

        self._file_row = Adw.ActionRow(title="File")
        info_group.add(self._file_row)

        # Edit group
        edit_group = Adw.PreferencesGroup(title="Settings")
        detail_box.append(edit_group)

        self._desc_row = Adw.EntryRow(title="Description")
        edit_group.add(self._desc_row)

        self._suite_row = Adw.EntryRow(title="Suite / Codename")
        edit_group.add(self._suite_row)

        self._components_row = Adw.EntryRow(title="Components")
        edit_group.add(self._components_row)

        self._enabled_row = Adw.SwitchRow(title="Enabled")
        edit_group.add(self._enabled_row)

        # Save button
        self._save_button = Gtk.Button(
            label="Save changes",
            margin_top=8,
            halign=Gtk.Align.END,
        )
        self._save_button.add_css_class("suggested-action")
        self._save_button.connect("clicked", self._on_save_clicked)
        detail_box.append(self._save_button)

        # Toast overlay wraps the stack — set child before adding to self
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._stack)
        self.append(self._toast_overlay)

    def _show_empty_state(self) -> None:
        self._stack.set_visible_child_name("empty")

    def _populate(self, repo: Repository) -> None:
        self._uri_row.set_subtitle(repo.uris[0] if repo.uris else "")

        fmt = "DEB822 (.sources)"
        if repo.file_format == FileFormat.ONE_LINE:
            fmt = "One-line (.list) — will convert to .sources on save"
        self._format_row.set_subtitle(fmt)

        self._file_row.set_subtitle(str(repo.source_file))

        self._desc_row.set_text(repo.description or "")
        self._suite_row.set_text(" ".join(repo.suites))
        self._components_row.set_text(" ".join(repo.components))
        self._enabled_row.set_active(repo.enabled)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save_clicked(self, _button: Gtk.Button) -> None:
        if self._repo is None:
            return
        self._apply_edits_to_repo()
        self._save_button.set_sensitive(False)
        self._save_button.set_label("Saving…")
        threading.Thread(target=self._do_save, daemon=True).start()

    def _apply_edits_to_repo(self) -> None:
        repo = self._repo
        repo.description = self._desc_row.get_text().strip() or None
        repo.suites = self._suite_row.get_text().split()
        repo.components = self._components_row.get_text().split()
        repo.enabled = self._enabled_row.get_active()

    def _do_save(self) -> None:
        """Background thread — calls polkit helper."""
        repo = self._repo
        writes = []
        deletes = []

        if repo.file_format == FileFormat.ONE_LINE:
            new_path, content = convert_to_deb822(repo)
            writes.append({"path": str(new_path), "content": content})
            deletes.append(str(repo.source_file))
        else:
            content = repo_to_deb822(repo)
            writes.append({"path": str(repo.source_file), "content": content})

        payload = json.dumps({"action": "write_files", "writes": writes, "deletes": deletes})
        result = subprocess.run(
            [PKEXEC, POLKIT_HELPER],
            input=payload,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            GLib.idle_add(self._on_save_success)
        else:
            GLib.idle_add(self._on_save_failure, result.stderr.strip())

    def _on_save_success(self) -> bool:
        self._save_button.set_label("Save changes")
        self._save_button.set_sensitive(True)
        self._toast_overlay.add_toast(Adw.Toast(title="Changes saved", timeout=2))
        self.emit("repo-saved", self._repo)
        return GLib.SOURCE_REMOVE

    def _on_save_failure(self, message: str) -> bool:
        self._save_button.set_label("Save changes")
        self._save_button.set_sensitive(True)
        self._toast_overlay.add_toast(Adw.Toast(title=f"Failed to save: {message}", timeout=5))
        return GLib.SOURCE_REMOVE
