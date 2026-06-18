from __future__ import annotations

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ..checker import get_network_error, reset_network_state
from ..models import Repository
from ..parser import Parser
from ..paths import PKEXEC, POLKIT_HELPER
from ..utils import repos_needing_attention
from .detail_pane import DetailPane
from .repo_row import RepoRow
from .wizard.dialog import RepomanWizardDialog


class RepomanWindow(Adw.ApplicationWindow):
    __gtype_name__ = "RepomanWindow"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            title="repoman",
            default_width=900,
            default_height=600,
            **kwargs,
        )
        self._parser = Parser()
        self._repos: list[Repository] = []
        self._wizard: RepomanWizardDialog | None = None
        self._rows: list[RepoRow] = []

        self._build_ui()
        # Load repos after the window is realized so the spinner shows
        self.connect("realize", lambda _: GLib.idle_add(self._load_repos))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Root toast overlay
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(outer_box)

        # Banner (upgrade alert — hidden by default)
        self._banner = Adw.Banner(revealed=False)
        self._banner.connect("button-clicked", lambda _: self.open_upgrade_wizard())
        outer_box.append(self._banner)

        # Main split pane
        split = Adw.OverlaySplitView()
        outer_box.append(split)

        # --- Sidebar ---
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_title_widget(Gtk.Label(label="repoman"))

        # Search button
        self._search_button = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self._search_button.set_tooltip_text("Search repositories")
        sidebar_header.pack_end(self._search_button)

        # Menu button
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_tooltip_text("Main menu")
        menu_button.set_menu_model(self._build_menu())
        sidebar_header.pack_end(menu_button)

        sidebar_box.append(sidebar_header)

        # Search bar
        self._search_bar = Gtk.SearchBar(search_mode_enabled=False)
        self._search_entry = Gtk.SearchEntry(hexpand=True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_bar.set_child(self._search_entry)
        self._search_bar.connect_entry(self._search_entry)
        self._search_button.bind_property(
            "active",
            self._search_bar,
            "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL,
        )
        sidebar_box.append(self._search_bar)

        # Repo list
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.set_filter_func(self._filter_row)
        self._list_box.connect("row-selected", self._on_row_selected)
        scroll.set_child(self._list_box)
        sidebar_box.append(scroll)

        # Loading spinner (shown while parsing)
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
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        detail_header = Adw.HeaderBar(show_title=False)
        detail_box.append(detail_header)

        self._detail_pane = DetailPane(vexpand=True)
        self._detail_pane.connect("repo-saved", self._on_repo_saved)
        detail_box.append(self._detail_pane)

        split.set_content(detail_box)

        # Keyboard shortcuts
        self._setup_actions()

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append("Upgrade assistant…", "win.upgrade-wizard")
        menu.append("Keyboard shortcuts", "win.show-shortcuts")
        menu.append_section(None, self._build_help_section())
        return menu

    def _build_help_section(self) -> Gio.Menu:
        section = Gio.Menu()
        section.append("Help", "win.open-help")
        section.append("About repoman", "win.about")
        return section

    def _setup_actions(self) -> None:
        actions = [
            ("upgrade-wizard", self.open_upgrade_wizard),
            ("show-shortcuts", self._show_shortcuts),
            ("open-help", self._open_help),
            ("about", self._show_about),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

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
        import json
        import subprocess

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
    # Wizard
    # ------------------------------------------------------------------

    def open_upgrade_wizard(self) -> None:
        if self._wizard and self._wizard.get_visible():
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
        self._wizard.connect("closed", lambda _: setattr(self, "_wizard", None))
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
    # Help / About
    # ------------------------------------------------------------------

    def _show_shortcuts(self) -> None:
        builder = Gtk.Builder()
        builder.add_from_string(_SHORTCUTS_UI)
        window = builder.get_object("shortcuts_window")
        window.set_transient_for(self)
        window.present()

    def _open_help(self) -> None:
        Gtk.show_uri(self, "https://github.com/Tecktron/repoman", 0)

    def _show_about(self) -> None:
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="repoman",
            application_icon="io.github.Tecktron.repoman",
            developer_name="Tecktron",
            version="0.1.0",
            website="https://github.com/Tecktron/repoman",
            issue_url="https://github.com/Tecktron/repoman/issues",
            license_type=Gtk.License.GPL_3_0,
            comments="GTK4 APT repository manager for Ubuntu/Xubuntu.\n\n"
            "Helps you review and re-enable third-party repos after an Ubuntu upgrade.",
        )
        about.present()


_SHORTCUTS_UI = """
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <object class="GtkShortcutsWindow" id="shortcuts_window">
    <property name="modal">true</property>
    <child>
      <object class="GtkShortcutsSection">
        <property name="title">repoman</property>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title">General</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Search repositories</property>
                <property name="accelerator">&lt;ctrl&gt;f</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Open upgrade assistant</property>
                <property name="accelerator">&lt;ctrl&gt;u</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title">Keyboard shortcuts</property>
                <property name="accelerator">&lt;ctrl&gt;F1</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>
"""
