# Repoman End-to-End Test Plan

Covers the full wizard flow, compat checker, and state management using fake
`.sources` files on a live `noble` system. Real repos in `/etc/apt/sources.list.d/`
are visible alongside the test files — focus on the `repoman-test-*` entries.

---

## Phase 1 — One-time setup

### 1a. Install polkit policy

```bash
sudo cp /home/craig/Projects/repoman/data/net.tecktron.repoman.policy \
        /usr/share/polkit-1/actions/
```

Verify:
```bash
ls /usr/share/polkit-1/actions/net.tecktron.repoman.policy
```

### 1b. Make polkit helper executable

```bash
chmod +x /home/craig/Projects/repoman/polkit-helper
```

### 1c. Symlink helper to installed path

Required for polkit to match the action and honour `auth_admin_keep`:

```bash
sudo mkdir -p /usr/lib/repoman
sudo ln -sf /home/craig/Projects/repoman/polkit-helper /usr/lib/repoman/polkit-helper
```

---

## Phase 2 — Create test repo files

Three files covering all three wizard outcomes.

### File A — stale codename, expects AVAILABLE

Docker publishes noble packages so the availability check returns green.

```bash
sudo tee /etc/apt/sources.list.d/repoman-test-docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: jammy
Components: stable
Enabled: yes
X-Repolib-Name: Docker CE (test)
EOF
```

### File B — disabled suite-agnostic repo, expects re-enabled with suite unchanged

`stable` is suite-agnostic. The wizard re-enables it but does **not** change the
suite field to the target codename.

```bash
sudo tee /etc/apt/sources.list.d/repoman-test-vscode.sources <<'EOF'
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Enabled: no
X-Repolib-Name: VS Code (test)
EOF
```

### File C — fake URL, expects UNAVAILABLE (skipped)

Tests the "Skipped" section on the confirm page.

```bash
sudo tee /etc/apt/sources.list.d/repoman-test-fake.sources <<'EOF'
Types: deb
URIs: https://packages.nonexistent-repoman-test.example.com
Suites: jammy
Components: main
Enabled: yes
X-Repolib-Name: Fake Unavailable Repo (test)
EOF
```

---

## Phase 3 — Launch the app

**Option A — from source (development):**

```bash
cd /home/craig/Projects/repoman
pkill -f "python3 -m repoman.main" 2>/dev/null; sleep 0.3
PYTHONPATH=/usr/lib/python3/dist-packages:/home/craig/Projects/repoman/src \
DISPLAY=:0 \
python3 -m repoman.main > /tmp/repoman.log 2>&1 &
```

**Option B — from .deb (installed package):**

```bash
dpkg-buildpackage -us -uc
sudo dpkg -i ../repoman_*.deb
# App auto-launches on install; or run: repoman
```

> Real repos will be visible alongside the test repos — focus on the
> `repoman-test-*` entries during wizard testing.

---

## Phase 4 — Walk through the wizard

### 4a. Banner

**Expected:** Banner appears and mentions repos needing review. The count includes
your real repos alongside the 3 test repos — look for the banner itself rather than
a specific count. The 3 test repos that should be flagged are:
- Docker CE (`jammy` ≠ `noble` — stale codename)
- VS Code (disabled)
- Fake Unavailable Repo (`jammy` ≠ `noble` — stale codename)

### 4b. Open wizard

Click **Review** on the banner, or **Tools → Run Upgrade Assistant**.

**Expected:** Wizard opens with Xfwm4 titlebar, showing "Select repositories"

### 4c. Step 1 — Select repositories

**Expected:**
- The 3 test repos listed and pre-ticked (real repos needing attention will also appear)
- Group header has a **"Deselect all"** button (all are ticked, so label reads "Deselect all")
- Status icons on the test repos (no network checks run yet on this page):
  - Docker CE → dimmed **?** (UNKNOWN — stale codename, not yet checked)
  - VS Code → **🔒** lock icon (SUITE_AGNOSTIC — detected at parse time)
  - Fake → dimmed **?** (UNKNOWN)
