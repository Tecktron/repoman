# Repoman

**Repo Man** — Repossess your PPAs.

A GTK4 + libadwaita graphical tool for managing third-party APT repositories on Ubuntu and Xubuntu. After a release upgrade, repoman checks which of your PPAs and custom repositories are available for the new codename, updates their `Suites:` fields in one authenticated step, and flags anything that needs attention.

> The name is a nod to the 1984 film.

---

## Features

- Scans `/etc/apt/sources.list.d/` and lists all third-party repositories
- Detects disabled repos and stale codenames left over after Ubuntu upgrades
- **Upgrade wizard** — select repos, check availability against Launchpad/network, confirm, apply in one polkit prompt
- **Pre-upgrade compatibility checker** — pick a target release and see which PPAs support it, with "last available" enrichment for discontinued ones
- **Add repository** — paste a one-liner or DEB822 block (Auto tab), or fill individual fields (Manual tab), with optional GPG key fetch
- **Remove** a single repository or multiple at once
- **GPG signing key editor** — fetch from URL, browse, or paste; verify before installing
- **Edit** description, suite, components, enabled state, and signing key path for any repo
- **Annotations** — human-readable names stored as `X-Repolib-Name:` in `.sources` files; survive future upgrades
- **Legacy `.list` → DEB822 `.sources` conversion** on save
- **State management** — save and load `.repoman` snapshots to migrate configs across machines
- **Reload** repository metadata via PackageKit (`apt update` equivalent)
- Privilege separation — GUI runs as your normal user; file writes go through a polkit helper

---

## Requirements

- Ubuntu / Xubuntu 24.04 LTS or later (libadwaita ≥ 1.5.0)
- Python 3.12+

Runtime dependencies (all available as system packages):

| Package | Purpose |
|---------|---------|
| `python3-gi` | GObject introspection bindings |
| `gir1.2-gtk-4.0` | GTK 4 |
| `gir1.2-adw-1` (≥ 1.5) | libadwaita |
| `gir1.2-packagekitglib-1.0` | PackageKit (apt update) |
| `python3-debian` | DEB822 file parsing |
| `python3-launchpadlib` | Launchpad PPA availability checks |
| `python3-requests` | HTTP for non-PPA availability checks |
| `python3-xlib` | Window centering via X11 |
| `policykit-1` | Polkit for privileged writes |
| `lsb-release` | Current codename detection |

---

## Installation

### From a .deb package (recommended)

