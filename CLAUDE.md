# repoman — Claude working guide

GTK4 + libadwaita APT repository manager for Ubuntu/Xubuntu.
"Repo Man" — as in repossessing your repos after an upgrade. Also the 1984 film.

---

## Decision discipline — MANDATORY

When presenting the user with a choice between options, **STOP and wait for their answer.**
Never pick an option on their behalf. Never assume silence or a topic change is consent.
If the user moves on without choosing, ask again before acting.
This applies to every decision, no matter how minor it seems.

---

## Code review passes — MANDATORY

When asked to review, check, or do "another pass" on any code:

1. **Trace every exit path** in every method — not just the happy path.
   For each early return: does it complete all the same side effects
   (callbacks, signals, state cleanup) that the full path does?

2. **Compare parallel paths** — if there is a success path and a
   failure/shortcut path, list what each one does and diff them.
   Anything the success path does that a shortcut skips is a bug candidate.

3. **Wizard `_on_proceed` checklist** — every exit must account for:
   - `state.on_complete(...)` called if it exists
   - Signals emitted (repos-updated, closing)
   - In-progress state cleaned up

Saying "looks good" without tracing every branch is not a pass.

---

**App ID:** `net.tecktron.repoman`
**Platform minimum:** Xubuntu 24.04 LTS (libadwaita 1.5.0)
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

## One-time dev setup

Symlink the dev helper to the installed path so polkit can match the action and
honour `auth_admin_keep` (~5-minute auth caching between operations):

```bash
sudo mkdir -p /usr/lib/repoman
sudo ln -sf /home/craig/Projects/repoman/polkit-helper /usr/lib/repoman/polkit-helper
```

## Running the app

```bash
cd /home/craig/Projects/repoman
# Kill ALL repoman instances (installed binary + dev launch) before starting
pkill -f "repoman" 2>/dev/null; sleep 0.5

# Dev source MUST come before system dist-packages — otherwise the installed
# .deb version wins and changes to src/ have no effect.
PYTHONPATH=/home/craig/Projects/repoman/src:/usr/lib/python3/dist-packages \
DISPLAY=:0 \
python3 -m repoman.main
```

## Tests

```bash
cd /home/craig/Projects/repoman
python3 -m pytest tests/ -q          # 221 tests, all must pass
ruff check src/                       # linter
ruff format --check src/              # formatter
```

---

## Complete file structure