- "Check availability" button is active

**Try:**
- Click **"Deselect all"** → all unchecked, label changes to "Select all", "Check availability" goes insensitive
- Click **"Select all"** → all re-ticked, button re-enables
- Manually untick one → label reverts to "Select all" (not all checked)
- Leave all ticked, click **Check availability**

### 4d. Step 2 — Checking availability

**Expected:**
- All rows start with spinning indicators
- Results after checks complete (for the test repos):
  - Docker CE → green **✓** (AVAILABLE)
  - VS Code → **🔒** lock icon (SUITE_AGNOSTIC — no network call needed)
  - Fake → orange **⚠** (UNAVAILABLE — may take a few seconds to time out)
- Hover over each icon → tooltip shows the status description
- Once all resolve, "Next" button becomes active
- Group description updates to reflect how many of the total checked repos are available

**Back-navigation check:**
- Click **Back** to return to Step 1
- Click **Check availability** again → icons should remain as-is, **no duplicates**

Click **Next**

### 4e. Step 3 — Confirm changes

**Expected:**
- **"Will be re-enabled"** group (visible — there are repos to apply):
  - Docker CE with **✓** icon; tooltip: "Will be re-enabled for noble"
  - VS Code with **✓** icon; tooltip: "Will be re-enabled (suite-agnostic — suite field unchanged)"
- **"Skipped — not yet available"** group:
  - Fake Unavailable Repo with **⚠** icon; tooltip: "Not yet available — skipped"
- **Auth row**: "Administrator password required — Writes to /etc/apt/sources.list.d/" with lock icon
- Button reads **"Apply changes"**

**Try (optional):** Close with the X button → verify clean close; re-open from Tools menu → fresh wizard.

### 4f. Empty-state variant (optional but worth checking)

To verify the "Done" path: run the wizard when only suite-agnostic repos are flagged, or
after applying the changes above so only non-applicable repos remain.

**Expected:**
- "Will be re-enabled" group is **hidden** (not shown as an empty section)
- Auth row is **hidden**
- Button reads **"Done"** — clicking it closes the wizard without polkit prompt

### 4g. Apply changes

Click **Apply changes**

**Expected:**
- polkit authentication dialog appears
- After authenticating: wizard closes, sidebar and banner refresh

---

## Phase 5 — Verify the files were updated

```bash
cat /etc/apt/sources.list.d/repoman-test-docker.sources
```
**Expected:** `Suites: noble` (updated from `jammy`), `Enabled: yes`

```bash
cat /etc/apt/sources.list.d/repoman-test-vscode.sources
```
**Expected:** `Enabled: yes` (re-enabled), `Suites: stable` (**unchanged** — suite-agnostic)

```bash
cat /etc/apt/sources.list.d/repoman-test-fake.sources
```
**Expected:** Unchanged (skipped)

---

## Phase 6 — Edge case checks

### 6a. Cancel polkit

- Open the wizard (only Fake should appear if the other two were fixed)
- Proceed to Step 3, click **Apply changes**
- **Cancel** the polkit dialog

**Expected:** "Failed to apply: …" toast, button re-enables, wizard stays open

### 6b. Close mid-check

- Open the wizard, advance to Step 2 while spinners are running
- Hit the X button

**Expected:** Wizard closes cleanly — no crash, no frozen window

### 6c. Re-open after completion

- Open the wizard again from the Tools menu after a prior successful run

**Expected:** Fresh wizard opens (no stale state)

---

## Phase 7 — Compat checker

Open **Tools → Check pre-upgrade compatibility…**

**Expected:**
- Window opens with Xfwm4 titlebar
- System group shows current release and upgrade path
- Target release combo is populated from ubuntu.csv
- **Check compatibility** button is enabled

Select a target release and click **Check compatibility**.

