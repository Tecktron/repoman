"""Restore wizard — page 3: grouped summary and polkit-guarded apply."""

from __future__ import annotations

import json
import subprocess
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ... import config_io
from ...models import Repository, RestoreWizardState
from ...paths import PKEXEC, POLKIT_HELPER
from ...writer import repo_to_deb822
from .base_page import RepomanWizardPage


class RestoreConfirmPage(RepomanWizardPage):
    """
    Page 3 — review categorised changes and apply via polkit.
    Rolls back in-memory mutations on failure.
    Relabels button "Done" and closes immediately if there is nothing to write.
    """

    __gtype_name__ = "RestoreConfirmPage"

    def __init__(self, state: RestoreWizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Confirm restore",
            tag="restore-confirm",
            next_label="Apply changes",
            **kwargs,
        )
        state_typed: RestoreWizardState = self._state
        self._matched, self._missing = config_io.match_repos(state_typed.saved, state_typed.live_repos)
        self._action_map = {id(e): a for e, a in zip(state_typed.saved, state_typed.actions, strict=True)}
        self._changed_repos: list[tuple[Repository, bool, list[str] | None]] = []
        self._writes: list[dict] = []
        self._has_changes = False
        self._build_apply_plan()
        self._build_ui()
        if not self._has_changes:
            self._next_button.set_label("Done")

    def can_proceed(self) -> bool:
        return True

    def _on_proceed(self) -> None:
        if not self._has_changes:
            self.get_root().close()
            return
        self._next_button.set_sensitive(False)
        self._next_button.set_label("Applying…")
        threading.Thread(target=self._apply, daemon=True).start()

    def _build_apply_plan(self) -> None:
        """Pre-compute writes and pre-adapt missing entries (done before UI build so state is consistent)."""
        state: RestoreWizardState = self._state
        cc = state.current_codename

        for entry, live in self._matched:
            action = self._action_map.get(id(entry), "restore_as_is")
            original_enabled = live.enabled
            original_suites: list[str] | None = None
            changed = False

            if action == "update_suite":
                original_suites = list(live.suites)
                live.suites = [cc]
                live.enabled = entry.get("enabled", live.enabled)
                changed = True
            elif action == "add_disabled":
                live.enabled = False
                changed = True
            elif action == "restore_as_is":
                if entry.get("enabled") != live.enabled:
                    live.enabled = entry["enabled"]
                    changed = True

            if changed:
                self._writes.append({"path": str(live.source_file), "content": repo_to_deb822(live)})
                self._changed_repos.append((live, original_enabled, original_suites))

        # Pre-adapt missing entries so the missing-repos dialog creates them correctly
        for entry in self._missing:
            action = self._action_map.get(id(entry), "restore_as_is")
            if action == "update_suite":
                entry["suites"] = [cc]
            elif action == "add_disabled":
                entry["enabled"] = False

        self._has_changes = bool(self._writes)

    def _build_ui(self) -> None:
        state: RestoreWizardState = self._state
        saved = state.saved
        actions = state.actions
        cc = state.current_codename

        def _display(entry: dict) -> tuple[str, str]:
            name = entry.get("description") or ""
            uri = (entry.get("uris") or [""])[0]
            return name or uri, uri if name else ""

        def _make_row(entry: dict, icon_name: str, css: str, tooltip: str) -> Adw.ActionRow:
            name, subtitle = _display(entry)
            row = Adw.ActionRow(title=name, subtitle=subtitle)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            if css:
                icon.add_css_class(css)
            icon.set_tooltip_text(tooltip)
            row.add_suffix(icon)
            return row

        if self._has_changes:
            auth_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            auth_card.add_css_class("card")
            lock_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
            lock_icon.set_icon_size(Gtk.IconSize.LARGE)
            lock_icon.add_css_class("accent")
            lock_icon.set_margin_start(12)
            auth_card.append(lock_icon)
            text = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2,
                valign=Gtk.Align.CENTER,
                margin_top=12,
                margin_bottom=12,
            )
            title_lbl = Gtk.Label(label="Administrator password required", xalign=0)
            title_lbl.add_css_class("caption-heading")
            title_lbl.add_css_class("warning")
            sub_lbl = Gtk.Label(label="Writes to /etc/apt/sources.list.d/", xalign=0)
            sub_lbl.add_css_class("caption")
            sub_lbl.set_opacity(0.55)
            text.append(title_lbl)
            text.append(sub_lbl)
            auth_card.append(text)
            self._content_box.append(auth_card)

        update_entries = [e for e, a in zip(saved, actions, strict=True) if a == "update_suite"]
        disabled_entries = [e for e, a in zip(saved, actions, strict=True) if a == "add_disabled"]
        unchanged_entries = [e for e, a in zip(saved, actions, strict=True) if a == "restore_as_is"]

        if update_entries:
            group = Adw.PreferencesGroup(
                title=f"Updating to {cc}",
                description="Suite field updated and repo enabled",
            )
            for entry in update_entries:
                group.add(_make_row(entry, "emblem-ok-symbolic", "success", f"Suite updated to {cc}"))
            self._content_box.append(group)

        if disabled_entries:
            group = Adw.PreferencesGroup(
                title="Adding as disabled",
                description=f"Not available for {cc} — added with Enabled: no",
            )
            for entry in disabled_entries:
                group.add(_make_row(entry, "dialog-warning-symbolic", "warning", f"Not available for {cc}"))
            self._content_box.append(group)

        if unchanged_entries:
            group = Adw.PreferencesGroup(title="Restoring unchanged")
            for entry in unchanged_entries:
                group.add(_make_row(entry, "emblem-ok-symbolic", "success", "Restored as-is"))
            self._content_box.append(group)

    def _apply(self) -> None:
        """Background thread. Calls pkexec — blocks until auth resolves."""
        payload = json.dumps({"action": "write_files", "writes": self._writes, "deletes": []})
        result = subprocess.run(
            [PKEXEC, POLKIT_HELPER],
            input=payload,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            GLib.idle_add(self._on_success)
        else:
            GLib.idle_add(self._on_failure, result.stderr.strip())

    def _on_success(self) -> bool:
        root = self.get_root()
        if hasattr(root, "emit_repos_updated"):
            root.emit_repos_updated()
        state: RestoreWizardState = self._state
        if state.on_complete:
            state.on_complete(self._missing)
        root.close()
        return GLib.SOURCE_REMOVE

    def _on_failure(self, message: str) -> bool:
        for live, original_enabled, original_suites in self._changed_repos:
            live.enabled = original_enabled
            if original_suites is not None:
                live.suites = original_suites
        toast = Adw.Toast(title=f"Failed to restore: {message}", timeout=5)
        self.get_root().add_toast(toast)
        self._next_button.set_label("Apply changes")
        self._next_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE
