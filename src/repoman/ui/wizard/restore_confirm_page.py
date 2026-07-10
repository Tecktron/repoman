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
from .popover import make_info_button


class RestoreConfirmPage(RepomanWizardPage):
    """
    Page 3 — review categorised changes and apply via polkit.

    Matched repos appear in groups by their resolved action:
      - "Updating to {cc}"  (update_suite: per-row enabled/disabled icon)
      - "Enabling"          (restore_as_is: was disabled, saved file says enabled)
      - "Disabling"         (restore_as_is/add_disabled: will be disabled)
      - "No changes"        (restore_as_is: enabled state matches saved file)

    Missing repos appear in "Not found - will be added enabled/disabled" groups.
    All writes are sent in a single polkit call; in-memory mutations roll back on failure.
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
        self._matched_enabling: list[dict] = []
        self._matched_disabling: list[dict] = []
        self._matched_unchanged: list[dict] = []
        self._build_apply_plan()
        self._build_ui()
        if not self._has_changes and not self._missing:
            self._next_button.set_label("Done")

    def can_proceed(self) -> bool:
        return True

    def _on_proceed(self) -> None:
        if not self._has_changes and not self._missing:
            self.get_root().close()
            return
        self._next_button.set_sensitive(False)
        self._next_button.set_label("Applying…")
        threading.Thread(target=self._apply, daemon=True).start()

    def _build_apply_plan(self) -> None:
        """Pre-compute all writes: matched repo mutations and missing repo creates."""
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
                if live.enabled:
                    live.enabled = False
                    changed = True
                self._matched_disabling.append(entry)
            elif action == "restore_as_is":
                saved_enabled = entry.get("enabled", live.enabled)
                if saved_enabled != original_enabled:
                    live.enabled = saved_enabled
                    changed = True
                    if saved_enabled:
                        self._matched_enabling.append(entry)
                    else:
                        self._matched_disabling.append(entry)
                else:
                    self._matched_unchanged.append(entry)

            if changed:
                self._writes.append({"path": str(live.source_file), "content": repo_to_deb822(live)})
                self._changed_repos.append((live, original_enabled, original_suites))

        # Pre-adapt missing entries then build their write list
        for entry in self._missing:
            action = self._action_map.get(id(entry), "restore_as_is")
            if action == "update_suite":
                entry["suites"] = [cc]
            elif action == "add_disabled":
                entry["enabled"] = False

        for entry in self._missing:
            repo = config_io.entry_to_repository(entry)
            if entry.get("signed_by_content_b64") and repo.signed_by and repo.signed_by.startswith("/"):
                self._writes.append(
                    {
                        "path": repo.signed_by,
                        "content": entry["signed_by_content_b64"],
                        "encoding": "base64",
                    }
                )
            self._writes.append({"path": str(repo.source_file), "content": repo_to_deb822(repo)})

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

        def _make_row(
            entry: dict, icon_name: str, css: str, tooltip: str, *, headline: str, target_label: str | None
        ) -> Adw.ActionRow:
            name, subtitle = _display(entry)
            row = Adw.ActionRow(title=name, subtitle=subtitle)
            repo = config_io.entry_to_repository(entry)
            row.add_suffix(
                make_info_button(
                    icon_name,
                    css,
                    tooltip,
                    headline=headline,
                    suites=entry.get("suites") or [],
                    target_label=target_label,
                    ppa_owner=repo.ppa_owner if repo.is_ppa else None,
                    ppa_name=repo.ppa_name if repo.is_ppa else None,
                )
            )
            return row

        if self._has_changes:
            auth_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            auth_card.add_css_class("card")
            lock_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
            lock_icon.set_icon_size(Gtk.IconSize.LARGE)
            lock_icon.add_css_class("accent")
            lock_icon.set_tooltip_text("Requires administrator password")
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

        # Filter to matched entries only — missing entries get their own group below
        matched_set = {id(e) for e, _ in self._matched}
        update_entries = [
            e for e, a in zip(saved, actions, strict=True) if a == "update_suite" and id(e) in matched_set
        ]

        if update_entries:
            group = Adw.PreferencesGroup(title=f"Updating to {cc}")
            for entry in update_entries:
                is_enabled = entry.get("enabled", True)
                if is_enabled:
                    icon_name, css = "tecktron-repoman-available", "success"
                    tooltip = f"Suite updated to {cc} - will be enabled"
                else:
                    icon_name, css = "dialog-warning-symbolic", "warning"
                    tooltip = f"Suite updated to {cc} - will be disabled"
                group.add(_make_row(entry, icon_name, css, tooltip, headline=tooltip, target_label=f"Target: {cc}"))
            self._content_box.append(group)

        if self._matched_enabling:
            group = Adw.PreferencesGroup(title="Enabling")
            for entry in self._matched_enabling:
                group.add(
                    _make_row(
                        entry,
                        "tecktron-repoman-available",
                        "success",
                        "Will be enabled",
                        headline="Will be enabled",
                        target_label=None,
                    )
                )
            self._content_box.append(group)

        if self._matched_disabling:
            group = Adw.PreferencesGroup(title="Disabling")
            for entry in self._matched_disabling:
                group.add(
                    _make_row(
                        entry,
                        "dialog-warning-symbolic",
                        "warning",
                        "Will be disabled",
                        headline="Will be disabled",
                        target_label=None,
                    )
                )
            self._content_box.append(group)

        if self._matched_unchanged:
            group = Adw.PreferencesGroup(title="No changes")
            for entry in self._matched_unchanged:
                group.add(
                    _make_row(
                        entry, "locked-symbolic", "", "Already up to date", headline="No changes", target_label=None
                    )
                )
            self._content_box.append(group)

        if self._missing:
            # Split by final enabled state — _build_apply_plan() has already mutated
            # add_disabled entries to entry["enabled"] = False.
            missing_enabled = [e for e in self._missing if e.get("enabled", True)]
            missing_disabled = [e for e in self._missing if not e.get("enabled", True)]

            def _missing_row(entry: dict) -> Adw.ActionRow:
                action = self._action_map.get(id(entry), "restore_as_is")
                is_enabled = entry.get("enabled", True)
                if action == "update_suite":
                    target_label: str | None = f"Target: {cc}"
                    if is_enabled:
                        icon_name, css = "tecktron-repoman-available", "success"
                        tooltip = f"Suite updated to {cc} - will be added enabled"
                    else:
                        icon_name, css = "locked-symbolic", ""
                        tooltip = f"Suite updated to {cc} - disabled in original file"
                elif action == "add_disabled":
                    icon_name, css = "dialog-warning-symbolic", "warning"
                    tooltip = f"Not available for {cc} - will be added as disabled"
                    target_label = f"Target: {cc}"
                else:
                    icon_name, css = "locked-symbolic", ""
                    tooltip = "Will be added unchanged"
                    target_label = None
                return _make_row(entry, icon_name, css, tooltip, headline=tooltip, target_label=target_label)

            if missing_enabled:
                ne = len(missing_enabled)
                enabled_group = Adw.PreferencesGroup(
                    title=f"Not found - will be added enabled ({ne})",
                    description=f"{'This repository does' if ne == 1 else 'These repositories do'} not exist on this system and will be created and enabled",
                )
                for entry in missing_enabled:
                    enabled_group.add(_missing_row(entry))
                self._content_box.append(enabled_group)

            if missing_disabled:
                nd = len(missing_disabled)
                disabled_group = Adw.PreferencesGroup(
                    title=f"Not found - will be added disabled ({nd})",
                    description=f"{'This repository does' if nd == 1 else 'These repositories do'} not exist on this system and will be created with Enabled: no",
                )
                for entry in missing_disabled:
                    disabled_group.add(_missing_row(entry))
                self._content_box.append(disabled_group)

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
