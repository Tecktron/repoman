"""Restore wizard — page 1: classified overview of all saved entries."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw

from ... import config_io
from ...models import RestoreWizardState
from .base_page import RepomanWizardPage
from .popover import make_info_button


class RestoreClassifyPage(RepomanWizardPage):
    """
    Page 1 — read-only grouped overview of all entries, classified by action.

    Entries are grouped into up to four groups (hidden when empty):
      - Updating suite to {current_codename}  (update_suite, non-PPA)
      - Checking against Launchpad            (ppa_check)
      - Adding as disabled                    (add_disabled)
      - Restoring unchanged                   (restore_as_is)

    Proceeds to RestoreCheckPpasPage if any ppa_check entries exist,
    otherwise skips straight to RestoreConfirmPage.
    """

    __gtype_name__ = "RestoreClassifyPage"

    def __init__(self, state: RestoreWizardState, nav_view: Adw.NavigationView, **kwargs) -> None:
        super().__init__(
            state=state,
            nav_view=nav_view,
            title="Review restore plan",
            tag="restore-classify",
            next_label="Next",
            **kwargs,
        )
        self._build_ui()

    def can_proceed(self) -> bool:
        return True

    def _on_proceed(self) -> None:
        state: RestoreWizardState = self._state
        if any(a == "ppa_check" for a in state.actions):
            from .restore_check_page import RestoreCheckPpasPage

            self._nav_view.push(RestoreCheckPpasPage(state=state, nav_view=self._nav_view))
        else:
            from .restore_confirm_page import RestoreConfirmPage

            self._nav_view.push(RestoreConfirmPage(state=state, nav_view=self._nav_view))

    def _build_ui(self) -> None:
        state: RestoreWizardState = self._state
        saved = state.saved
        actions = state.actions
        cc = state.current_codename

        def _display(entry: dict) -> tuple[str, str]:
            name = entry.get("description") or ""
            uri = (entry.get("uris") or [""])[0]
            return name or uri, uri if name else ""

        def _add_group(
            title: str,
            entries: list[dict],
            icon_name: str,
            css: str,
            tooltip: str,
            target_label: str | None,
        ) -> None:
            if not entries:
                return
            group = Adw.PreferencesGroup(title=title)
            for entry in entries:
                name, subtitle = _display(entry)
                row = Adw.ActionRow(title=name, subtitle=subtitle)
                repo = config_io.entry_to_repository(entry)
                row.add_suffix(
                    make_info_button(
                        icon_name,
                        css,
                        tooltip,
                        headline=tooltip,
                        suites=entry.get("suites") or [],
                        target_label=target_label,
                        ppa_owner=repo.ppa_owner if repo.is_ppa else None,
                        ppa_name=repo.ppa_name if repo.is_ppa else None,
                    )
                )
                group.add(row)
            self._content_box.append(group)

        update_entries = [e for e, a in zip(saved, actions, strict=True) if a == "update_suite"]
        ppa_entries = [e for e, a in zip(saved, actions, strict=True) if a == "ppa_check"]
        disabled_entries = [e for e, a in zip(saved, actions, strict=True) if a == "add_disabled"]
        unchanged_entries = [e for e, a in zip(saved, actions, strict=True) if a == "restore_as_is"]

        _add_group(
            f"Updating suite to {cc}",
            update_entries,
            "pamac-tray-no-update",
            "success",
            f"Suite will be updated to {cc}",
            f"Target: {cc}",
        )
        _add_group(
            "Checking against Launchpad",
            ppa_entries,
            "dialog-question-symbolic",
            "",
            "Will be checked against Launchpad in Step 2",
            f"Target: {cc}",
        )
        _add_group(
            "Adding as disabled",
            disabled_entries,
            "dialog-warning-symbolic",
            "warning",
            "Will be added as disabled",
            f"Target: {cc}",
        )
        _add_group(
            "Restoring unchanged",
            unchanged_entries,
            "locked-symbolic",
            "",
            "Will be restored unchanged",
            None,
        )
