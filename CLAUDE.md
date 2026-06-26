# repoman — Claude working guide

GTK4 + libadwaita APT repository manager for Ubuntu/Xubuntu.
"Repo Man" — as in repossessing your repos after an upgrade. Also the 1984 film.

**App ID:** `io.github.Tecktron.repoman`
**Platform minimum:** Xubuntu 24.04 LTS (libadwaita 1.4.2)
**Target environment:** Xfce/Xfwm4 (system-decorated windows, SSD, no CSD)
**Singleton:** `Gio.Application` — a second `python3 -m repoman.main` launch
opens a new window in the existing process, not a new process.

---

## Writing code — holistic file awareness

Before finalising any change, take a pass over the **whole file**, not just
the lines you touched. Catch these before they land:

**Imports** — module-level by default. Before putting `from X import Y`
inside a function body, check: is this symbol used (or likely to be used)
anywhere else in the file? If yes, it belongs at the top. Inline imports
are only justified to break circular dependencies, and that reason must be
obvious from context.

**DRY** — before writing a new helper, scan the file for something that
already does it. A function that only delegates to one other function
(`def foo(): return bar()`) is noise — collapse it.

**Type hints** — be precise every time. `list` → `list[Repository]`.
`T` → `T | None` when `None` is a valid argument or return value. When a
parameter can be `None`, grep all call sites and make sure the hint matches
reality before committing.

**Broad exception handlers** — `except Exception` must always be paired
with `_log.debug(…, exc_info=True)` on the very next line. No silent
broad catches, ever.

**Dead code** — if a code path has no callers, remove it. Dead code in
security-sensitive helpers (polkit, setuid) is a liability, not a
harmless placeholder.

**Callers** — when changing a function signature, grep every call site
and update them in the same diff. A type hint that contradicts how the
function is actually called is worse than no hint.

---

## Running the app

```bash
cd /home/craig/Projects/repoman
# Kill any existing instance first — second launch silently opens in existing process
pkill -f "python3 -m repoman.main" 2>/dev/null; sleep 0.3

PYTHONPATH=/usr/lib/python3/dist-packages \
DISPLAY=:0 \
REPOMAN_HELPER_PATH=/home/craig/Projects/repoman/polkit-helper \
python3 -m repoman.main
```

## Tests

```bash
cd /home/craig/Projects/repoman
python3 -m pytest tests/ -q          # 134 tests, all must pass
ruff check src/                       # linter
ruff format --check src/              # formatter
```

---

## Complete file structure

```
src/repoman/
  main.py            — RepomanApplication (Adw.Application); --sources-dir flag;
                       startup tool check via check_required_tools()
  models.py          — Repository dataclass, WizardState dataclass,
                       FileFormat enum, AvailabilityStatus enum
  parser.py          — Parser class: scans sources.list.d/, handles DEB822 (.sources)
                       and one-line (.list); filters official Ubuntu URIs; detects
                       suite-agnostic repos; reads X-Repolib-Name and leading # comments
  writer.py          — repo_to_deb822(): pure serialiser, no I/O; enable_patch()
  converter.py       — convert_to_deb822(): ONE_LINE → DEB822, returns (new_path, content)
  checker.py         — Checker class: launchpadlib for PPAs, requests.head for others;
                       global _network_failed flag to suppress cascading errors
  upgrade_info.py    — OS release detection; Ubuntu CSV distro info;
                       get_upgrade_targets(); get_ppa_suites() (dists/ GET);
                       check_ppa_for_codename() (InRelease HEAD)
  utils.py           — get_current_codename() via lsb_release; repos_needing_attention()
  paths.py           — shutil.which() for pkexec, lsb_release, update-manager,
                       software-properties-gtk; REPOMAN_HELPER_PATH env override;
                       check_required_tools()
  config_io.py       — Save/load .repoman state files (pure, no GTK, fully tested):
                       save_config() → JSON str; load_config() → list[dict];
                       match_repos() → (matched, missing) by uris[0];
                       entry_to_repository() reconstructs a Repository from a saved entry

  ui/
    main_window.py   — RepomanWindow (Gtk.Window); sidebar list + detail pane;
                       Adw.Banner for upgrade alert; search; disable-all; menu bar;
                       wizard launch; compat checker launch; about/shortcuts windows;
                       Tools → State Management → Save… / Load… (.repoman files)
    repo_row.py      — RepoRow (Adw.ActionRow); enable/disable switch prefix;
                       availability badge suffix; repo-toggled signal
    detail_pane.py   — DetailPane (Gtk.Box); edit description/suite/components/enabled;
                       copy-URI button; open-in-browser button; save via polkit
    compat_checker.py — CompatCheckerWindow (Gtk.Window); combo selects target release;
                        PPA availability via get_ppa_suites(); status buttons;
                        enrichment popover for UNAVAILABLE PPAs (latest/last available)
    position.py      — center_on_screen(), center_on_parent() via python-xlib;
                       post-map positioning (known flicker — deferred fix)

  ui/wizard/
    dialog.py        — RepomanWizardDialog (Gtk.Window); AdwNavigationView;
                       repos-updated and closing signals; _schedule_close() pattern
    base_page.py     — RepomanWizardPage (Adw.NavigationPage); _content_box, _next_button,
                       can_proceed(), _on_proceed(), refresh_proceed()
    select_page.py   — Step 1: checkbox list, pre-ticks non-UNAVAILABLE repos;
                       "Select all / Deselect all" button in group header suffix;
                       UNKNOWN status shows dimmed question mark (not spinner —
                       no checks run on Step 1)
    check_page.py    — Step 2: background Checker thread; spinner → icon per row;
                       Next locked until all pending == 0; _checks_started flag
                       guards _on_shown() so back-navigation never re-runs checks
                       or duplicates icons; icons have set_tooltip_text()
    confirm_page.py  — Step 3: "Will be re-enabled" / "Skipped" groups (each hidden
                       when empty); auth row hidden when nothing to apply; "Apply
                       changes" relabelled "Done" and closes wizard when _to_apply
                       is empty; icons have set_tooltip_text(); pkexec via
                       subprocess.run(); toast on failure; on_complete on success

polkit-helper        — Privileged write helper (run via pkexec).
                       Actions: enable_repos (patch Suites/Enabled in existing .sources),
                       write_files (write content + optional deletes for .list conversion).
                       Validates all paths against _ALLOWED before any write.
                       Writes atomically: .tmp → rename.
data/
  io.github.Tecktron.repoman.policy  — polkit policy; auth_admin_keep
  repoman-suite-agnostic.conf        — dev fallback agnostic suite names
```

