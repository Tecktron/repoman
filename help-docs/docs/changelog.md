# Changelog

All notable changes to repoman will be documented here. repoman uses [Semantic Versioning](https://semver.org/).

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
- Reload repository metadata via PackageKit (`apt update` equivalent)
- Privilege separation: GUI runs as normal user, writes via polkit helper
