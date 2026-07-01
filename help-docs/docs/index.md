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

## What repoman does

Every Ubuntu version upgrade silently disables your third-party APT repositories — PPAs, vendor repos, all of them. Ubuntu replaces `Enabled: yes` with `Enabled: no` and strips any comments you've added. There's also a subtler failure: repos that survive the upgrade with `Enabled: yes` but carry no packages for the new codename generate silent 404 errors on every `apt update` run.

repoman catches both — and it doesn't stop there. Between upgrades it's a full repository manager: add repos from a one-liner or a DEB822 block, remove ones you no longer need, edit any field, fetch and install signing keys, and save a snapshot of your entire repo configuration to restore after a fresh install or on a new machine.

---

## Features

<div class="grid cards" markdown>

-   :material-magnify: __Finds what broke after an upgrade__

    ---

    Scans your system and flags every third-party repository that got disabled or is silently 404-ing for your current Ubuntu release — the failures `apt update` won't explain.

-   :material-list-status: __Guided upgrade workflow__

    ---

    A step-by-step wizard walks you through selecting, checking availability against Launchpad and the network, and re-enabling repositories in a single polkit prompt.

-   :material-shield-check-outline: __Pre-upgrade compatibility check__

    ---

    Pick a target Ubuntu release before you upgrade and see which of your PPAs support it. UNAVAILABLE repos show which release they were last published for.

-   :material-plus-circle-outline: __Add repositories__

    ---

    Paste a `deb` one-liner or a full DEB822 block (Auto tab), or fill in fields manually (Manual tab). Optionally fetch and install the signing key in the same step.

-   :material-delete-outline: __Remove repositories__

    ---

    Remove a single repository from the detail pane, or open the bulk removal dialog to check off multiple repos and delete them in one polkit prompt.

-   :material-pencil-outline: __Edit repository details__

    ---

    Change the name, suite, components, or enabled state of any repo. The detail pane writes changes back to the `.sources` file with a single Save.

-   :material-key-outline: __GPG signing key management__

    ---

    Add or edit signing keys for any repository — fetch from a URL, browse for a file, or paste content directly. Keys are verified before being installed.

-   :material-content-save-outline: __Save and restore state__

    ---

    Export your full repo list to a `.repoman` snapshot file. Load it on any machine to restore enabled states, create missing repos, and migrate your setup after a reinstall.

-   :material-note-edit-outline: __Annotations that survive upgrades__

    ---

    Add descriptions to your repositories. repoman stores them as `X-Repolib-Name:` directly in the `.sources` file — no sidecar database, nothing stripped on the next upgrade.

-   :material-file-replace-outline: __Legacy format migration__

    ---

    Works with both modern DEB822 `.sources` files and legacy `.list` format. Set a description on a `.list` repo and repoman converts it automatically on save.

-   :material-shield-lock-outline: __Privilege separation__

    ---

    The GUI runs as your normal user. Only write operations that require it are escalated via polkit — no running the whole app as root.

</div>

---

## System requirements

- **Ubuntu 24.04 LTS or later** — Xubuntu, Kubuntu, Ubuntu GNOME, and any other official flavor
- GTK4 and libadwaita 1.5 — included with Ubuntu 24.04, no extra packages needed
- No additional runtime dependencies beyond what Ubuntu ships