---

## Data models

### `Repository` (dataclass)
Fields set from file: `source_file`, `file_format`, `types`, `uris`, `suites`,
`components`, `enabled`, `description`, `signed_by`.
Derived in `__post_init__`: `is_ppa`, `ppa_owner`, `ppa_name`.
Mutable runtime state: `availability` (default `UNKNOWN`).
`display_name` property: description if set, else first URI.

### `AvailabilityStatus`
- `UNKNOWN` — not yet checked (default); shown as dimmed question mark on Step 1
- `CHECKING` — reserved for in-progress state; spinner shown in wizard Step 2
  while background thread runs (status transitions directly to AVAILABLE/UNAVAILABLE
  when the check completes — CHECKING is never written back to the repo object)
- `AVAILABLE` — confirmed for target release
- `UNAVAILABLE` — confirmed not available
- `SUITE_AGNOSTIC` — fixed suite name (stable, main, etc.) — never needs updating

### `WizardState`
Threaded through all wizard pages: `candidate_repos`, `target_codename`,
`selected` (populated in step 1), `on_complete` callback (fires after polkit write).

---

## Parser behaviour — important details

- **Official Ubuntu URIs filtered out**: `archive.ubuntu.com`, `security.ubuntu.com`,
  `ports.ubuntu.com`, `esm.ubuntu.com` — never shown in repoman.
- **Suite-agnostic detection**: suites in `data/repoman-suite-agnostic.conf`
  (falls back to built-ins: stable, main, testing, sid, etc.) OR any suite with
  non-alpha characters (focal-security, noble/updates). Sets `SUITE_AGNOSTIC`.
- **Description sources** (DEB822, in priority order):
  1. `X-Repolib-Name:` field (software-properties-gtk convention)
  2. `Description:` field
  3. Leading `#comment` line immediately before the stanza (repolib convention)
- **ONE_LINE format**: commented-out `# deb ...` lines are parsed as disabled repos.
- **`repos_needing_attention()`** catches two cases:
  1. `Enabled: no`
  2. Enabled repo with a suite that `.isalpha() and .islower()` and != current codename
     (catches stale codenames that silently 404 on `apt update`)

---

## Polkit helper interface

The helper reads JSON from stdin and exits 0 on success, 1 on error.

**`enable_repos`** — used by the upgrade wizard:
```json
{
  "action": "enable_repos",
  "target_codename": "resolute",
  "repos": [
    {"source_file": "/etc/apt/sources.list.d/example.sources",
     "suites": ["resolute"], "enabled": true}
  ]
}
```

