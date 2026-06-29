from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from .. import gpg
from ..models import Repository
from ..paths import PKEXEC, POLKIT_HELPER
from ..writer import repo_to_deb822
from .position import center_on_parent

# ---------------------------------------------------------------------------
# Add window — three tabs: Fetch / Browse existing file / Paste
# ---------------------------------------------------------------------------

_ADD_TAB_FETCH = 0
_ADD_TAB_BROWSE = 1
_ADD_TAB_PASTE = 2


class KeyAddWindow(Gtk.Window):
    """
    Modal window for adding a GPG signing key to a repository that has none.

    Three tabs let the user choose their key source:
      Fetch from URL — download from a URL (or auto-detect for PPAs)
      Use existing file — point to an already-installed keyring file
      Paste — type or paste an ASCII-armored key block

    Save is only enabled once content is available on the active tab.
    Emits "key-saved" with the installed key path string on success.
    """

    __gtype_name__ = "RepomanKeyAddWindow"

    key_saved = GObject.Signal("key-saved", arg_types=(str,))

    def __init__(self, repo: Repository, **kwargs) -> None:
        super().__init__(
            title="Add signing key",
            modal=True,
            resizable=False,
            default_width=540,
            **kwargs,
        )
        self._repo = repo
        self._fetched_bytes: bytes | None = None
        self._selected_file: str | None = None
        self._build_ui()
        self.connect("map", lambda w: GLib.idle_add(lambda: w.set_focus(None) or GLib.SOURCE_REMOVE))
        center_on_parent(self)

    def _build_ui(self) -> None:
        outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=18,
            margin_bottom=18,
            margin_start=18,
            margin_end=18,
        )

        # Key file path — empty in add mode
        path_group = Adw.PreferencesGroup(title="Key file location")
        self._path_row = Adw.EntryRow(title="Key file path")
        self._path_row.connect("changed", lambda _: self._update_sensitivity())
        path_group.add(self._path_row)
        outer.append(path_group)

        self._notebook = Gtk.Notebook()
        self._notebook.connect("switch-page", self._on_tab_switched)

        # ── Tab 0: Fetch from URL ─────────────────────────────────────
        fetch_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        fetch_group = Adw.PreferencesGroup()
        self._url_row = Adw.EntryRow(title="Key URL")
        self._url_row.set_input_purpose(Gtk.InputPurpose.URL)
        self._url_row.connect("changed", self._on_url_changed)
        self._fetch_btn = Gtk.Button(label="Fetch", valign=Gtk.Align.CENTER)
        self._fetch_btn.add_css_class("flat")
        self._fetch_btn.connect("clicked", self._on_fetch_clicked)
        self._url_row.add_suffix(self._fetch_btn)
        fetch_group.add(self._url_row)
        fetch_box.append(fetch_group)

        self._fetch_status_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._fetch_status_lbl.set_visible(False)
        fetch_box.append(self._fetch_status_lbl)

        self._notebook.append_page(fetch_box, Gtk.Label(label="Fetch from URL"))

        # ── Tab 1: Use existing file ──────────────────────────────────
        browse_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        browse_box.append(
            Gtk.Label(
                label="Select a GPG keyring file already installed on this system.\n"
                "The repository will be updated to reference its path.",
                xalign=0,
                wrap=True,
            )
        )
        browse_btn = Gtk.Button(label="Browse for key file…", halign=Gtk.Align.START)
        browse_btn.connect("clicked", self._on_browse_clicked)
        browse_box.append(browse_btn)

        self._browse_lbl = Gtk.Label(label="No file selected", xalign=0, wrap=True, selectable=True)
        self._browse_lbl.add_css_class("dim-label")
        browse_box.append(self._browse_lbl)

        self._notebook.append_page(browse_box, Gtk.Label(label="Use existing file"))

        # ── Tab 2: Paste ─────────────────────────────────────────────
        paste_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        paste_box.append(
            Gtk.Label(
                label="Paste an ASCII-armored public key\n(begins with -----BEGIN PGP PUBLIC KEY BLOCK-----).",
                xalign=0,
                wrap=True,
            )
        )
        paste_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            height_request=160,
        )
        paste_scroll.add_css_class("card")
        self._paste_view = Gtk.TextView(
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            margin_top=6,
            margin_bottom=6,
            margin_start=6,
            margin_end=6,
        )
        self._paste_view.get_buffer().connect("changed", lambda _: self._update_sensitivity())
        paste_scroll.set_child(self._paste_view)
        paste_box.append(paste_scroll)

        self._notebook.append_page(paste_box, Gtk.Label(label="Paste"))

        outer.append(self._notebook)

        self._error_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._error_lbl.add_css_class("warning")
        self._error_lbl.set_visible(False)
        outer.append(self._error_lbl)

        btn_row = Gtk.Box(spacing=6, halign=Gtk.Align.END, margin_top=4)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        self._save_btn = Gtk.Button(label="Save key")
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.set_sensitive(False)
        self._save_btn.connect("clicked", self._on_save_clicked)
        btn_row.append(cancel_btn)
        btn_row.append(self._save_btn)
        outer.append(btn_row)

        self.set_child(outer)
        self._update_sensitivity()

    # ------------------------------------------------------------------
    # Sensitivity
    # ------------------------------------------------------------------

    def _on_tab_switched(self, _nb, _page, _num: int) -> None:
        self._error_lbl.set_visible(False)
        self._update_sensitivity()

    def _update_sensitivity(self) -> None:
        tab = self._notebook.get_current_page()
        if tab == _ADD_TAB_FETCH:
            enabled = self._fetched_bytes is not None
        elif tab == _ADD_TAB_BROWSE:
            enabled = self._selected_file is not None
        else:
            buf = self._paste_view.get_buffer()
            enabled = bool(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip())
        self._save_btn.set_sensitive(enabled)

    # ------------------------------------------------------------------
    # Tab 0 — Fetch
    # ------------------------------------------------------------------

    def _on_url_changed(self, _row) -> None:
        self._fetched_bytes = None
        self._fetch_status_lbl.set_visible(False)
        url = self._url_row.get_text().strip()
        if url and not self._path_row.get_text().strip():
            host = urlparse(url).netloc or url
            sanitized = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
            self._path_row.set_text(f"/usr/share/keyrings/{sanitized}.gpg")
        self._update_sensitivity()

    def _on_fetch_clicked(self, _btn: Gtk.Button) -> None:
        url = self._url_row.get_text().strip()
        self._error_lbl.set_visible(False)
        self._fetch_status_lbl.set_visible(False)
        if url:
            self._set_busy(True)
            threading.Thread(target=self._do_fetch_url, args=(url,), daemon=True).start()
        elif self._repo.is_ppa and self._repo.ppa_owner and self._repo.ppa_name:
            self._set_busy(True)
            threading.Thread(
                target=self._do_fetch_ppa,
                args=(self._repo.ppa_owner, self._repo.ppa_name),
                daemon=True,
            ).start()
        else:
            self._show_error("Enter a key URL above, or select a PPA repository first.")

    def _do_fetch_url(self, url: str) -> None:
        GLib.idle_add(self._on_fetch_done, *gpg.fetch_key(url))

    def _do_fetch_ppa(self, owner: str, ppa: str) -> None:
        GLib.idle_add(self._on_fetch_done, *gpg.fetch_ppa_key(owner, ppa))

    def _on_fetch_done(self, key_bytes: bytes | None, err: str | None) -> bool:
        self._set_busy(False)
        if err or not key_bytes:
            self._show_error(f"Fetch failed: {err or 'empty response'}")
            return GLib.SOURCE_REMOVE
        self._fetched_bytes = key_bytes
        self._fetch_status_lbl.set_label(f"Key fetched — {len(key_bytes):,} bytes")
        self._fetch_status_lbl.remove_css_class("warning")
        self._fetch_status_lbl.add_css_class("success")
        self._fetch_status_lbl.set_visible(True)
        self._error_lbl.set_visible(False)
        self._update_sensitivity()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------
    # Tab 1 — Browse
    # ------------------------------------------------------------------

    def _on_browse_clicked(self, _btn: Gtk.Button) -> None:
        key_filter = Gtk.FileFilter()
        key_filter.set_name("GPG key files (*.gpg, *.asc, *.pgp)")
        key_filter.add_pattern("*.gpg")
        key_filter.add_pattern("*.asc")
        key_filter.add_pattern("*.pgp")
        any_filter = Gtk.FileFilter()
        any_filter.set_name("All files")
        any_filter.add_pattern("*")
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        filters.append(key_filter)
        filters.append(any_filter)
        dialog = Gtk.FileDialog(title="Choose GPG key file", modal=True)
        dialog.set_filters(filters)
        dialog.set_default_filter(key_filter)
        keyrings = Path("/usr/share/keyrings")
        if keyrings.exists():
            dialog.set_initial_folder(Gio.File.new_for_path(str(keyrings)))
        dialog.open(self, None, self._on_browse_done)

    def _on_browse_done(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        if not gfile:
            return
        path = gfile.get_path()
        self._selected_file = path
        self._browse_lbl.set_label(path)
        self._browse_lbl.remove_css_class("dim-label")
        self._path_row.set_text(path)
        self._update_sensitivity()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save_clicked(self, _btn: Gtk.Button) -> None:
        self._save_btn.set_sensitive(False)
        self._save_btn.set_label("Saving…")
        self._error_lbl.set_visible(False)
        threading.Thread(target=self._do_save, daemon=True).start()

    def _do_save(self) -> None:
        key_path = self._path_row.get_text().strip()
        tab = self._notebook.get_current_page()
        writes = []

        if tab == _ADD_TAB_FETCH:
            if not key_path:
                GLib.idle_add(self._on_save_failed, "Key file path is required.")
                return
            writes.append({"path": key_path, "content": gpg.key_to_b64(self._fetched_bytes), "encoding": "base64"})
        elif tab == _ADD_TAB_BROWSE:
            key_path = self._selected_file or key_path
            if not key_path:
                GLib.idle_add(self._on_save_failed, "No file selected.")
                return
        else:
            buf = self._paste_view.get_buffer()
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
            if not content:
                GLib.idle_add(self._on_save_failed, "No key content provided.")
                return
            if not key_path:
                GLib.idle_add(self._on_save_failed, "Key file path is required.")
                return
            valid, error = gpg.verify_key(content)
            if not valid:
                GLib.idle_add(self._on_save_failed, f"Key verification failed: {error}")
                return
            writes.append({"path": key_path, "content": gpg.key_to_b64(content.encode()), "encoding": "base64"})

        self._repo.signed_by = key_path or None
        writes.append({"path": str(self._repo.source_file), "content": repo_to_deb822(self._repo)})
        payload = json.dumps({"action": "write_files", "writes": writes, "deletes": []})
        result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)
        if result.returncode == 0:
            GLib.idle_add(self._on_save_success, key_path)
        else:
            GLib.idle_add(self._on_save_failed, result.stderr.strip())

    def _on_save_success(self, key_path: str) -> bool:
        self.emit("key-saved", key_path)
        self.close()
        return GLib.SOURCE_REMOVE

    def _on_save_failed(self, message: str) -> bool:
        self._show_error(message)
        self._save_btn.set_sensitive(True)
        self._save_btn.set_label("Save key")
        return GLib.SOURCE_REMOVE

    def _set_busy(self, busy: bool) -> None:
        self._fetch_btn.set_sensitive(not busy)
        self._save_btn.set_sensitive(not busy)

    def _show_error(self, message: str) -> None:
        self._error_lbl.set_label(message)
        self._error_lbl.set_visible(True)


