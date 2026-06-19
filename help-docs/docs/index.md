---
template: home.html
hide:
  - navigation
  - toc
---

<div class="rp-quick-install" markdown>
<p>Quick install</p>

```bash
sudo add-apt-repository ppa:tecktron-studios/repoman
sudo apt update && sudo apt install repoman
```
</div>

!!! warning "Pre-release"
    repoman is not yet publicly available. Watch the [GitHub repository](https://github.com/Tecktron/repoman) for the initial release announcement.

---

## What repoman fixes

Every Ubuntu version upgrade silently disables your third-party APT repositories — PPAs, vendor repos, all of them. Ubuntu does this by replacing the `Enabled: yes` line with `Enabled: no` and stripping any comments you've added, so you lose both the repos and any notes about why they were there.

There's also a subtler failure: repos that survive the upgrade with `Enabled: yes` but whose packages don't exist for the new Ubuntu codename. Those generate silent 404 errors on every `apt update` run. Ubuntu won't explain why. You won't notice until something doesn't install.

repoman catches both.

---

## Features

<div class="grid cards" markdown>

-   :material-magnify: __Finds disabled repos__

    ---

    Scans your system after an Ubuntu upgrade and lists every third-party repository that got disabled, so nothing falls through the cracks.

-   :material-alert-circle-outline: __Catches silent 404s__

    ---

    Detects repositories that appear enabled but carry no packages for your current Ubuntu release — the quiet failures `apt update` doesn't explain.

-   :material-note-edit-outline: __Annotations that survive upgrades__

    ---

    Add descriptions to your repositories. repoman stores them directly in the `.sources` file — no sidecar database, nothing to lose on the next upgrade.

-   :material-list-status: __Guided upgrade workflow__

    ---

    A step-by-step wizard walks you through reviewing, checking availability, and re-enabling repositories after each Ubuntu version upgrade.

-   :material-file-replace-outline: __Legacy format migration__

    ---

    Works with both modern DEB822 `.sources` files and legacy `.list` format. Adds a description to a `.list` repo and repoman converts it automatically.

-   :material-shield-lock-outline: __Privilege separation__

    ---

    The GUI runs as your normal user. Only the write operations that require it are escalated via polkit — no running the whole app as root.

</div>

---

## System requirements

- **Ubuntu 24.04 LTS or later** — Xubuntu, Kubuntu, Ubuntu GNOME, and any other official flavor
- GTK4 and libadwaita 1.4 — included with Ubuntu 24.04, no extra packages needed
- No additional runtime dependencies beyond what Ubuntu ships