**`write_files`** — used by detail pane save, disable-all, and state load:
```json
{
  "action": "write_files",
  "writes": [{"path": "/etc/apt/sources.list.d/example.sources", "content": "..."}],
  "deletes": ["/etc/apt/sources.list.d/example.list"]
}
```
Deletes happen after all writes succeed. Used for `.list` → `.sources` conversion
(write new `.sources`, delete old `.list` in one polkit prompt). Also used by
the state load feature to apply enabled/disabled changes and create missing repos.

The helper is located via `REPOMAN_HELPER_PATH` env var (dev) or
`/usr/lib/repoman/polkit-helper` (installed). Set the env var when running from source.

---

## Threading rules

- All background work (network, disk, pkexec) runs in `threading.Thread(daemon=True)`.
- Results return to the GTK main thread exclusively via `GLib.idle_add(callback, *args)`.
- Callbacks from `idle_add` must return `GLib.SOURCE_REMOVE`.
- Never touch GTK widgets from a background thread — causes silent corruption or crashes.

---

## Window management

All windows (`RepomanWindow`, `RepomanWizardDialog`, `CompatCheckerWindow`,
shortcuts window, about window) are **`Gtk.Window`**, not `Adw.ApplicationWindow`.
This gives consistent Xfwm4 system titlebars. libadwaita widgets inside still work.

`Adw.Dialog` is NOT used — it requires libadwaita 1.5; minimum is 1.4.2 (24.04).

**Centering** (`src/repoman/ui/position.py`): post-map via python-xlib
(`configure(x=y)` + `display.sync()`). Known issue: slight flicker because the WM
places the window before the move fires. Pre-realize positioning is the correct fix
but is deferred. `center_on_screen()` for the main window; `center_on_parent()` for
all secondary windows.

**Wizard close**: `RepomanWizardDialog.do_close_request()` returns `True` (suppress
default), calls `_schedule_close()` which emits `closing`, hides the window, then
`GLib.idle_add(self.destroy)`. `main_window.py` clears `self._wizard = None` on
`closing` signal so re-opening works cleanly.

---

## GTK4 widget selection — check this BEFORE implementing

Picking the wrong widget is the most common source of subtle bugs. Ask
"what behaviour do I need?" first, then pick the widget that provides it.

### Button that opens a popover
**Use `Gtk.MenuButton`, not `Gtk.Button`.**

`Gtk.MenuButton` owns the popover lifecycle: manages button active/pressed CSS
state, closes on Escape or outside-click, keeps icon in sync.
`Gtk.Button` does none of this — wiring it up manually reproduces a broken
subset of what `MenuButton` already does. The button gets stuck in a pressed
visual state after keyboard-close, icons stop updating, popover state corrupts.

```python
btn = Gtk.MenuButton(valign=Gtk.Align.CENTER)
btn.set_child(icon)              # custom icon child with any CSS classes
btn.add_css_class("flat")
btn.add_css_class("circular")
popover = Gtk.Popover(child=content)
btn.set_popover(popover)         # MenuButton owns open/close from here
```

Do NOT: `popover.set_parent(btn)` + `btn.connect("clicked", popover.popup)`.

### Button that performs an action on click
`Gtk.Button` — copy-to-clipboard, open-URL, save, close, advance wizard.
No popover. `Gtk.Button` is correct here.

### App menu bar
`Gtk.PopoverMenuBar.new_from_model(menu_model)`.

### Libadwaita preference rows
Prefer `Adw.ActionRow`, `Adw.EntryRow`, `Adw.SwitchRow`, `Adw.ComboRow`
over raw `Gtk.ListBoxRow`. Add suffix/prefix widgets with `row.add_suffix()` /
`row.add_prefix()`.

### Selectable text in a popover
`Gtk.Label(selectable=True)` — GTK provides right-click copy context menu free.
Do NOT add `Gtk.EventControllerKey` to the popover for Ctrl+C — this breaks
the popover's close mechanism (Escape stops working).

GTK4 auto-selects all text in a focused selectable label when a popover opens.
Clear it on the `show` signal:
```python
def _clear_label_selections(popover):
    def _do_clear():
        stack = [popover.get_child()]
        while stack:
            w = stack.pop()
            if isinstance(w, Gtk.Label) and w.get_selectable():
                w.select_region(0, 0)
            child = w.get_first_child() if hasattr(w, "get_first_child") else None
            while child:
                stack.append(child)
                child = child.get_next_sibling()
        return GLib.SOURCE_REMOVE
    GLib.idle_add(_do_clear)

popover.connect("show", _clear_label_selections)
```

---

## Exception handling

- Network calls: narrow `except` to specific types (`Timeout`, `ConnectionError`,
  `RequestException`); return `(None, error_str)` to the caller.
- File/parse: `except (OSError, csv.Error)`, `except configparser.Error`.
- Best-effort X11/positioning code: `except Exception:` is acceptable **only** with
  `_log.debug(..., exc_info=True)` — never `pass`.