# ---------------------------------------------------------------------------
# Edit window — current key content + Update tab
# ---------------------------------------------------------------------------

_EDIT_TAB_CONTENT = 0
_EDIT_TAB_UPDATE = 1


class KeyEditWindow(Gtk.Window):
    """
    Modal window for editing an existing GPG signing key.

    Tab "Key content": shows the current key file content (editable).
      - Path shown in warning style if the file is missing.
      - Text area empty when file is missing; user can paste a replacement.
    Tab "Update": replace the key from a new file (Browse) or a URL (Fetch).

    Emits "key-saved" with the (possibly changed) key path on success.
    """

    __gtype_name__ = "RepomanKeyEditWindow"

    key_saved = GObject.Signal("key-saved", arg_types=(str,))

    def __init__(self, repo: Repository, **kwargs) -> None:
        super().__init__(
            title="Edit signing key",
            modal=True,
            resizable=False,
            default_width=540,
            **kwargs,
        )
        self._repo = repo
        self._original_signed_by = repo.signed_by or ""
        signed_by = self._original_signed_by
        self._file_existed = bool(signed_by) and Path(signed_by).exists()
        self._original_content = ""
        self._content_trusted = False
        self._update_selected_file: str | None = None
        self._update_fetched_bytes: bytes | None = None
        self._build_ui()
        self.connect("map", lambda w: GLib.idle_add(lambda: w.set_focus(None) or GLib.SOURCE_REMOVE))
        center_on_parent(self)

    def _build_ui(self) -> None:
        outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=18,
            margin_bottom=18,
            margin_start=18,
            margin_end=18,
        )

        signed_by = self._original_signed_by

        # Key file path — always editable
        path_group = Adw.PreferencesGroup(title="Key file location")
        self._path_row = Adw.EntryRow(title="Key file path")
        self._path_row.set_text(signed_by)
        if not self._file_existed and signed_by:
            self._path_row.add_css_class("error")
        self._path_row.connect("changed", lambda _: self._update_sensitivity())
        path_group.add(self._path_row)
        outer.append(path_group)

        # Notebook
        self._notebook = Gtk.Notebook()
        self._notebook.connect("switch-page", self._on_tab_switched)

        # ── Tab 0: Key content ────────────────────────────────────────
        content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )

        if not self._file_existed and signed_by:
            missing_lbl = Gtk.Label(
                label="Key file not found. Paste a replacement key below to create it.",
                xalign=0,
                wrap=True,
            )
            missing_lbl.add_css_class("warning")
            content_box.append(missing_lbl)

        content_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            height_request=200,
        )
        content_scroll.add_css_class("card")
        self._content_view = Gtk.TextView(
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            margin_top=6,
            margin_bottom=6,
            margin_start=6,
            margin_end=6,
        )
        if self._file_existed:
            loaded = gpg.read_key_content(Path(signed_by))
            if loaded:
                self._original_content = loaded
                self._content_view.get_buffer().set_text(loaded)
                self._content_trusted = True
        self._content_view.get_buffer().connect("changed", self._on_content_changed)
        content_scroll.set_child(self._content_view)
        content_box.append(content_scroll)

        self._notebook.append_page(content_box, Gtk.Label(label="Key content"))

        # ── Tab 1: Update ─────────────────────────────────────────────
        update_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )

        # From file
        file_group = Adw.PreferencesGroup(title="Replace from file")
        file_row = Adw.ActionRow(
            title="Browse for key file…",
            subtitle="Select a GPG keyring file from disk",
            activatable=True,
        )
        file_row.connect("activated", lambda _: self._on_browse_clicked())
        file_row.add_suffix(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
        file_group.add(file_row)
        update_box.append(file_group)

        self._selected_file_lbl = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._selected_file_lbl.add_css_class("dim-label")
        self._selected_file_lbl.set_visible(False)
        update_box.append(self._selected_file_lbl)

        # From URL
        url_group = Adw.PreferencesGroup(title="Replace from URL")
        self._update_url_row = Adw.EntryRow(title="Key URL")
        self._update_url_row.set_input_purpose(Gtk.InputPurpose.URL)
        self._update_url_row.connect("changed", self._on_update_url_changed)
        self._update_fetch_btn = Gtk.Button(label="Fetch", valign=Gtk.Align.CENTER)
        self._update_fetch_btn.add_css_class("flat")
        self._update_fetch_btn.connect("clicked", self._on_update_fetch_clicked)
        self._update_url_row.add_suffix(self._update_fetch_btn)
        url_group.add(self._update_url_row)
        update_box.append(url_group)

        self._fetch_status_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._fetch_status_lbl.set_visible(False)
        update_box.append(self._fetch_status_lbl)

        self._notebook.append_page(update_box, Gtk.Label(label="Update"))

        outer.append(self._notebook)

        # Error label
        self._error_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._error_lbl.add_css_class("warning")
        self._error_lbl.set_visible(False)
        outer.append(self._error_lbl)

        # Button row — action button label changes per tab
        btn_row = Gtk.Box(spacing=6, halign=Gtk.Align.END, margin_top=4)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        self._action_btn = Gtk.Button(label="Save changes")
        self._action_btn.add_css_class("suggested-action")
        self._action_btn.set_sensitive(False)
        self._action_btn.connect("clicked", self._on_action_clicked)
        btn_row.append(cancel_btn)
        btn_row.append(self._action_btn)
        outer.append(btn_row)

        self.set_child(outer)
        self._update_sensitivity()

    # ------------------------------------------------------------------
    # Sensitivity
    # ------------------------------------------------------------------

    def _on_tab_switched(self, _nb, _page, num: int) -> None:
        self._error_lbl.set_visible(False)
        self._action_btn.set_label("Save changes" if num == _EDIT_TAB_CONTENT else "Replace key")
        self._update_sensitivity()

    def _update_sensitivity(self) -> None:
        tab = self._notebook.get_current_page()
        if tab == _EDIT_TAB_CONTENT:
            buf = self._content_view.get_buffer()
            current = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
            current_path = self._path_row.get_text().strip()
            enabled = bool(current) and (
                current != self._original_content or current_path != self._original_signed_by or not self._file_existed
            )
        else:
            enabled = self._update_selected_file is not None or self._update_fetched_bytes is not None
        self._action_btn.set_sensitive(enabled)

    def _on_content_changed(self, _buf) -> None:
        self._content_trusted = False
        self._update_sensitivity()

    # ------------------------------------------------------------------
    # Tab 1 — Update: Browse
    # ------------------------------------------------------------------

    def _on_browse_clicked(self) -> None:
        key_filter = Gtk.FileFilter()
        key_filter.set_name("GPG key files (*.gpg, *.asc, *.pgp)")
        key_filter.add_pattern("*.gpg")
        key_filter.add_pattern("*.asc")
        key_filter.add_pattern("*.pgp")
        any_filter = Gtk.FileFilter()
        any_filter.set_name("All files")
        any_filter.add_pattern("*")
        filters = Gio.ListStore(item_type=Gtk.FileFilter)
        filters.append(key_filter)
        filters.append(any_filter)
        dialog = Gtk.FileDialog(title="Choose GPG key file", modal=True)
        dialog.set_filters(filters)
        dialog.set_default_filter(key_filter)
        keyrings = Path("/usr/share/keyrings")
        if keyrings.exists():
            dialog.set_initial_folder(Gio.File.new_for_path(str(keyrings)))
        dialog.open(self, None, self._on_browse_done)

    def _on_browse_done(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        if not gfile:
            return
        path = gfile.get_path()
        self._update_selected_file = path
        self._update_fetched_bytes = None  # clear the other source
        self._fetch_status_lbl.set_visible(False)
        self._selected_file_lbl.set_label(f"Selected: {path}")
        self._selected_file_lbl.remove_css_class("dim-label")
        self._selected_file_lbl.set_visible(True)
        self._update_sensitivity()

    # ------------------------------------------------------------------
    # Tab 1 — Update: Fetch from URL
    # ------------------------------------------------------------------

    def _on_update_url_changed(self, _row) -> None:
        self._update_fetched_bytes = None
        self._fetch_status_lbl.set_visible(False)
        self._update_sensitivity()

    def _on_update_fetch_clicked(self, _btn: Gtk.Button) -> None:
        url = self._update_url_row.get_text().strip()
        self._error_lbl.set_visible(False)
        self._fetch_status_lbl.set_visible(False)
        if not url:
            self._show_error("Enter a key URL to fetch from.")
            return
        self._update_fetch_btn.set_sensitive(False)
        self._action_btn.set_sensitive(False)
        threading.Thread(target=self._do_update_fetch, args=(url,), daemon=True).start()

    def _do_update_fetch(self, url: str) -> None:
        GLib.idle_add(self._on_update_fetch_done, *gpg.fetch_key(url))

    def _on_update_fetch_done(self, key_bytes: bytes | None, err: str | None) -> bool:
        self._update_fetch_btn.set_sensitive(True)
        if err or not key_bytes:
            self._show_error(f"Fetch failed: {err or 'empty response'}")
            return GLib.SOURCE_REMOVE
        self._update_fetched_bytes = key_bytes
        self._update_selected_file = None  # clear the other source
        self._selected_file_lbl.set_visible(False)
        self._fetch_status_lbl.set_label(f"Key fetched — {len(key_bytes):,} bytes")
        self._fetch_status_lbl.remove_css_class("warning")
        self._fetch_status_lbl.add_css_class("success")
        self._fetch_status_lbl.set_visible(True)
        self._error_lbl.set_visible(False)
        self._update_sensitivity()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------
    # Action (Save / Replace)
    # ------------------------------------------------------------------

    def _on_action_clicked(self, _btn: Gtk.Button) -> None:
        self._action_btn.set_sensitive(False)
        self._action_btn.set_label("Saving…")
        self._error_lbl.set_visible(False)
        threading.Thread(target=self._do_action, daemon=True).start()

    def _do_action(self) -> None:
        tab = self._notebook.get_current_page()
        key_path = self._path_row.get_text().strip()
        writes = []

        if tab == _EDIT_TAB_CONTENT:
            buf = self._content_view.get_buffer()
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
            if not content:
                GLib.idle_add(self._on_action_failed, "No key content provided.")
                return
            if not key_path:
                GLib.idle_add(self._on_action_failed, "Key file path is required.")
                return
            if not self._content_trusted:
                valid, error = gpg.verify_key(content)
                if not valid:
                    GLib.idle_add(self._on_action_failed, f"Key verification failed: {error}")
                    return
            writes.append({"path": key_path, "content": gpg.key_to_b64(content.encode()), "encoding": "base64"})

        else:  # _EDIT_TAB_UPDATE
            if self._update_fetched_bytes is not None:
                # Write fetched bytes to the current key path
                if not key_path:
                    GLib.idle_add(self._on_action_failed, "Key file path is required.")
                    return
                writes.append(
                    {
                        "path": key_path,
                        "content": gpg.key_to_b64(self._update_fetched_bytes),
                        "encoding": "base64",
                    }
                )
            elif self._update_selected_file:
                # Point signed_by at the selected file (no content copy needed)
                key_path = self._update_selected_file
            else:
                GLib.idle_add(self._on_action_failed, "No update source selected.")
                return

        self._repo.signed_by = key_path or None
        writes.append({"path": str(self._repo.source_file), "content": repo_to_deb822(self._repo)})
        payload = json.dumps({"action": "write_files", "writes": writes, "deletes": []})
        result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)
        if result.returncode == 0:
            GLib.idle_add(self._on_action_success, key_path)
        else:
            GLib.idle_add(self._on_action_failed, result.stderr.strip())

    def _on_action_success(self, key_path: str) -> bool:
        self.emit("key-saved", key_path)
        self.close()
        return GLib.SOURCE_REMOVE

    def _on_action_failed(self, message: str) -> bool:
        self._show_error(message)
        tab = self._notebook.get_current_page()
        self._action_btn.set_label("Save changes" if tab == _EDIT_TAB_CONTENT else "Replace key")
        self._action_btn.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _show_error(self, message: str) -> None:
        self._error_lbl.set_label(message)
        self._error_lbl.set_visible(True)