**Expected:**
- PPA repos show spinners then resolve to status icons
- Suite-agnostic repos show lock icon immediately (no network call)
- Non-PPA repos show ? icon with "Manual check recommended"
- Clicking a status icon opens a detail popover:
  - AVAILABLE: "Repo is ready for {target}"
  - UNAVAILABLE: shows "Latest available: {suite}" or "Last available: {suite}"
  - Contains current suite, target codename, Launchpad link (for PPAs)
- Group description updates to "{N} of {M} available for {target}"
- Close button closes the window

---

## Phase 8 — State Management (Save / Load)

### 8a. Save

- With repos loaded, open **Tools → State Management → Save…**
- Choose a location (e.g. `~/Desktop/test.repoman`)

**Expected:**
- FileDialog opens, default filename is `state-{today}.repoman`
- After saving: toast "Config saved to test.repoman"
- File is valid JSON with `version: 1` and `repos` list

### 8b. Load — no changes

- Immediately load the file you just saved via **Tools → State Management → Load…**

**Expected:** Toast "No changes — system already matches config"

### 8c. Load — with changes

- Manually edit the `.repoman` file to toggle `"enabled"` on one repo
- Reload it

**Expected:**
- polkit prompt for the write
- After auth: sidebar refreshes, toast "Updated 1 repository"

### 8d. Load — missing repos

Create a file called `missing.repoman` with the following content:

```json
{
  "version": 1,
  "saved_at": "2026-06-27T10:00:00",
  "repos": [
    {
      "types": ["deb"],
      "uris": ["https://packages.missing-test.repoman.example.com/ubuntu"],
      "suites": ["noble"],
      "components": ["main"],
      "enabled": true,
      "description": "Missing Test Repo",
      "source_file": "/etc/apt/sources.list.d/missing-test.sources"
    }
  ]
}
```

Load it via **Tools → State Management → Load…**

**Expected:**
- Alert dialog "1 repository not found" with Skip / Add all options
- "Add all 1" → polkit prompt, file created in sources.list.d, sidebar refreshes
- "Skip" → dialog closes, no file created

To also test the GPG warning shown in the dialog, add `"signed_by": "/usr/share/keyrings/missing-test-archive-keyring.gpg"` to the repo entry before loading.

---

## Phase 9 — Add repository

### 9a. Add via URL tab (one-liner)

Open **Repos → Add Repository…**, paste into the URL tab:

```
deb https://download.docker.com/linux/ubuntu noble stable
```

Click **Add Repository**.

**Expected:**
- polkit prompt fires
- After auth: new `download-docker-com.sources` row appears in sidebar, selected
- Detail pane shows the Docker URI, suite `noble`, component `stable`

### 9b. Add via URL tab (DEB822 block)

Open **Repos → Add Repository…**, paste a full DEB822 block:

```
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
X-Repolib-Name: VS Code Test
```

Click **Add Repository**.

**Expected:** File created, row selected, description shows "VS Code Test"

### 9c. Add via Manual tab

Switch to the Manual tab. Fill:
- Repository URI: `https://packages.mozilla.org/apt`
- Suite / Codename: `mozilla`
- Components: `main`
- GPG key URL: _(leave empty)_
- Name / Description: `Mozilla APT`

Click **Add Repository**.

**Expected:** `packages-mozilla-org.sources` created, row selected.

### 9d. Add with GPG key URL

Manual tab, fill URI + paste a key URL (e.g. `https://packages.microsoft.com/keys/microsoft.asc`).

**Expected:**
- Signing key path auto-filled as `/usr/share/keyrings/packages-microsoft-com.gpg`
- After polkit: both `.sources` and `.gpg` files created
- Detail pane signing row shows the key filename

### 9e. URL tab — parse failure

Open **Repos → Add Repository…**, paste garbage text into URL tab and click **Add Repository**.

**Expected:** Inline error label appears ("Could not parse…"), button re-enables.

### 9f. Manual tab — empty URI

Manual tab with URI field empty (button should be insensitive).

**Expected:** "Add Repository" button is greyed out until a URI is typed.

