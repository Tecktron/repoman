from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, GObject, Gtk

from .. import gpg
from ..models import FileFormat, Repository
from ..paths import PKEXEC, POLKIT_HELPER
from ..source_parse import (
    parse_source_block as _parse_source_block,
    uri_to_key_filename as _uri_to_key_filename,
    uri_to_source_filename as _uri_to_source_filename,
)
from ..utils import get_current_codename
from ..writer import repo_to_deb822
from .position import center_on_parent

_SOURCES_DIR = Path("/etc/apt/sources.list.d")
_KEYRINGS_DIR = Path("/usr/share/keyrings")


def _unique_source_path(name: str) -> Path:
    path = _SOURCES_DIR / name
    if not path.exists():
        return path
    stem = path.stem
    for i in range(1, 100):
        candidate = _SOURCES_DIR / f"{stem}-{i}.sources"
        if not candidate.exists():
            return candidate
    return path


class AddRepoDialog(Gtk.Window):
    """
    Three-tab dialog for adding a new APT repository.

    Tab 0 (PPA): enter a Launchpad PPA address (ppa:owner/name).
    Tab 1 (URL): paste a deb one-liner or DEB822 block + optional GPG key URL.
    Tab 2 (Manual): fill individual fields.

    Emits "repo-added" with the new Repository object on success.
    """

    __gtype_name__ = "RepomanAddRepoDialog"

    repo_added = GObject.Signal("repo-added", arg_types=(object,))

    def __init__(self, **kwargs) -> None:
        super().__init__(
            title="Add Repository",
            modal=True,
            resizable=False,
            default_width=520,
            **kwargs,
        )
        self.set_icon_name("io.github.Tecktron.repoman")
        self._build_ui()
        center_on_parent(self)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._notebook = Gtk.Notebook()
        self._notebook.set_margin_top(12)
        self._notebook.set_margin_bottom(0)
        self._notebook.set_margin_start(12)
        self._notebook.set_margin_end(12)
        # switch-page connected after _add_btn exists — signal fires on first append_page()

        # Tab 0 — PPA
        ppa_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=6,
            margin_end=6,
        )
        ppa_box.append(
            Gtk.Label(
                label="Enter a Launchpad PPA address. The signing key is fetched and installed automatically.",
                xalign=0,
                wrap=True,
            )
        )
        ppa_group = Adw.PreferencesGroup()
        self._ppa_row = Adw.EntryRow(title="PPA address  (ppa:owner/name)")
        self._ppa_row.connect("changed", self._on_ppa_changed)
        ppa_group.add(self._ppa_row)
        ppa_box.append(ppa_group)
        self._ppa_error_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._ppa_error_lbl.add_css_class("warning")
        self._ppa_error_lbl.set_visible(False)
        ppa_box.append(self._ppa_error_lbl)
        self._notebook.append_page(ppa_box, Gtk.Label(label="PPA"))

        # Tab 1 — URL
        url_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=6,
            margin_end=6,
        )
        url_box.append(
            Gtk.Label(
                label="Paste a sources line (deb …) or a full DEB822 block:",
                xalign=0,
            )
        )
        url_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            height_request=130,
        )
        url_scroll.add_css_class("card")
        self._auto_text = Gtk.TextView(
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            margin_top=6,
            margin_bottom=6,
            margin_start=6,
            margin_end=6,
        )
        url_scroll.set_child(self._auto_text)
        url_box.append(url_scroll)
        url_key_group = Adw.PreferencesGroup()
        self._auto_key_row = Adw.EntryRow(title="GPG key URL (optional)")
        self._auto_key_row.set_input_purpose(Gtk.InputPurpose.URL)
        url_key_group.add(self._auto_key_row)
        url_box.append(url_key_group)
        self._auto_error_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._auto_error_lbl.add_css_class("warning")
        self._auto_error_lbl.set_visible(False)
        url_box.append(self._auto_error_lbl)
        self._notebook.append_page(url_box, Gtk.Label(label="URL"))
        self._auto_text.get_buffer().connect("changed", self._on_auto_changed)

        # Tab 2 — Manual
        manual_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=6,
            margin_end=6,
        )
        fields_group = Adw.PreferencesGroup()
        self._uri_row = Adw.EntryRow(title="Repository URI")
        self._uri_row.set_input_purpose(Gtk.InputPurpose.URL)
        self._uri_row.connect("changed", self._on_manual_changed)
        fields_group.add(self._uri_row)
        self._suite_row = Adw.EntryRow(title="Suite / Codename")
        fields_group.add(self._suite_row)
        self._components_row = Adw.EntryRow(title="Components")
        self._components_row.set_text("main")
        fields_group.add(self._components_row)
        self._desc_row = Adw.EntryRow(title="Name / Description (optional)")
        fields_group.add(self._desc_row)
        self._key_url_row = Adw.EntryRow(title="GPG key URL (optional)")
        self._key_url_row.set_input_purpose(Gtk.InputPurpose.URL)
        self._key_url_row.connect("changed", self._on_key_url_changed)
        fields_group.add(self._key_url_row)
        self._signed_by_row = Adw.EntryRow(title="Signing key path (auto-filled from key URL)")
        fields_group.add(self._signed_by_row)
        self._deb_src_row = Adw.SwitchRow(title="Also include source packages (deb-src)")
        fields_group.add(self._deb_src_row)
        self._enabled_row = Adw.SwitchRow(title="Enabled")
        self._enabled_row.set_active(True)
        fields_group.add(self._enabled_row)
        manual_box.append(fields_group)
        self._manual_error_lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=55)
        self._manual_error_lbl.add_css_class("warning")
        self._manual_error_lbl.set_visible(False)
        manual_box.append(self._manual_error_lbl)
        self._notebook.append_page(manual_box, Gtk.Label(label="Manual"))

        outer.append(self._notebook)

        btn_box = Gtk.Box(
            spacing=6,
            halign=Gtk.Align.END,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        self._add_btn = Gtk.Button(label="Add Repository")
        self._add_btn.add_css_class("suggested-action")
        self._add_btn.set_sensitive(False)
        self._add_btn.connect("clicked", self._on_add_clicked)
        btn_box.append(cancel_btn)
        btn_box.append(self._add_btn)
        outer.append(Gtk.Separator())
        outer.append(btn_box)

        self.set_child(outer)
        self._notebook.connect("switch-page", self._on_tab_switched)
        self._update_ppa_sensitivity()

    # ------------------------------------------------------------------
    # Sensitivity
    # ------------------------------------------------------------------

    def _on_tab_switched(self, _nb, _page, page_num: int) -> None:
        if page_num == 0:
            self._update_ppa_sensitivity()
        elif page_num == 1:
            self._on_auto_changed(self._auto_text.get_buffer())
        else:
            self._update_manual_sensitivity()

    def _on_auto_changed(self, buf) -> None:
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if self._notebook.get_current_page() == 1:
            self._add_btn.set_sensitive(bool(text))

    def _on_manual_changed(self, _row) -> None:
        self._update_manual_sensitivity()

    def _update_manual_sensitivity(self) -> None:
        self._add_btn.set_sensitive(bool(self._uri_row.get_text().strip()))

    def _on_ppa_changed(self, _row) -> None:
        self._update_ppa_sensitivity()

    def _update_ppa_sensitivity(self) -> None:
        self._add_btn.set_sensitive(bool(self._ppa_row.get_text().strip()))

    def _on_key_url_changed(self, _row) -> None:
        url = self._key_url_row.get_text().strip()
        if url:
            host = urlparse(url).netloc or url
            sanitized = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
            self._signed_by_row.set_text(f"{_KEYRINGS_DIR}/{sanitized}.gpg")
            self._signed_by_row.set_sensitive(False)
        else:
            self._signed_by_row.set_text("")
            self._signed_by_row.set_sensitive(True)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _on_add_clicked(self, _btn: Gtk.Button) -> None:
        self._add_btn.set_sensitive(False)
        self._add_btn.set_label("Adding…")
        self._auto_error_lbl.set_visible(False)
        self._manual_error_lbl.set_visible(False)
        self._ppa_error_lbl.set_visible(False)
        threading.Thread(target=self._do_add, daemon=True).start()

    def _do_add(self) -> None:
        page = self._notebook.get_current_page()
        if page == 0:
            self._do_add_ppa()
        elif page == 1:
            self._do_add_auto()
        else:
            self._do_add_manual()

    # --- Auto tab ---

    def _do_add_auto(self) -> None:
        buf = self._auto_text.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()

        # Catch direct package download URLs early with a helpful message
        if text.startswith(("http://", "https://")) and " " not in text:
            if urlparse(text).path.lower().endswith((".deb", ".rpm", ".apk")):
                GLib.idle_add(
                    self._fail_auto,
                    "This looks like a direct package download link, not a repository source."
                    " Download the file and install it with your package manager instead.",
                )
                return

        fields = _parse_source_block(text)
        if not fields:
            GLib.idle_add(self._fail_auto, "Could not parse the pasted text. Please check the format.")
            return

        key_url = self._auto_key_row.get_text().strip()
        self._submit_fields(fields, key_url)

    # --- Manual tab ---

    def _do_add_manual(self) -> None:
        uri = self._uri_row.get_text().strip()
        if not uri:
            GLib.idle_add(self._fail_manual, "Repository URI is required.")
            return

        types = ["deb"]
        if self._deb_src_row.get_active():
            types.append("deb-src")

        fields = {
            "types": types,
            "uris": [uri],
            "suites": self._suite_row.get_text().split(),
            "components": self._components_row.get_text().split(),
            "enabled": self._enabled_row.get_active(),
            "signed_by": self._signed_by_row.get_text().strip() or None,
            "description": self._desc_row.get_text().strip() or None,
        }
        key_url = self._key_url_row.get_text().strip()
        self._submit_fields(fields, key_url)

    # --- PPA tab ---

    def _do_add_ppa(self) -> None:
        text = self._ppa_row.get_text().strip()
        if text.startswith("ppa:"):
            text = text[4:]
        parts = text.split("/", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            GLib.idle_add(self._fail_ppa, "Enter a PPA address in the format ppa:owner/name")
            return
        owner, name = parts[0].strip(), parts[1].strip()
        codename = get_current_codename()
        uri = f"https://ppa.launchpadcontent.net/{owner}/{name}/ubuntu"
        fields = {
            "types": ["deb"],
            "uris": [uri],
            "suites": [codename],
            "components": ["main"],
            "enabled": True,
            "signed_by": None,
            "description": f"PPA: {owner}/{name}",
        }
        self._submit_fields(fields, "")

    # --- Shared submission logic ---

    def _submit_fields(self, fields: dict, key_url: str) -> None:
        """Build and write the new repo. Runs in a background thread."""
        uri = fields["uris"][0] if fields["uris"] else ""
        source_path = _unique_source_path(_uri_to_source_filename(uri))

        repo = Repository(
            source_file=source_path,
            file_format=FileFormat.DEB822,
            types=fields.get("types") or ["deb"],
            uris=fields.get("uris") or [],
            suites=fields.get("suites") or [],
            components=fields.get("components") or [],
            enabled=fields.get("enabled", True),
            description=fields.get("description"),
            signed_by=fields.get("signed_by"),
        )

        writes = []
        key_error: str | None = None

        # GPG key handling
        if key_url:
            key_bytes, err = gpg.fetch_key(key_url)
            if err or not key_bytes:
                key_error = err or "Empty response from key URL"
            else:
                key_filename = _uri_to_key_filename(key_url)
                key_path = str(_KEYRINGS_DIR / key_filename)
                repo.signed_by = key_path
                writes.append(
                    {
                        "path": key_path,
                        "content": gpg.key_to_b64(key_bytes),
                        "encoding": "base64",
                    }
                )
        elif not repo.signed_by and repo.is_ppa and repo.ppa_owner and repo.ppa_name:
            key_bytes, err = gpg.fetch_ppa_key(repo.ppa_owner, repo.ppa_name)
            if key_bytes and not err:
                key_filename = f"{repo.ppa_owner}-{repo.ppa_name}.gpg"
                key_path = str(_KEYRINGS_DIR / key_filename)
                repo.signed_by = key_path
                writes.append(
                    {
                        "path": key_path,
                        "content": gpg.key_to_b64(key_bytes),
                        "encoding": "base64",
                    }
                )

        # .sources file write
        writes.append({"path": str(source_path), "content": repo_to_deb822(repo)})

        payload = json.dumps({"action": "write_files", "writes": writes, "deletes": []})
        result = subprocess.run([PKEXEC, POLKIT_HELPER], input=payload, capture_output=True, text=True)

        if result.returncode == 0:
            GLib.idle_add(self._on_add_success, repo, key_error)
        else:
            page = self._notebook.get_current_page()
            fail_fn = self._fail_ppa if page == 0 else (self._fail_auto if page == 1 else self._fail_manual)
            GLib.idle_add(fail_fn, result.stderr.strip())

    def _on_add_success(self, repo: Repository, key_warning: str | None) -> bool:
        if key_warning:
            # Warn but still close — repo was added, just without the key
            page = self._notebook.get_current_page()
            lbl = self._ppa_error_lbl if page == 0 else (self._auto_error_lbl if page == 1 else self._manual_error_lbl)
            lbl.set_label(f"Key fetch failed: {key_warning}. Repository added without signing.")
            lbl.set_visible(True)
            self._add_btn.set_sensitive(True)
            self._add_btn.set_label("Add Repository")
        self.emit("repo-added", repo)
        if not key_warning:
            self.close()
        return GLib.SOURCE_REMOVE

    def _fail_auto(self, message: str) -> bool:
        self._auto_error_lbl.set_label(message)
        self._auto_error_lbl.set_visible(True)
        self._add_btn.set_sensitive(True)
        self._add_btn.set_label("Add Repository")
        return GLib.SOURCE_REMOVE

    def _fail_manual(self, message: str) -> bool:
        self._manual_error_lbl.set_label(message)
        self._manual_error_lbl.set_visible(True)
        self._add_btn.set_sensitive(True)
        self._add_btn.set_label("Add Repository")
        return GLib.SOURCE_REMOVE

    def _fail_ppa(self, message: str) -> bool:
        self._ppa_error_lbl.set_label(message)
        self._ppa_error_lbl.set_visible(True)
        self._add_btn.set_sensitive(True)
        self._add_btn.set_label("Add Repository")
        return GLib.SOURCE_REMOVE
