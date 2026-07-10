"""Restore wizard — page 1: classified overview of all saved entries."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw

from ... import config_io
from ...models import Repository, RestoreWizardState
from .base_page import RepomanWizardPage
from .popover import make_info_button

_AGNOSTIC = frozenset(
    [
        "stable",
        "main",
        "testing",
        "sid",
        "unstable",
        "bookworm",
        "bullseye",
        "buster",
        "stretch",
        "oldstable",
        "oldoldstable",
    ]
)


class RestoreClassifyPage(RepomanWizardPage):
    """
    Page 1 — read-only overview of what will happen during restore.

    Pre-resolve: matched repos whose live suite is already current (or suite-agnostic) are
    set to "restore_as_is" — only their enabled state will sync. Matched repos with stale
    suites keep their classified action (update_suite or ppa_check) for later pages.

    Existing repos (matched) — up to four sub-groups (hidden when empty):
      - Existing - state will change  (restore_as_is/add_disabled with enabled diff)
      - Existing - updating suite to {cc}  (update_suite)
      - Existing - checking PPA availability  (ppa_check)
      - Existing - no changes  (restore_as_is, same enabled state)

    Repos to add (missing) — up to four sub-groups (hidden when empty):
      - Adding - checking against Launchpad  (ppa_check)
      - Adding - will be created  (update_suite)
      - Adding - will be added as disabled  (add_disabled)
      - Adding - no changes needed  (restore_as_is, e.g. suite-agnostic repos)

    Proceeds to RestoreCheckPpasPage if any ppa_check entries exist, otherwise skips
    straight to RestoreConfirmPage.
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
        self._matched, self._missing = config_io.match_repos(state.saved, state.live_repos)
        self._matched_by_id: dict[int, Repository] = {id(e): live for e, live in self._matched}
        cc = state.current_codename

        for i, (entry, _action) in enumerate(zip(state.saved, state.actions, strict=True)):
            live = self._matched_by_id.get(id(entry))
            if live is None:
                continue
            suite_is_current = any(s == cc for s in live.suites) or all(
                not (s.isalpha() and s.islower()) or s in _AGNOSTIC for s in live.suites
            )
            if suite_is_current:
                state.actions[i] = "restore_as_is"

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
        cc = state.current_codename
        action_by_id = {id(e): a for e, a in zip(state.saved, state.actions, strict=True)}

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

        # ── Existing repos (matched) ──────────────────────────────────────
        exist_no_change: list[dict] = []
        exist_state_change: list[tuple[dict, bool]] = []  # (entry, will_be_enabled)
        exist_ppa_check: list[dict] = []
        exist_suite_update: list[dict] = []

        for entry, live in self._matched:
            action = action_by_id[id(entry)]
            if action == "restore_as_is":
                saved_enabled = entry.get("enabled", live.enabled)
                if saved_enabled == live.enabled:
                    exist_no_change.append(entry)
                else:
                    exist_state_change.append((entry, bool(saved_enabled)))
            elif action == "ppa_check":
                exist_ppa_check.append(entry)
            elif action == "update_suite":
                exist_suite_update.append(entry)
            elif action == "add_disabled":
                exist_state_change.append((entry, False))

        if exist_state_change:
            group = Adw.PreferencesGroup(title="Existing - state will change")
            for entry, will_be_enabled in exist_state_change:
                name, subtitle = _display(entry)
                row = Adw.ActionRow(title=name, subtitle=subtitle)
                repo = config_io.entry_to_repository(entry)
                if will_be_enabled:
                    icon_name = "tecktron-repoman-available"
                    css = "success"
                    tooltip = "Currently disabled - will be enabled"
                else:
                    icon_name = "dialog-warning-symbolic"
                    css = "warning"
                    tooltip = "Currently enabled - will be disabled"
                row.add_suffix(
                    make_info_button(
                        icon_name,
                        css,
                        tooltip,
                        headline=tooltip,
                        suites=entry.get("suites") or [],
                        target_label=None,
                        ppa_owner=repo.ppa_owner if repo.is_ppa else None,
                        ppa_name=repo.ppa_name if repo.is_ppa else None,
                    )
                )
                group.add(row)
            self._content_box.append(group)

        _add_group(
            f"Existing - updating suite to {cc}",
            exist_suite_update,
            "tecktron-repoman-available",
            "success",
            f"Suite will be updated to {cc}",
            f"Target: {cc}",
        )
        _add_group(
            "Existing - checking PPA availability",
            exist_ppa_check,
            "dialog-question-symbolic",
            "",
            "Will be verified against Launchpad in Step 2",
            f"Target: {cc}",
        )
        _add_group(
            "Existing - no changes",
            exist_no_change,
            "locked-symbolic",
            "",
            "Already up to date",
            None,
        )

        # ── Repos to add (missing) ────────────────────────────────────────
        miss_ppa_check = [e for e in self._missing if action_by_id[id(e)] == "ppa_check"]
        miss_update = [e for e in self._missing if action_by_id[id(e)] == "update_suite"]
        miss_disabled = [e for e in self._missing if action_by_id[id(e)] == "add_disabled"]
        miss_as_is = [e for e in self._missing if action_by_id[id(e)] == "restore_as_is"]

        _add_group(
            "Adding - checking against Launchpad",
            miss_ppa_check,
            "dialog-question-symbolic",
            "",
            "Will be checked against Launchpad in Step 2",
            f"Target: {cc}",
        )
        _add_group(
            "Adding - will be created",
            miss_update,
            "tecktron-repoman-available",
            "success",
            f"Will be added for {cc}",
            f"Target: {cc}",
        )
        _add_group(
            "Adding - will be added as disabled",
            miss_disabled,
            "dialog-warning-symbolic",
            "warning",
            "Will be added as disabled",
            f"Target: {cc}",
        )
        _add_group(
            "Adding - no changes needed",
            miss_as_is,
            "locked-symbolic",
            "",
            "Will be added unchanged",
            None,
        )