---

## Phase 10 — Remove repository

### 10a. Remove single repo

Select a test repo (e.g. the Docker one added in Phase 9a). Click **Remove repository…**.

**Expected:**
- Confirmation modal opens titled "Remove repository"
- Body mentions the file name
- Cancel → nothing happens, repo still selected
- Click Remove → polkit prompt
- After auth: row gone, detail pane shows "No repository selected" empty state
- Toast: _(no explicit toast — panel just clears)_

### 10b. Remove multiple repos

Create two test repos via Phase 9 steps, then open **Repos → Remove Multiple…**.

**Expected:**
- Window lists all current repos with checkboxes
- "Remove N selected" button is insensitive until at least one is checked
- Check two repos → button label reads "Remove 2 selected"
- Click → polkit prompt
- After auth: both rows gone, sidebar refreshes, toast "Removed 2 repositories"

---

## Phase 11 — Signing key editor

### 11a. Add signing key to repo without one

Select a repo that has no `Signed-By`. The Signing group should show "No signing key configured" with an **Add** button.

Click **Add**.

**Expected:** "Add signing key" window opens with three tabs: Fetch, Use existing file, Paste.

**Fetch tab:**
- Enter a valid key URL and click Fetch
- Key content appears in the text area
- File path row auto-populated if empty
- Save becomes active
- Click Save → polkit → signing row updates with key filename

**Use existing file tab:**
- Click "Choose file…" → file browser opens filtered to `.gpg`, `.asc`, `.pgp`
- Select an existing keyring from `/usr/share/keyrings/`
- Save becomes active (no key content written — just updates Signed-By path)

**Paste tab:**
- Paste an ASCII-armored key block
- Save validates via gpg — rejects garbage, accepts valid key

### 11b. Edit existing signing key

Select a repo with a `Signed-By` field. Signing row shows key filename with **Edit** button.

Click **Edit**.

**Expected:** "Edit signing key" window opens with two tabs: "Key content" and "Update".

- Key content tab shows the armored key text (even for binary `.gpg` files)
- Content is editable; Save button activates when content differs from original
- Update tab has "Replace from file" (opens file browser) and "Replace from URL" with Fetch button
- Selecting a file on Update tab → "Replace key" button activates
- After Replace from file → polkit updates Signed-By path in `.sources`

### 11c. Signing key file missing

Select a repo where `Signed-By` points to a non-existent file.

**Expected:**
- Signing row subtitle "Key file not found" with warning styling
- Button label **Add**
- Clicking Add → key editor opens; key content tab shows warning label, text area empty

---

## Phase 12 — Reload repositories

Open **Tools → Reload repositories (apt update)…**

**Expected:**
- Toast "Updating repositories…" appears
- After PackageKit finishes: toast updates to "Repositories updated"
- If PackageKit fails: error dialog shown with message

---

## Phase 13 — Cleanup

```bash
sudo rm /etc/apt/sources.list.d/repoman-test-docker.sources \
        /etc/apt/sources.list.d/repoman-test-vscode.sources \
        /etc/apt/sources.list.d/repoman-test-fake.sources
```

Remove any repos added in Phases 9–12:

```bash
sudo rm -f /etc/apt/sources.list.d/download-docker-com.sources \
           /etc/apt/sources.list.d/packages-microsoft-com.sources \
           /etc/apt/sources.list.d/packages-mozilla-org.sources
```

If Phase 8d "Add all" was used, also remove the file it created:

```bash
sudo rm -f /etc/apt/sources.list.d/missing-test.sources
```

Remove the test state files:

```bash
rm -f ~/Desktop/test.repoman ~/Desktop/missing.repoman
```

Kill the app:
```bash
pkill -f "python3 -m repoman.main"
```

---

## Success checklist

