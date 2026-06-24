from __future__ import annotations

import json
import subprocess
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ...models import AvailabilityStatus, Repository, WizardState
from ...paths import PKEXEC, POLKIT_HELPER
from .base_page import RepomanWizardPage


class ConfirmChangesPage(RepomanWizardPage):
    """
    Step 3 — summary and polkit-guarded apply.
    UNAVAILABLE repos are excluded from the write payload even if the user
    ticked them in step 1 — safety net against enabling broken repos.
    """

    __gtype_name__ = "RepomanConfirmChangesPage"

    def __init__(self, state: WizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Confirm changes",
            tag="confirm",
            next_label="Apply changes",
            **kwargs,
        )
        self._to_apply = [r for r in self._state.selected if r.availability != AvailabilityStatus.UNAVAILABLE]
        if not self._to_apply:
            self._next_button.set_label("Done")
        self._build_ui()

    def can_proceed(self) -> bool:
        return True

    def _on_proceed(self) -> None:
        if not self._to_apply:
            self.get_root().close()
            return
        self._next_button.set_sensitive(False)
        self._next_button.set_label("Applying…")
        threading.Thread(target=self._apply, daemon=True).start()

    def _build_ui(self) -> None:
        if self._to_apply:
            will_apply_group = Adw.PreferencesGroup(
                title="Will be re-enabled",
                description=f"Suite field updated to {self._state.target_codename}",
            )
            for repo in self._to_apply:
                will_apply_group.add(self._make_row(repo, success=True))
            self._content_box.append(will_apply_group)

        skipped = [r for r in self._state.selected if r.availability == AvailabilityStatus.UNAVAILABLE]
        if skipped:
            skipped_group = Adw.PreferencesGroup(title="Skipped — not yet available for this release")
            for repo in skipped:
                skipped_group.add(self._make_row(repo, success=False))
            self._content_box.append(skipped_group)

        if self._to_apply:
            auth_group = Adw.PreferencesGroup()
            auth_row = Adw.ActionRow(
                title="Administrator password required",
                subtitle="Writes to /etc/apt/sources.list.d/",
            )
            auth_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-password-symbolic"))
            auth_group.add(auth_row)
            self._content_box.append(auth_group)

    def _make_row(self, repo: Repository, *, success: bool) -> Adw.ActionRow:
        row = Adw.ActionRow(
            title=repo.display_name,
            subtitle=repo.uris[0] if repo.uris else "",
        )
        icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic" if success else "dialog-warning-symbolic")
        icon.add_css_class("success" if success else "warning")
        if not success:
            tooltip = "Not yet available — skipped"
        elif repo.availability == AvailabilityStatus.SUITE_AGNOSTIC:
            tooltip = "Will be re-enabled (suite-agnostic — suite field unchanged)"
        else:
            tooltip = f"Will be re-enabled for {self._state.target_codename}"
        icon.set_tooltip_text(tooltip)
        row.add_suffix(icon)
        return row

    def _repo_payload(self, repo: Repository) -> dict:
        """Build the enable_repos entry for one repo.
        Suite-agnostic repos only get Enabled patched — their suite is left untouched."""
        entry: dict = {"source_file": str(repo.source_file), "enabled": True}
        if repo.availability != AvailabilityStatus.SUITE_AGNOSTIC:
            entry["suites"] = [self._state.target_codename]
        return entry

    def _apply(self) -> None:
        """Background thread. Calls pkexec — blocks until auth resolves."""
        payload = json.dumps(
            {
                "action": "enable_repos",
                "target_codename": self._state.target_codename,
                "repos": [self._repo_payload(repo) for repo in self._to_apply],
            }
        )
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
        if self._state.on_complete:
            self._state.on_complete()
        return GLib.SOURCE_REMOVE

    def _on_failure(self, message: str) -> bool:
        toast = Adw.Toast(title=f"Failed to apply: {message}", timeout=5)
        self.get_root().add_toast(toast)
        self._next_button.set_label("Apply changes")
        self._next_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE
