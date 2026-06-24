from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from ..checker import get_network_error, reset_network_state
from ..models import Repository
from ..parser import Parser
from ..paths import PKEXEC, POLKIT_HELPER, SOFTWARE_PROPERTIES, UPDATE_MANAGER
from ..utils import repos_needing_attention
from .detail_pane import DetailPane
from .position import center_on_parent, center_on_screen
from .repo_row import RepoRow
from .wizard.dialog import RepomanWizardDialog


class RepomanWindow(Gtk.ApplicationWindow):
    """
    Main application window.

    Uses Gtk.ApplicationWindow (not Adw.ApplicationWindow) so that the system
    window manager (Xfwm4, etc.) draws the titlebar with the user's own theme.
    All libadwaita widgets inside still work fine.
    """

    __gtype_name__ = "RepomanWindow"

    def __init__(self, sources_dir: Path | None = None, **kwargs) -> None:
        super().__init__(
            title="Repoman",
            default_width=900,
            default_height=600,
            **kwargs,
        )
        self._parser = Parser(sources_dir=sources_dir) if sources_dir else Parser()
        self._repos: list[Repository] = []
        self._wizard: RepomanWizardDialog | None = None
        self._rows: list[RepoRow] = []

        self._build_ui()
        self.connect("realize", self._on_realize)
        center_on_screen(self)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._toast_overlay = Adw.ToastOverlay()
        self.set_child(self._toast_overlay)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(outer_box)

        # Menu bar spanning full window width
        menu_bar = Gtk.PopoverMenuBar.new_from_model(self._build_menu_model())
        menu_bar.set_hexpand(True)
        outer_box.append(menu_bar)
        outer_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Banner (upgrade alert — below menu bar, hidden by default)
        self._banner = Adw.Banner(revealed=False)
        self._banner.connect("button-clicked", lambda _: self.open_upgrade_wizard())
        outer_box.append(self._banner)

        # Main split pane
        split = Adw.OverlaySplitView(sidebar_width_fraction=0.32, min_sidebar_width=260)
        outer_box.append(split)

        # --- Sidebar ---
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Search entry — always visible at the top of the sidebar
        search_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            margin_start=6,
            margin_end=6,
            margin_top=6,
            margin_bottom=6,
        )
        self._search_entry = Gtk.SearchEntry(hexpand=True, placeholder_text="Search repositories…")
        self._search_entry.connect("search-changed", self._on_search_changed)
        search_box.append(self._search_entry)
        sidebar_box.append(search_box)
        sidebar_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Repo list
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.set_filter_func(self._filter_row)
        self._list_box.connect("row-selected", self._on_row_selected)
        scroll.set_child(self._list_box)

        # Loading spinner
        self._spinner_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            vexpand=True,
            valign=Gtk.Align.CENTER,
            spacing=12,
        )
        self._spinner = Gtk.Spinner(spinning=True)
        self._spinner_box.append(self._spinner)
        self._spinner_box.append(Gtk.Label(label="Loading repositories…", css_classes=["dim-label"]))

        sidebar_stack = Gtk.Stack()
        sidebar_stack.add_named(self._spinner_box, "loading")
        sidebar_stack.add_named(scroll, "list")
        sidebar_stack.set_visible_child_name("loading")
        self._sidebar_stack = sidebar_stack
        sidebar_box.append(sidebar_stack)

        split.set_sidebar(sidebar_box)

        # --- Detail pane ---
        self._detail_pane = DetailPane(vexpand=True)
        self._detail_pane.connect("repo-saved", self._on_repo_saved)
        split.set_content(self._detail_pane)

        # Actions
        self._setup_actions()

    def _build_menu_model(self) -> Gio.MenuModel:
        model = Gio.Menu()

        # Tools
        tools = Gio.Menu()
        tools.append("Run Upgrade Assistant…", "win.upgrade-wizard")
        tools.append("Check pre-update compatibility…", "win.compat-check")
        state_mgmt = Gio.Menu()
        state_mgmt.append("Save…", "win.save-config")
        state_mgmt.append("Load…", "win.load-config")
        tools.append_submenu("State Management", state_mgmt)
        tools.append("Disable All Third-Party Repos…", "win.disable-all-repos")
        companion_section = Gio.Menu()
        companion_section.append("Software Updater", "win.launch-updater")
        companion_section.append("Software & Updates", "win.launch-software-properties")
        tools.append_section(None, companion_section)
        model.append_submenu("Tools", tools)

        # Help (keyboard shortcuts merged in here; no separate Settings menu)
        help_menu = Gio.Menu()
        help_menu.append("Keyboard Shortcuts", "win.show-shortcuts")
        help_section = Gio.Menu()
        help_section.append("Help", "win.open-help")
        help_section.append("About repoman", "win.about")
        help_menu.append_section(None, help_section)
        model.append_submenu("Help", help_menu)

        return model

    def _setup_actions(self) -> None:
        # Standard actions
        for name, callback in [
            ("upgrade-wizard", self.open_upgrade_wizard),
            ("compat-check", self._open_compat_checker),
            ("load-config", self._load_config),
            ("show-shortcuts", self._show_shortcuts),
            ("open-help", self._open_help),
            ("about", self._show_about),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

        # Save-config action — disabled until repos have loaded
        self._save_config_action = Gio.SimpleAction.new("save-config", None)
        self._save_config_action.connect("activate", lambda _a, _p: self._save_config())
        self._save_config_action.set_enabled(False)
        self.add_action(self._save_config_action)

        # Disable-all action — sensitivity updated after repo load
        self._disable_all_action = Gio.SimpleAction.new("disable-all-repos", None)
        self._disable_all_action.connect("activate", lambda _a, _p: self._confirm_disable_all())
        self._disable_all_action.set_enabled(False)
        self.add_action(self._disable_all_action)

        # Launch companion tools — disabled if not installed
        updater_action = Gio.SimpleAction.new("launch-updater", None)
        updater_action.connect("activate", lambda _a, _p: self._launch(UPDATE_MANAGER))
        updater_action.set_enabled(UPDATE_MANAGER is not None)
        self.add_action(updater_action)

        props_action = Gio.SimpleAction.new("launch-software-properties", None)
        props_action.connect("activate", lambda _a, _p: self._launch(SOFTWARE_PROPERTIES))
        props_action.set_enabled(SOFTWARE_PROPERTIES is not None)
        self.add_action(props_action)

    # ------------------------------------------------------------------
    # Realize / startup
    # ------------------------------------------------------------------

    def _on_realize(self, _widget) -> None:
        GLib.idle_add(self._load_repos)

    # ------------------------------------------------------------------
    # Repo loading
    # ------------------------------------------------------------------

    def _load_repos(self) -> bool:
        threading.Thread(target=self._parse_repos, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _parse_repos(self) -> None:
        repos = self._parser.load_all()
        GLib.idle_add(self._on_repos_loaded, repos)

    def _on_repos_loaded(self, repos: list[Repository]) -> bool:
        self._repos = repos
        self._rows = []
        while child := self._list_box.get_first_child():
            self._list_box.remove(child)

        for repo in repos:
            row = RepoRow(repo)
            row.connect("repo-toggled", self._on_repo_toggled)
            self._list_box.append(row)
            self._rows.append(row)

        self._sidebar_stack.set_visible_child_name("list")
        self._update_banner()
        return GLib.SOURCE_REMOVE

    def _update_banner(self) -> None:
        attention = repos_needing_attention(self._repos)
        if attention:
            n = len(attention)
            self._banner.set_title(f"{n} {'repository' if n == 1 else 'repositories'} need review after upgrade")
            self._banner.set_button_label("Review")
            self._banner.set_revealed(True)
        else:
            self._banner.set_revealed(False)
        self._save_config_action.set_enabled(bool(self._repos))
        self._disable_all_action.set_enabled(any(r.enabled for r in self._repos))

    # ------------------------------------------------------------------
    # Search / filter
    # ------------------------------------------------------------------

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._list_box.invalidate_filter()

    def _filter_row(self, row: Gtk.ListBoxRow) -> bool:
        query = self._search_entry.get_text().strip().lower()
        if not query:
            return True
        if not isinstance(row, RepoRow):
            return True
        repo = row.repo
        return query in repo.display_name.lower() or any(query in uri.lower() for uri in repo.uris)

    # ------------------------------------------------------------------
    # Row interactions
    # ------------------------------------------------------------------

    def _on_row_selected(self, _list_box: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None or not isinstance(row, RepoRow):
            self._detail_pane.clear()
            return
        self._detail_pane.show_repo(row.repo)

    def _on_repo_toggled(self, _row: RepoRow, repo: Repository) -> None:
        """Quick enable/disable toggle — writes immediately via polkit."""
        from ..writer import repo_to_deb822

        content = repo_to_deb822(repo)
        payload = json.dumps(
            {
                "action": "write_files",
                "writes": [{"path": str(repo.source_file), "content": content}],
                "deletes": [],
            }
        )

        def _write() -> None:
            result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)
            if result.returncode != 0:
                GLib.idle_add(
                    self._toast_overlay.add_toast,
                    Adw.Toast(title=f"Failed to save: {result.stderr.strip()}", timeout=4),
                )

        threading.Thread(target=_write, daemon=True).start()

    def _on_repo_saved(self, _pane: DetailPane, repo: Repository) -> None:
        for row in self._rows:
            if row.repo is repo:
                row.refresh(repo)
                break
        self._update_banner()

    # ------------------------------------------------------------------
    # Disable all third-party repos
    # ------------------------------------------------------------------

    def _confirm_disable_all(self) -> None:
        enabled_count = sum(1 for r in self._repos if r.enabled)
        if enabled_count == 0:
            return
        dialog = Adw.AlertDialog.new(
            "Disable all third-party repositories?",
            f"This will disable all {enabled_count} enabled "
            f"{'repository' if enabled_count == 1 else 'repositories'}. "
            "You can re-enable them individually in repoman after your upgrade.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("disable", "Disable All")
        dialog.set_response_appearance("disable", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_disable_all_response)
        dialog.present(self)

    def _on_disable_all_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response != "disable":
            return
        from ..writer import repo_to_deb822

        to_disable = [r for r in self._repos if r.enabled]
        for repo in to_disable:
            repo.enabled = False

        writes = [{"path": str(r.source_file), "content": repo_to_deb822(r)} for r in to_disable]
        payload = json.dumps({"action": "write_files", "writes": writes, "deletes": []})

        def _write() -> None:
            result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)
            if result.returncode == 0:
                GLib.idle_add(self._on_disable_all_success, len(to_disable))
            else:
                GLib.idle_add(self._on_disable_all_failure, result.stderr.strip(), to_disable)

        threading.Thread(target=_write, daemon=True).start()

    def _on_disable_all_success(self, count: int) -> bool:
        for row in self._rows:
            row.refresh(row.repo)
        self._update_banner()
        self._toast_overlay.add_toast(
            Adw.Toast(title=f"Disabled {count} {'repository' if count == 1 else 'repositories'}", timeout=4)
        )
        return GLib.SOURCE_REMOVE

    def _on_disable_all_failure(self, message: str, repos: list) -> bool:
        for repo in repos:
            repo.enabled = True
        for row in self._rows:
            row.refresh(row.repo)
        self._toast_overlay.add_toast(Adw.Toast(title=f"Failed to disable repositories: {message}", timeout=5))
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------
    # Launch companion tools
    # ------------------------------------------------------------------

    def _launch(self, cmd: str | None) -> None:
        if cmd:
            subprocess.Popen([cmd])

    # ------------------------------------------------------------------
    # Wizard
    # ------------------------------------------------------------------

    def _open_compat_checker(self) -> None:
        from .compat_checker import CompatCheckerWindow

        win = CompatCheckerWindow(repos=self._repos, parent=self)
        win.present()

    def open_upgrade_wizard(self) -> None:
        if self._wizard is not None:
            self._wizard.present()
            return

        attention = repos_needing_attention(self._repos)
        if not attention:
            dialog = Adw.AlertDialog.new(
                "All repositories are current",
                "Every repository is enabled and pointing at the correct release.",
            )
            dialog.add_response("ok", "OK")
            dialog.present(self)
            return

        reset_network_state()
        self._wizard = RepomanWizardDialog(repos=attention, parent=self)
        self._wizard.connect("repos-updated", self._on_repos_updated)
        self._wizard.connect("closing", lambda _: setattr(self, "_wizard", None))
        self._wizard.present()

    def _on_repos_updated(self, _dialog: RepomanWizardDialog) -> None:
        self._repos = self._parser.load_all()
        self._on_repos_loaded(self._repos)

        err = get_network_error()
        if err:
            self._toast_overlay.add_toast(
                Adw.Toast(
                    title="Network error during availability check — some results may be incomplete",
                    timeout=6,
                )
            )

    # ------------------------------------------------------------------
    # Save / Load config
    # ------------------------------------------------------------------

    def _save_config(self) -> None:
        from datetime import date

        dialog = Gtk.FileDialog.new()
        dialog.set_title("Save repository configuration")
        dialog.set_initial_name(f"state-{date.today()}.repoman")
        f = Gtk.FileFilter()
        f.add_pattern("*.repoman")
        f.set_name("Repoman configs (*.repoman)")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dialog.set_filters(store)
        dialog.set_initial_folder(Gio.File.new_for_path(str(Path.home())))
        dialog.save(self, None, self._on_save_config_chosen)

    def _on_save_config_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        from .. import config_io

        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        path = Path(gfile.get_path())
        if path.suffix != ".repoman":
            path = path.with_suffix(".repoman")
        try:
            path.write_text(config_io.save_config(self._repos), encoding="utf-8")
            self._toast_overlay.add_toast(Adw.Toast(title=f"Config saved to {path.name}", timeout=3))
        except OSError as exc:
            self._toast_overlay.add_toast(Adw.Toast(title=f"Failed to save config: {exc}", timeout=5))

    def _load_config(self) -> None:
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Load repository configuration")
        f = Gtk.FileFilter()
        f.add_pattern("*.repoman")
        f.set_name("Repoman configs (*.repoman)")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dialog.set_filters(store)
        dialog.open(self, None, self._on_load_config_chosen)

    def _on_load_config_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        from .. import config_io

        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        path = Path(gfile.get_path())
        try:
            saved = config_io.load_config(path)
        except (json.JSONDecodeError, ValueError, OSError, KeyError) as exc:
            self._toast_overlay.add_toast(Adw.Toast(title=f"Failed to read config: {exc}", timeout=5))
            return
        self._apply_config_load(saved)

    def _apply_config_load(self, saved: list[dict]) -> None:
        from .. import config_io
        from ..writer import repo_to_deb822

        matched, missing = config_io.match_repos(saved, self._repos)

        writes = []
        changed_repos: list[tuple[Repository, bool]] = []
        for entry, live in matched:
            if entry.get("enabled") != live.enabled:
                original = live.enabled
                live.enabled = entry["enabled"]
                writes.append({"path": str(live.source_file), "content": repo_to_deb822(live)})
                changed_repos.append((live, original))

        if writes:
            payload = json.dumps({"action": "write_files", "writes": writes, "deletes": []})

            def _write() -> None:
                result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)
                if result.returncode == 0:
                    GLib.idle_add(self._after_config_write_success, len(writes), missing)
                else:
                    GLib.idle_add(self._after_config_write_failure, result.stderr.strip(), changed_repos)

            threading.Thread(target=_write, daemon=True).start()
        else:
            self._after_config_write_success(0, missing)

    def _after_config_write_success(self, changed: int, missing: list[dict]) -> bool:
        if changed:
            self._on_repos_updated(None)
            self._toast_overlay.add_toast(
                Adw.Toast(
                    title=f"Updated {changed} {'repository' if changed == 1 else 'repositories'}",
                    timeout=3,
                )
            )
        if missing:
            self._show_missing_repos_dialog(missing)
        elif changed == 0:
            self._toast_overlay.add_toast(Adw.Toast(title="No changes — system already matches config", timeout=3))
        return GLib.SOURCE_REMOVE

    def _after_config_write_failure(self, message: str, changed_repos: list[tuple[Repository, bool]]) -> bool:
        for live, original in changed_repos:
            live.enabled = original
        for row in self._rows:
            row.refresh(row.repo)
        self._toast_overlay.add_toast(Adw.Toast(title=f"Failed to apply config: {message}", timeout=5))
        return GLib.SOURCE_REMOVE

    def _show_missing_repos_dialog(self, missing: list[dict]) -> None:
        n = len(missing)
        enabled_count = sum(1 for m in missing if m.get("enabled", True))
        has_signed_by = any(m.get("signed_by") for m in missing)

        body = (
            f"{n} {'repository' if n == 1 else 'repositories'} from the config "
            f"{'was' if n == 1 else 'were'} not found on this system."
        )
        if has_signed_by:
            body += (
                "\n\nSome of these repositories reference GPG signing keys that may not "
                "be installed. You may need to add the keys manually after creating them."
            )

        dialog = Adw.AlertDialog.new(f"{n} {'repository' if n == 1 else 'repositories'} not found", body)
        dialog.add_response("skip", "Skip")
        if 0 < enabled_count < n:
            dialog.add_response("enabled-only", f"Add {enabled_count} enabled")
        dialog.add_response("all", f"Add all {n}")
        dialog.set_default_response("skip")
        dialog.set_close_response("skip")
        dialog.connect("response", lambda _d, r: self._on_missing_response(r, missing))
        dialog.present(self)

    def _on_missing_response(self, response: str, missing: list[dict]) -> None:
        from .. import config_io
        from ..writer import repo_to_deb822

        if response == "skip":
            return
        to_create = missing if response == "all" else [m for m in missing if m.get("enabled", True)]
        if not to_create:
            return

        writes = []
        for e in to_create:
            repo = config_io.entry_to_repository(e)
            writes.append({"path": str(repo.source_file), "content": repo_to_deb822(repo)})
        payload = json.dumps({"action": "write_files", "writes": writes, "deletes": []})

        def _write() -> None:
            result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)
            if result.returncode == 0:
                GLib.idle_add(self._on_missing_create_success, len(to_create))
            else:
                GLib.idle_add(
                    self._toast_overlay.add_toast,
                    Adw.Toast(title=f"Failed to create repositories: {result.stderr.strip()}", timeout=5),
                )

        threading.Thread(target=_write, daemon=True).start()

    def _on_missing_create_success(self, count: int) -> bool:
        self._on_repos_updated(None)
        self._toast_overlay.add_toast(
            Adw.Toast(
                title=f"Created {count} {'repository' if count == 1 else 'repositories'}",
                timeout=3,
            )
        )
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------
    # Help / About
    # ------------------------------------------------------------------

    def _show_shortcuts(self) -> None:
        win = Gtk.Window(
            title="Keyboard Shortcuts",
            transient_for=self,
            modal=True,
            default_width=420,
            resizable=False,
        )
        center_on_parent(win)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
            spacing=12,
        )
        group = Adw.PreferencesGroup(title="Repoman")
        for label, accel in [
            ("Search repositories", "<Primary>f"),
            ("Open upgrade assistant", "<Primary>u"),
            ("Keyboard shortcuts", "<Primary>F1"),
        ]:
            row = Adw.ActionRow(title=label)
            row.add_suffix(Gtk.ShortcutLabel(accelerator=accel))
            group.add(row)
        box.append(group)
        win.set_child(box)
        win.present()

    def _open_help(self) -> None:
        Gtk.show_uri(self, "https://github.com/Tecktron/repoman", 0)

    def _show_about(self) -> None:
        win = Gtk.Window(
            title="About Repoman",
            transient_for=self,
            modal=True,
            default_width=360,
            resizable=False,
        )
        center_on_parent(win)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
            spacing=16,
        )

        # Icon + name + version
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("io.github.Tecktron.repoman")
        icon.set_pixel_size(64)
        header_box.append(icon)
        name_label = Gtk.Label(label="Repoman")
        name_label.add_css_class("title-1")
        header_box.append(name_label)
        header_box.append(Gtk.Label(label="Version 0.1.0", css_classes=["dim-label"]))
        box.append(header_box)

        box.append(Gtk.Separator())

        # Info group
        info_group = Adw.PreferencesGroup()
        desc_row = Adw.ActionRow(
            title="Description",
            subtitle="GTK4 APT repository manager for Ubuntu/Xubuntu. "
            "Helps you review and re-enable third-party repos after an upgrade.",
        )
        desc_row.set_subtitle_selectable(True)
        info_group.add(desc_row)

        author_row = Adw.ActionRow(title="Author", subtitle="Tecktron")
        info_group.add(author_row)

        license_row = Adw.ActionRow(title="License", subtitle="GNU General Public License v3.0")
        info_group.add(license_row)

        gh_row = Adw.ActionRow(title="Source code", subtitle="github.com/Tecktron/repoman")
        gh_row.set_subtitle_selectable(True)
        gh_btn = Gtk.Button.new_from_icon_name("applications-internet-symbolic")
        gh_btn.set_tooltip_text("Open on GitHub")
        gh_btn.add_css_class("flat")
        gh_btn.set_valign(Gtk.Align.CENTER)
        gh_btn.connect("clicked", lambda _: Gtk.show_uri(win, "https://github.com/Tecktron/repoman", 0))
        gh_row.add_suffix(gh_btn)
        info_group.add(gh_row)

        box.append(info_group)
        win.set_child(box)
        win.present()