```
src/repoman/
  main.py            — RepomanApplication (Adw.Application);
                       startup tool check via check_required_tools()
  models.py          — Repository dataclass, WizardState dataclass,
                       RestoreWizardState dataclass, FileFormat enum, AvailabilityStatus enum
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
                       software-properties-gtk; POLKIT_HELPER hardcoded to
                       /usr/lib/repoman/polkit-helper; check_required_tools()
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
    popover.py       — make_info_button(): flat circular Gtk.MenuButton with status icon
                       and info popover (headline, suite, target, Launchpad link for PPAs);
                       _clear_label_selections(): shared by all wizard pages and compat_checker
    select_page.py   — Step 1: checkbox list, pre-ticks non-UNAVAILABLE repos;
                       "Select all / Deselect all" button in group header suffix;
                       UNKNOWN status shows dimmed question mark (not spinner —
                       no checks run on Step 1); all icons are make_info_button() MenuButtons
    check_page.py    — Step 2: background Checker thread; spinner → make_info_button() per row;
                       Next locked until all pending == 0; _checks_started flag
                       guards _on_shown() so back-navigation never re-runs checks
                       or duplicates icons; icons have tooltip + popover
    confirm_page.py  — Step 3: "Will be re-enabled" / "Skipped" groups (each hidden
                       when empty); auth row hidden when nothing to apply; "Apply
                       changes" relabelled "Done" and closes wizard when _to_apply
                       is empty; icons are make_info_button() with tooltip + popover;
                       pkexec via subprocess.run(); toast on failure; on_complete on success
    restore_dialog.py       — RestoreWizardDialog; wraps 3-page restore flow;
                              accepts saved/actions/codenames/live_repos/on_complete;
                              same repos-updated + closing signals as RepomanWizardDialog
    restore_classify_page.py — Step 1: "Existing repos" vs "Repos to add" overview.
                               Pre-resolve: matched repos whose live suite is already
                               current (or agnostic) → "restore_as_is" (sync enabled
                               only); stale-suite matched repos keep classified action.
                               Existing sub-groups: state-change, suite-updating,
                               checking PPA availability, no-changes. Adding sub-groups:
                               checking Launchpad, will be created, add-disabled, as-is.
                               Skips page 2 if no ppa_check entries remain.
    restore_check_page.py   — Step 2: per-PPA spinner -> make_info_button() availability
                              check via check_ppa_for_codename(); _checks_started guard;
                              _matched_ids distinguishes existing vs new PPAs — UNAVAILABLE
                              matched → restore_as_is (keep suite, sync enabled);
                              UNAVAILABLE missing → add_disabled; _pending counter
    restore_confirm_page.py — Step 3: grouped summary. Matched: "Updating to {cc}"
                              (per-row enabled/disabled icon), "Enabling", "Disabling",
                              "No changes". Missing: "Not found - will be added
                              enabled/disabled". Auth card; polkit write_files apply;
                              rollback on failure; all icons make_info_button()

polkit-helper        — Privileged write helper (run via pkexec).
                       Actions: enable_repos (patch Suites/Enabled in existing .sources),
                       write_files (write content + optional deletes for .list conversion).
                       Validates all paths against _ALLOWED before any write.
                       Writes atomically: .tmp → rename.
data/
  net.tecktron.repoman.policy  — polkit policy; auth_admin_keep
  suite-agnostic.conf        — dev fallback agnostic suite names
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

### `RestoreWizardState`
Threaded through all restore wizard pages: `saved` (raw dicts from load_config),
`actions` (parallel list, mutated by page 2 for ppa_check entries),
`saved_codename`, `current_codename`, `live_repos` (snapshot at wizard-open time),
`on_complete(missing)` callback (called with pre-adapted missing entries after apply).

---

## Parser behaviour — important details

- **Official Ubuntu URIs filtered out**: `archive.ubuntu.com`, `security.ubuntu.com`,
  `ports.ubuntu.com`, `esm.ubuntu.com` — never shown in repoman.
- **Suite-agnostic detection**: suites in `data/suite-agnostic.conf`
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

The helper path is hardcoded to `/usr/lib/repoman/polkit-helper`. For dev, symlink
the repo's `polkit-helper` there (see One-time dev setup above).

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

`Adw.Dialog` is NOT used — `Gtk.Window` gives consistent Xfwm4 system titlebars and the approach is already established across all windows.

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

**Repos → Save state… / Load state…** (no submenu — flat items in the Repos menu).

Save calls `config_io.save_config(repos, current_codename)` → JSON string written
directly to wherever the user picks via `Gtk.FileDialog` (no polkit). Default filename:
`state-{date}.repoman`. GPG key file bytes are read and embedded as base64
(`signed_by_content_b64`) when the key path is readable.

### Load — same-machine fast path

Triggered when `saved_codename` is absent (v1 file) or matches `get_current_codename()`.
Matches saved entries to live repos by `uris[0]`. Three outcomes per entry:
- URI found, enabled state differs → write via polkit `write_files`
- URI found, state same → no-op
- URI not found → "missing" list (see below)

### Load — cross-machine restore

Triggered when `saved_codename` is set and differs from `get_current_codename()`.
Steps:
1. `classify_restore_entry()` in `config_io.py` assigns each entry one of:
   `restore_as_is` / `update_suite` / `add_disabled` / `ppa_check`
2. PPA entries get a HEAD check via `check_ppa_for_codename()` (background thread;
   toast shown during check). Result resolves to `update_suite` or `add_disabled`.
3. Summary `Gtk.Window` shows categorised changes; user clicks Cancel or Apply.
4. Apply: matched repos' suites/enabled mutated and written via one polkit `write_files`.
   On failure, in-memory state rolls back (`enabled` + `suites`).
5. Missing entries pre-adapted (suite / enabled) then passed to the missing repos dialog.

### Missing repos dialog (`Gtk.Window`, not `Adw.AlertDialog`)

Three choices: Skip / Add N enabled / Add all N. Creates repos via polkit `write_files`.
Key files with `signed_by_content_b64` are written in the same polkit call (no manual
key install needed). Warning only shown for repos whose key is not bundled.

Repos on the system but absent from the file are left untouched.

**File format (version 2):**
```json
{
  "version": 2,
  "saved_at": "2026-07-08T14:22:00",
  "saved_codename": "noble",
  "repos": [
    {"types": ["deb"], "uris": ["https://..."], "suites": ["noble"],
     "components": ["main"], "enabled": true,
     "description": "...", "signed_by": "/usr/share/keyrings/example.gpg",
     "signed_by_content_b64": "<base64>",
     "source_file": "/etc/apt/sources.list.d/example.sources"}
  ]
}
```

Version 1 files (no `saved_codename`, no `signed_by_content_b64`) still load via the
fast path with reduced capability.

`config_io.py` is pure (no GTK) with 48 unit tests in `tests/test_config_io.py`.

---

## Known issues / deferred work

- **Window positioning flicker**: move fires post-map (window appears at WM default,
  then jumps). Fix: pre-realize positioning with `get_default_size()`. Deferred.
- **`.list` → `.sources` conversion**: converter.py is written; detail_pane.py
  save path triggers it correctly. Not yet exercised in a real-world test.
- **Distribution**: PPA at `ppa:tecktron-studios/repoman` published; noble, questing, resolute.

---

## Build / packaging

Runtime deps (system packages, not pip): `python3-gi`, `gir1.2-gtk-4.0`,
`gir1.2-adw-1` (≥1.5), `gir1.2-packagekitglib-1.0`, `python3-debian`,
`python3-launchpadlib`, `python3-requests`, `python3-xlib`, `policykit-1`,
`lsb-release`.

polkit policy must be installed to `/usr/share/polkit-1/actions/` and polkit
restarted (`systemctl restart polkit`) before the wizard's Apply step works.
The helper must be executable: `chmod +x polkit-helper`.

`debian/` contains control, rules (dh + pybuild), install, postinst
(compiles GSettings schemas, updates icon cache, sets helper +x), changelog.

Build deps (beyond what `debhelper-compat` pulls in): `dh-python`,
`pybuild-plugin-pyproject`, `python3-all`, `python3-setuptools`.
Install with `sudo apt install debhelper dh-python pybuild-plugin-pyproject python3-all python3-setuptools` before building.

Build: `dpkg-buildpackage -us -uc` (run from the repo root; output lands in `../`).
Install: `sudo dpkg -i ../repoman_*.deb`.
