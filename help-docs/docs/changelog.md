# Changelog

All notable changes to repoman will be documented here. repoman uses [Semantic Versioning](https://semver.org/).

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
- Add repository (Auto tab: paste one-liner or DEB822 block; Manual tab: individual fields)
- Remove single repository or multiple repositories at once
- GPG signing key editor (fetch, browse, paste)
- Edit repository details: description, suite, components, enabled state, signing key path
- Annotations: descriptions stored as `X-Repolib-Name:` in `.sources` files, survive upgrades
- Legacy `.list` → DEB822 `.sources` conversion on save
- State management: save and load `.repoman` snapshots
- Privilege separation: GUI runs as normal user, writes via polkit helper
