# Managing Repositories

## Browsing

The left sidebar lists all third-party repositories found in `/etc/apt/sources.list.d/`. Click any row to open it in the detail pane. The search bar at the top filters by display name or URI.

## Editing a repository

Select a repository to see its fields in the detail pane:

- **Name / Description** — a human-readable label stored as `X-Repolib-Name:` in the `.sources` file. See [Annotations](annotations.md).
- **Suite** — the Ubuntu codename or fixed suite name (e.g. `noble`, `stable`).
- **Components** — space-separated list (e.g. `main contrib non-free`).
- **Enabled** — toggle to enable or disable without deleting the file.
- **Signing key** — the path to the GPG keyring file used to verify packages from this repository.

The detail pane also has two utility buttons at the top right:

- **Copy URI** — copies the repository's primary URI to the clipboard.
- **Open in browser** — opens the repository URI in your default web browser.

Click **Save** to write the changes. A polkit authentication dialog appears because writing to `/etc/apt/sources.list.d/` requires root.

<!-- screenshot: detail-pane-edit -->
!!! example ""
    *Screenshot coming soon.*

!!! note "Legacy .list format"
    If a `.list` repository has no description, editing the Name field and saving converts it to DEB822 `.sources` format automatically. The old `.list` file is deleted and the new `.sources` file is written in a single polkit operation.

## Adding a repository

Open **Repos → Add Repository…**

### Auto tab

Paste a one-liner or a full DEB822 block directly from a project's installation instructions:

```
deb [signed-by=/usr/share/keyrings/example.gpg] https://packages.example.com/ubuntu noble main
```

```
Types: deb
URIs: https://packages.example.com/ubuntu
Suites: noble
Components: main
Signed-By: /usr/share/keyrings/example.gpg
X-Repolib-Name: Example Project
```

If the source provides a GPG key URL, paste it in the **GPG key URL** field below the text area. repoman will download and install the key alongside the repository file.

### Manual tab

Fill in individual fields:

| Field | Description |
|-------|-------------|
| Repository URI | The base URL of the repository |
| Suite / Codename | The release name or fixed suite |
| Components | Space-separated (defaults to `main`) |
| Name / Description | Optional human-readable label |
| GPG key URL | URL to the signing key — auto-fills the key path |
| Signing key path | Where the key will be installed (`/usr/share/keyrings/…`) |
| Include source packages | Adds `deb-src` type |
| Enabled | Whether the repository is active on save |

When a key URL is provided, the signing key path is filled automatically based on the repository hostname. You can override it by clearing the key URL field and typing a path directly.

Click **Add Repository**. If a key URL was provided, the key is downloaded, verified, and written alongside the `.sources` file — both in a single polkit prompt.

<!-- screenshot: add-repo-dialog -->
!!! example ""
    *Screenshot coming soon.*

## Removing a repository

### Single repository

With a repository selected, click **Remove repository…** at the bottom left of the detail pane. A confirmation dialog shows the filename that will be deleted. Confirm to proceed — a polkit prompt follows, then the row is removed from the sidebar.

### Multiple repositories

Open **Repos → Remove Multiple…** to open a checklist of all repositories. Check any number, then click **Remove N selected**. One polkit prompt covers all deletions.

## Signing keys

Every repository row in the detail pane has a **Signing key** section showing the current state:

| State | Display |
|-------|---------|
| No key configured | "No signing key configured" + **Add** button |
| Key file exists | Filename + **Edit** button |
| Key path set but file missing | "Key file not found" (warning style) + **Add** button |

### Adding a key

Click **Add** to open the key editor. Three ways to provide a key:

- **Fetch** — enter a key URL and click Fetch. For PPA repositories, the key is retrieved automatically from Launchpad without a URL.
- **Use existing file** — browse to a `.gpg`, `.asc`, or `.pgp` file already on your system.
- **Paste** — paste an ASCII-armored key block directly. repoman verifies it before saving.

### Editing a key

Click **Edit** to open the key editor in edit mode. The **Key content** tab shows the current key in ASCII-armored format. The **Update** tab lets you replace the key from a file or URL without changing the path.

<!-- screenshot: key-editor -->
!!! example ""
    *Screenshot coming soon.*

## Disabling all repositories

**Repos → Disable All Third-Party Repos…** sets `Enabled: no` on every repository in one polkit operation. This is useful before an Ubuntu upgrade to prevent APT from attempting to fetch packages from repos that may not be ready.

Re-enable them individually from the detail pane, or use the upgrade wizard after the upgrade completes.

## Reloading repository metadata

**Tools → Reload repositories (apt update)…** runs the equivalent of `sudo apt update` via PackageKit. A toast appears while the refresh is in progress and updates when it completes.

This does not install or upgrade any packages — it only refreshes the package index.