Not yet published. See [Building a .deb](#building-a-deb) below.

### Manual install with make

Installs to `/usr/` by default. Requires `sudo`.

```bash
git clone https://github.com/Tecktron/repoman.git
cd repoman
sudo make install
```

To install to a different prefix (e.g. `/usr/local`):

```bash
sudo make install PREFIX=/usr/local
```

To uninstall:

```bash
sudo make uninstall
```

What `make install` does:

- Copies the Python package to `/usr/lib/python3/dist-packages/repoman/`
- Installs `bin/repoman` to `/usr/bin/repoman`
- Installs the polkit helper to `/usr/lib/repoman/polkit-helper`
- Installs the `.desktop` file, icons (SVG + 8 PNG sizes), GSettings schema, polkit policy, AppStream metadata, and `suite-agnostic.conf`
- Runs post-install hooks: `glib-compile-schemas`, `gtk-update-icon-cache`, `systemctl reload polkit`

---

## Running from source (development)

Install runtime dependencies:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-packagekitglib-1.0 \
    python3-debian python3-launchpadlib python3-requests python3-xlib \
    policykit-1 lsb-release
```

Symlink the polkit helper so privilege escalation works correctly in-tree:

```bash
sudo mkdir -p /usr/lib/repoman
sudo ln -sf /path/to/repoman/polkit-helper /usr/lib/repoman/polkit-helper
```

The polkit policy must also be installed and polkit restarted once:

```bash
sudo install -m 644 data/io.github.Tecktron.repoman.policy \
    /usr/share/polkit-1/actions/
sudo systemctl restart polkit
```

Run the app:

```bash
cd /path/to/repoman

# Kill any existing instance first — a second launch opens in the existing process
pkill -f "python3 -m repoman.main" 2>/dev/null; sleep 0.3

PYTHONPATH=/usr/lib/python3/dist-packages:/path/to/repoman/src \
DISPLAY=:0 \
python3 -m repoman.main
```

---

## Building a .deb

```bash
# Install build tools once
sudo apt install debhelper dh-python pybuild-plugin-pyproject python3-all python3-setuptools

cd /path/to/repoman
dpkg-buildpackage -us -uc

# Install the built package
sudo dpkg -i ../repoman_*.deb
```

The `debian/` directory contains `control`, `rules` (debhelper + pybuild), `install`, `postinst` (runs post-install hooks), and `changelog`.

---

## Project layout

```
repoman/
├── bin/
│   └── repoman                  # Entry point script
├── src/repoman/
│   ├── main.py                  # RepomanApplication (Adw.Application)
│   ├── models.py                # Repository, WizardState dataclasses; enums
│   ├── parser.py                # Scans sources.list.d/; DEB822 + one-line formats
│   ├── writer.py                # repo_to_deb822() serialiser; enable_patch()
│   ├── converter.py             # ONE_LINE → DEB822 conversion
│   ├── checker.py               # Availability checks (Launchpad + network)
│   ├── upgrade_info.py          # OS release detection; PPA suite queries
│   ├── utils.py                 # get_current_codename(); repos_needing_attention()
│   ├── paths.py                 # Tool discovery; check_required_tools()
│   ├── config_io.py             # Save/load .repoman state files (no GTK)
│   ├── source_parse.py          # Pure source-line parsing helpers
│   ├── gpg.py                   # GPG key fetch, verify helpers (no GTK)
│   └── ui/
│       ├── main_window.py       # RepomanWindow — sidebar + detail pane
│       ├── repo_row.py          # RepoRow (Adw.ActionRow) — sidebar item
│       ├── detail_pane.py       # DetailPane — edit + save a repository
│       ├── add_repo_dialog.py   # Add Repository dialog (Auto + Manual tabs)
│       ├── key_editor_window.py # Add/Edit GPG signing key window
│       ├── compat_checker.py    # Pre-upgrade compatibility checker window
│       ├── position.py          # Window centering via python-xlib
│       └── wizard/
│           ├── dialog.py        # RepomanWizardDialog — upgrade assistant
│           ├── base_page.py     # RepomanWizardPage base class
│           ├── select_page.py   # Step 1: choose repositories
│           ├── check_page.py    # Step 2: check availability (background thread)
│           └── confirm_page.py  # Step 3: review + apply via polkit
├── polkit-helper                # Privileged write helper (run via pkexec)
├── data/
│   ├── io.github.Tecktron.repoman.desktop
│   ├── io.github.Tecktron.repoman.policy  # Polkit action definition
│   ├── io.github.Tecktron.repoman.gschema.xml
│   ├── io.github.Tecktron.repoman.metainfo.xml
│   ├── suite-agnostic.conf      # Suite names that never need a codename update
│   └── icons/hicolor/           # App icon — SVG + PNG at 8 sizes
├── tests/                       # pytest test suite
├── help-docs/                   # MkDocs documentation site
├── debian/                      # Debian packaging skeleton
├── Makefile                     # Direct install/uninstall targets
└── pyproject.toml
```

---

## Testing

Run the full test suite from the project root:

```bash
python3 -m pytest tests/ -q
```

Lint and format checks:

```bash
ruff check src/
ruff format --check src/
```

Install test/dev dependencies:

```bash
pip install pytest ruff
```

Tests cover: parser, writer, converter, checker, upgrade info, utils, config I/O, GPG helpers, and source parsing. All tests are pure (no GTK, no network, no disk writes) and run without any system services.

---

## Contributing

1. Fork the repository and create a feature branch.
2. Make your changes. Follow the patterns in `CLAUDE.md` for coding conventions (imports, type hints, exception handling, GTK widget choices).
3. Ensure all tests pass and no lint errors: `pytest tests/ -q && ruff check src/`
4. Open a pull request with a clear description of what changed and why.

Please keep pull requests focused — one feature or fix per PR. UI changes that touch GTK widget selection should reference the widget guidance in `CLAUDE.md`.

---

## License

See [LICENSE](LICENSE).