- Never suppress exceptions silently. No `# noqa: S110`.

---

## PPA availability — two functions, two use cases

Both live in `upgrade_info.py`:

- **`get_ppa_suites(owner, ppa)`** — used in `compat_checker.py`. One GET to
  `https://ppa.launchpadcontent.net/{owner}/{ppa}/ubuntu/dists/`, parses Apache
  directory listing with `re.findall(r'href="([^/"]+)/"', ...)`.
  Returns `(frozenset[str], None)` on success, `(None, error_str)` on failure,
  `(frozenset(), None)` on 404. Gives all supported suites in one request.

- **`check_ppa_for_codename(owner, ppa, codename)`** — HEAD to the specific
  InRelease URL. Returns `(AvailabilityStatus, error_str | None)`. Used by
  `checker.py` in the wizard's check_page.

The `compat_checker.py` uses `get_ppa_suites()` instead of the wizard's `Checker`
class so it can enrich the UNAVAILABLE popover with "latest/last available" info
derived from the full suite set.

---

## Compat checker — popover enrichment

When a PPA is UNAVAILABLE for the target codename, the popover shows which Ubuntu
release it was last (or most recently) published for:

- Intersect `suites` frozenset with `_ordered_codenames` (all Ubuntu series in
  release-date order from `get_all_known_codenames()`).
- Compare `latest_idx` vs `current_idx`:
  - `latest_idx > current_idx` → "Latest available: {latest}" (PPA maintained but
    hasn't published for target yet)
  - `latest_idx <= current_idx` → "Last available: {latest}" (PPA may be abandoned)
  - Empty intersection → "No packages found for any Ubuntu release"

---

## Save / Load state (`.repoman` files)

**Tools → State Management → Save… / Load…**

Save serialises `self._repos` to a JSON `.repoman` file (no polkit — written directly
to wherever the user chooses via `Gtk.FileDialog`). Default filename: `state-{date}.repoman`.

Load matches saved entries to live repos **by `uris[0]`** (stable across upgrades).
Three outcomes per entry:
- URI found, state differs → write via polkit `write_files`
- URI found, state same → no-op
- URI not found → "missing" list

After polkit write succeeds, any missing repos are presented in an `Adw.AlertDialog`
with three choices: Skip / Add N enabled / Add all N. "Create" fires another polkit
`write_files` call. GPG/Signed-By warning shown in the dialog if any missing repo has
a `signed_by` field.

Polkit failure rolls back in-memory `enabled` state before refreshing rows.
Repos on the system but absent from the file are left untouched.

**File format (version 1):**
```json
{
  "version": 1,
  "saved_at": "2026-06-23T22:00:00",
  "repos": [
    {"types": ["deb"], "uris": ["https://..."], "suites": ["noble"],
     "components": ["main"], "enabled": true,
     "description": "...", "signed_by": "/path/to.gpg",
     "source_file": "/etc/apt/sources.list.d/example.sources"}
  ]
}
```

`config_io.py` is pure (no GTK) with 24 unit tests in `tests/test_config_io.py`.

---

## Known issues / deferred work

- **Window positioning flicker**: move fires post-map (window appears at WM default,
  then jumps). Fix: pre-realize positioning with `get_default_size()`. Deferred.
- **`.list` → `.sources` conversion**: converter.py is written; detail_pane.py
  save path triggers it correctly. Not yet exercised in a real-world test.
- **Wizard dry-run test**: the full wizard flow (banner → select → check →
  confirm → polkit write → reload) hasn't been exercised end-to-end with test
  `.sources` files. See `test-plan.md` for the full test procedure.
- **Icon**: no app icon SVG yet (`io.github.Tecktron.repoman`).
- **Packaging**: `debian/` skeleton exists; `.deb` has not been built or tested.
- **Distribution**: PPA at `ppa:tecktron-studios/repoman` not yet created.

---

## Build / packaging

Runtime deps (system packages, not pip): `python3-gi`, `gir1.2-gtk-4.0`,
`gir1.2-adw-1` (≥1.4), `python3-apt`, `python3-debian`, `python3-launchpadlib`,
`python3-requests`, `policykit-1`.

polkit policy must be installed to `/usr/share/polkit-1/actions/` and polkit
restarted (`systemctl restart polkit`) before the wizard's Apply step works.
The helper must be executable: `chmod +x polkit-helper`.

`debian/` contains control, rules (dh + pybuild), install, postinst
(compiles GSettings schemas, updates icon cache, sets helper +x), changelog.
Build: `dpkg-buildpackage -us -uc`. Install: `dpkg -i repoman_*.deb`.