### Wizard
- [ ] Banner appears and the 3 test repos show up in the wizard
- [ ] Wizard opens from banner and from Tools menu
- [ ] All repos appear in Step 1 with correct pre-ticked state
- [ ] Step 1: "Deselect all" / "Select all" button works correctly
- [ ] Step 1: UNKNOWN repos show dimmed ? icon (no spinner — checks haven't run)
- [ ] Step 1: SUITE_AGNOSTIC repos show lock icon
- [ ] Step 1: unticking all makes "Check availability" insensitive
- [ ] Step 2: all rows start as spinners, resolve to correct icons
- [ ] Step 2: hovering an icon shows the correct tooltip
- [ ] Step 2: navigating Back then Next does NOT duplicate icons
- [ ] Step 2: group description shows correct available count
- [ ] Step 3: "Will be re-enabled" group hidden when no repos to apply
- [ ] Step 3: auth row hidden when no repos to apply
- [ ] Step 3: button reads "Done" when nothing to apply; closes wizard on click
- [ ] Step 3: hovering icons shows correct tooltips
- [ ] Step 3: suite-agnostic repo tooltip says "suite field unchanged"
- [ ] polkit prompt fires on "Apply changes"
- [ ] Docker file updated: `Suites: noble`, `Enabled: yes`
- [ ] VS Code file updated: `Enabled: yes`, `Suites: stable` unchanged
- [ ] Fake repo file is unchanged
- [ ] Banner and sidebar refresh after wizard completes
- [ ] Cancel-polkit shows error toast and recovers cleanly
- [ ] Close mid-check doesn't crash
- [ ] Re-opening wizard after a prior run works cleanly

### Compat checker
- [ ] Window opens and populates system info
- [ ] Check runs and resolves status icons
- [ ] Status popover shows correct details
- [ ] "Latest/Last available" enrichment shown for UNAVAILABLE PPAs

### State Management
- [ ] Save creates a valid `.repoman` JSON file
- [ ] Load with no changes shows "No changes" toast
- [ ] Load with changed enabled state triggers polkit and updates sidebar
- [ ] Load with missing repos offers Add / Skip dialog
- [ ] "Add all" creates files and reloads sidebar

### Add Repository
- [ ] URL tab: one-liner parses correctly, polkit fires, row selected after add
- [ ] URL tab: DEB822 block parses correctly including X-Repolib-Name
- [ ] Manual tab: repo created from individual fields
- [ ] Manual tab: GPG key URL auto-fills Signing key path field
- [ ] Manual tab: key URL provided → key file written alongside .sources in one polkit call
- [ ] URL tab: bad input shows inline error, button re-enables
- [ ] Manual tab: empty URI keeps "Add Repository" insensitive

### Remove Repository
- [ ] Single remove: confirmation modal shows repo name and file
- [ ] Cancel in modal → nothing happens
- [ ] Confirm → polkit → row gone, detail pane shows empty state
- [ ] Remove multiple: checkbox list, button insensitive until ≥1 checked
- [ ] Remove multiple: button label updates with count
- [ ] Remove multiple: polkit → all checked rows gone, sidebar refreshes, toast shown

### Signing Key Editor
- [ ] Add signing key: Fetch tab downloads key and populates text area
- [ ] Add signing key: Use existing file tab — file browser opens, Save activates on selection
- [ ] Add signing key: Paste tab — rejects garbage key, accepts valid armored key
- [ ] Add signing key: after save, signing row updates to show key filename
- [ ] Edit signing key: "Key content" tab shows armored text for binary .gpg files
- [ ] Edit signing key: content change enables Save
- [ ] Edit signing key: "Update" tab — Replace from file updates Signed-By path in .sources
- [ ] Edit signing key: "Update" tab — Replace from URL fetches and writes new key
- [ ] Missing key file: signing row shows "Key file not found", button label is "Add"
- [ ] Missing key file: clicking Add opens editor with empty content tab

### Reload repositories
- [ ] Tools → Reload repositories fires apt update via PackageKit
- [ ] "Updating repositories…" toast appears during refresh
- [ ] Success toast "Repositories updated" shown on completion
- [ ] Failure shows error dialog with message
