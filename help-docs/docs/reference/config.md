# Configuration Reference

## State files (.repoman)

State files let you save a snapshot of your repository configuration and restore it later — on the same machine after a fresh install, or on a different machine entirely.

### Saving

**Repos → Save state…** opens a file dialog. The default filename is `state-YYYY-MM-DD.repoman`. Choose any location; the file is written as your normal user with no polkit prompt.

### Loading

**Repos → Load state…** opens a file dialog. repoman reads the file and compares it against the repositories currently on the system, matching by URI.

Three outcomes per repository in the file:

| Outcome | Action |
|---------|--------|
| URI found, enabled state differs | Updated via polkit |
| URI found, state matches | No-op |
| URI not found on this system | Offered as "missing" |

If any repositories from the file are not found on the system, a dialog lists them and offers three options:

- **Cancel** — load the changes to existing repositories and ignore the missing ones
- **Add N enabled** — create `.sources` files for the missing repositories with `Enabled: yes`
- **Add all N** — same, but respects the `enabled` state from the file

!!! info "Signing keys (v2 files)"
    Version 2 state files embed the GPG key bytes as `signed_by_content_b64` when the key file is readable at save time. On restore, repoman writes the key file automatically — no manual step needed.

    If the key was not readable at save time, or you are loading a version 1 file, only the path is stored. In that case you will need to install the key on the new machine before APT can verify packages from that repository.

Repositories on the system that are absent from the file are left untouched.

### File format

State files are JSON with a `.repoman` extension:

```json
{
  "version": 2,
  "saved_at": "2026-07-15T14:22:00",
  "saved_codename": "noble",
  "repos": [
    {
      "types": ["deb"],
      "uris": ["https://packages.example.com/ubuntu"],
      "suites": ["noble"],
      "components": ["main"],
      "enabled": true,
      "description": "Example Project",
      "signed_by": "/usr/share/keyrings/example.gpg",
      "signed_by_content_b64": "<base64-encoded key bytes>",
      "source_file": "/etc/apt/sources.list.d/example.sources"
    }
  ]
}
```

Fields:

| Field | Type | Description |
|-------|------|-------------|
| `version` | integer | File format version. Currently `2`. |
| `saved_at` | string | ISO 8601 timestamp of when the file was saved. |
| `saved_codename` | string | Ubuntu codename of the machine that saved the file. Absent in v1 files. Triggers cross-machine restore when it differs from the current codename. |
| `repos` | array | List of repository entries. |
| `types` | string[] | `["deb"]`, `["deb-src"]`, or `["deb", "deb-src"]` |
| `uris` | string[] | Repository base URLs. Matching on load uses `uris[0]`. |
| `suites` | string[] | Distribution codenames or suite names. |
| `components` | string[] | Repository components (e.g. `["main", "contrib"]`). |
| `enabled` | boolean | Whether the repository should be enabled. |
| `description` | string or null | Human-readable name (`X-Repolib-Name`). |
| `architectures` | string[] | Architecture filter (e.g. `["amd64"]`). Empty list means all architectures. |
| `signed_by` | string or null | Path to a GPG keyring file, or an inline ASCII-armored PGP key block. |
| `signed_by_content_b64` | string or null | Base64-encoded GPG key bytes, embedded at save time when the key file is readable. Used by the restore flow to write the key automatically. Absent in v1 files. |
| `source_file` | string | Original path in `sources.list.d/` — used as a hint when creating missing repos. |

### Cross-machine restore

When `saved_codename` is present in the file and differs from the current machine's
codename, repoman launches the cross-machine restore wizard instead of the fast path.

Each repository entry in the file is classified into one of four actions:

| Classification | Condition | Result |
|----------------|-----------|--------|
| `restore_as_is` | Suite already matches current codename, or suite is agnostic | Sync enabled state only |
| `update_suite` | Suite is a stale codename (non-PPA repo) | Update suite to current codename and sync enabled state |
| `add_disabled` | PPA confirmed unavailable for current codename | Create as disabled |
| `ppa_check` | PPA not yet checked | Live availability check (HEAD to InRelease) → resolves to `update_suite` or `add_disabled` |

The wizard shows a three-page flow: classify → check PPAs (if any `ppa_check` entries
remain) → confirm and apply. See the [State Management guide](../usage/state-management.md)
for a full walkthrough with screenshots.

## Suite-agnostic names

repoman treats certain suite names as version-agnostic — repositories using these suites are not flagged as needing a codename update, and the upgrade wizard leaves their `Suites:` field unchanged.

The built-in list includes: `stable`, `main`, `testing`, `sid`, `unstable`, `bookworm`, `bullseye`, `buster`, `stretch`, `oldstable`, `oldoldstable`.

Any suite name containing non-alphabetic characters (e.g. `focal-security`, `noble/updates`) is also treated as agnostic.

### User override

To add your own suite names, create:

```
~/.config/repoman/suite-agnostic.conf
```

One name per line, `#` for comments. If this file exists and is non-empty, it replaces the built-in list entirely — include any built-in names you still want.

```
# ~/.config/repoman/suite-agnostic.conf
stable
main
lts
```

The system-wide list is at `/usr/share/repoman/suite-agnostic.conf`.
