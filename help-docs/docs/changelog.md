# Changelog

All notable changes to repoman will be documented here. repoman uses [Semantic Versioning](https://semver.org/).

## 1.0.1 — 2026-07-15

### Fixed

- Sphinx API docs build failure: `repoman.ui.position` reference removed from `sphinx/api/ui.rst` after the module was deleted in 1.0.0.
- `gi.repository.GdkX11` and `Xlib` removed from `sphinx/conf.py` autodoc mock imports (dependencies removed in 1.0.0).

---

## 1.0.0 — 2026-07-15

### Changed

- **UI label and naming consistency**: "Upgrade Assistant" is now named consistently
  across the menu, window title, and keyboard shortcuts window. "pre-upgrade" is used
  consistently throughout (was "pre-update" in the menu and one help-docs reference).
- **CompatChecker button order corrected**: Close is now on the left, Check compatibility
  on the right — consistent with every other dialog in the app.
- **Missing repos dialog**: "Skip" renamed to "Cancel"; when both "Add N enabled" and
  "Add all N" options are shown, only "Add all N" carries the primary action style.
- **"Disable All Repositories" window title**: was "Disable all repositories?" — removed
  the question mark; title is now declarative and title-case like all other windows.
- **"About Repoman" menu label**: capitalised to match the window title.
- **"Remove Multiple Repositories" window title**: now includes "Multiple" to distinguish
  from single-repo removal.
- **State file terminology**: file dialogs and filter labels now say "state" consistently
  (was "configuration" / "configs" in file dialogs, "state" in the menu).
- **metainfo.xml description**: updated to reflect current feature set (Software Updater
  replaces the removed built-in apt update).

### Removed

- **`python3-xlib` and `gir1.2-packagekitglib-1.0` dependencies**: both are unused.
  Window positioning code was removed in 0.2.1; PackageKit was removed in 0.1.6.

### Documentation

- Config reference updated to v2 format: `saved_codename` and `signed_by_content_b64`
  fields documented; signing-key warning corrected (v2 bundles keys automatically);
  cross-machine restore classification flow added.
- Hamburger navigation dropdown synced with the full site nav (was missing Why repoman,
  Installation, and State Management pages).
- Keyboard shortcuts table added to Getting Started.
- Companion tools section added to Managing Repositories (Software Updater,
  Software & Updates, Install a .deb package).
- AppStream screenshots added to `net.tecktron.repoman.metainfo.xml`.

---

## 0.2.1 — 2026-07-10

### Changed

- **App ID**: renamed to `net.tecktron.repoman` (owned domain, removes GitHub dependency).
- **Help URL**: updated to `repoman.tecktron.net` (stable owned subdomain).
- **Restore wizard redesign**: matched repos whose suite is already current skip network
  checks and only sync their enabled state. Clearer "Existing repos" vs "Adding repos"
  grouping throughout.
- **Window positioning removed**: all positioning code deleted. GTK4 removed
  `gtk_window_move()` and the available alternatives were either fragile or visually
  inconsistent on Xfce. Window placement is now left entirely to the window manager.

### Fixed

- Opening URLs now works correctly on Xfce without a GNOME portal.
- `entry_to_repository()` normalises `.list` source paths to `.sources`.
- Missing repos dialog no longer crashes when the list is empty.

### Added

- Tooltips and popovers on compat checker rows for suite-agnostic and non-PPA repos.
- Availability icon updated to `tecktron-repoman-available`.

---

## 0.2.0 — 2026-07-08

### Added

- **Restore wizard**: cross-machine restore now uses a 3-page wizard (classify, check PPAs,
  confirm + apply) instead of a flat dialog. Shows per-PPA spinners with live results,
  grouped summaries, and a familiar wizard-style flow consistent with the upgrade assistant.
- **Exit menu item**: **Tools → Exit** closes the application immediately. Keyboard shortcut: `Ctrl+Q`.
- **Select disabled button**: the Remove Multiple Repos dialog now has a **Select disabled** button
  in the bottom-left corner that automatically checks all currently disabled repositories. It never
  deselects anything, so it is safe to click multiple times or after manually selecting other rows.

---

## 0.1.7 — 2026-07-08

### Added

- **Cross-machine restore**: loading a `.repoman` file saved on a different Ubuntu
  release now adapts repository suites automatically. PPAs are checked against
  Launchpad; third-party repos with older codenames are updated to the current release;
  repos that use a newer codename than the current OS are added as disabled. A summary
  dialog shows exactly what will change before anything is written.
- **Bundled GPG keys**: `.repoman` files (format v2) now embed signing key bytes as
  base64. On restore, keys are written to their original paths via polkit — no manual
  key installation needed. Version 1 files continue to work with the old behaviour.
- **State Management help page**: new documentation covering save, load, cross-machine
  restore, and the `.repoman` file format.

---

## 0.1.6 — 2026-07-07

### Fixed

- About dialog now reads version from `repoman.__version__` instead of a hardcoded string — no longer shows stale version across releases.

### Changed

- Removed "Reload repositories (apt update)" from the Tools menu; `Ctrl+R` now opens Software Updater (if installed). Software Updater already provides `apt update` and package upgrades, making the built-in reload redundant.

---

## 0.1.5 — 2026-07-03

### CI

- Add `workflow_dispatch` trigger to the `.deb` build workflow so it can be run manually without requiring a new release tag

---

## 0.1.4 — 2026-07-03

### Documentation

- PPA published at `ppa:tecktron-studios/repoman` — install instructions updated
- Fix incorrect menu path for Save state / Load state (Repos menu, not Tools)
- Remove pre-release warnings now that the initial release is available

---

## 0.1.3 — 2026-07-03

### Documentation

- Add header navigation dropdown menu to all doc pages
- Fix broken `/developers/` page when clicking from Material's instant navigation

---

## 0.1.2 — 2026-07-03

### Documentation

- Fix Sphinx API reference not appearing at `/developers/` in the deployed site

---

## 0.1.1 — 2026-07-03

### Documentation

- Added screenshots throughout the help docs
- Published full Sphinx API reference at `/developers/`
- Fixed GitHub Pages deployment workflow

---

## 0.1.0 — 2026-06-29

First release.

### Features

- Scans `/etc/apt/sources.list.d/` and lists all third-party repositories
- Detects disabled repositories and stale codenames after Ubuntu upgrades
- Upgrade wizard: select, check availability, confirm, apply in one polkit prompt
- Pre-upgrade compatibility checker with Launchpad PPA enrichment
- Add repository (URL tab: paste one-liner or DEB822 block; Manual tab: individual fields)
- Remove single repository or multiple repositories at once
- GPG signing key editor (fetch, browse, paste)
- Edit repository details: description, suite, components, enabled state, signing key path
- Annotations: descriptions stored as `X-Repolib-Name:` in `.sources` files, survive upgrades
- Legacy `.list` → DEB822 `.sources` conversion on save
- State management: save and load `.repoman` snapshots
- Privilege separation: GUI runs as normal user, writes via polkit helper
