# Installation

## Requirements

- **Ubuntu 24.04 LTS or later** — Xubuntu, Kubuntu, Ubuntu GNOME, and any other official flavor
- GTK4 and libadwaita 1.5 — included with Ubuntu 24.04, no extra packages needed

All other runtime dependencies are standard system packages available from the Ubuntu archive. No pip installs, no virtual environments.

---

## Via PPA (recommended)

!!! warning "Not yet available"
    The PPA is not yet published. Watch the [GitHub repository](https://github.com/Tecktron/repoman) for the announcement.

Once available:

```bash
sudo add-apt-repository ppa:tecktron-studios/repoman
sudo apt update && sudo apt install repoman
```

---

## Via .deb package

!!! warning "Not yet published"
    Signed `.deb` packages will be attached to each [GitHub release](https://github.com/Tecktron/repoman/releases) once the first release is tagged.

Download the `.deb` from the releases page and install it:

```bash
sudo dpkg -i repoman_*.deb
sudo apt install -f   # resolves any missing dependencies
```

---

## Manual install from source

The current working installation method. Installs to `/usr/` by default.

### 1. Install runtime dependencies

```bash
sudo apt install \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gir1.2-packagekitglib-1.0 \
    python3-debian \
    python3-launchpadlib \
    python3-requests \
    python3-xlib \
    policykit-1 \
    lsb-release
```

### 2. Clone and install

```bash
git clone https://github.com/Tecktron/repoman.git
cd repoman
sudo make install
```

To install to `/usr/local` instead of `/usr`:

```bash
sudo make install PREFIX=/usr/local
```

### 3. Launch

repoman will appear in your application menu under **System**. You can also launch it from a terminal:

```bash
repoman
```

### Uninstalling

```bash
cd repoman
sudo make uninstall
```

---

## What `make install` installs

| Path | Contents |
|------|----------|
| `/usr/lib/python3/dist-packages/repoman/` | Python package |
| `/usr/bin/repoman` | Entry point |
| `/usr/lib/repoman/polkit-helper` | Privileged write helper |
| `/usr/share/applications/` | Desktop entry |
| `/usr/share/icons/hicolor/` | App icon (SVG + 8 PNG sizes) |
| `/usr/share/polkit-1/actions/` | Polkit policy |
| `/usr/share/glib-2.0/schemas/` | GSettings schema |
| `/usr/share/metainfo/` | AppStream metadata |
| `/usr/share/repoman/suite-agnostic.conf` | Suite name configuration |

After installing, `make` runs `glib-compile-schemas`, `gtk-update-icon-cache`, and `systemctl reload polkit` automatically.
