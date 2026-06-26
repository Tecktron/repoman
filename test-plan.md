# Repoman End-to-End Test Plan

Covers the full wizard flow, compat checker, and state management using fake
`.sources` files on a live `noble` system. Real repos in `/etc/apt/sources.list.d/`
are visible alongside the test files — focus on the `repoman-test-*` entries.

---

## Phase 1 — One-time setup

### 1a. Install polkit policy

```bash
sudo cp /home/craig/Projects/repoman/data/io.github.Tecktron.repoman.policy \
        /usr/share/polkit-1/actions/
```

Verify:
```bash
ls /usr/share/polkit-1/actions/io.github.Tecktron.repoman.policy
```

### 1b. Make polkit helper executable

```bash
chmod +x /home/craig/Projects/repoman/polkit-helper
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

```bash
cd /home/craig/Projects/repoman
pkill -f "python3 -m repoman.main" 2>/dev/null; sleep 0.3
PYTHONPATH=/usr/lib/python3/dist-packages:/home/craig/Projects/repoman/src \
DISPLAY=:0 \
REPOMAN_HELPER_PATH=/home/craig/Projects/repoman/polkit-helper \
python3 -m repoman.main > /tmp/repoman.log 2>&1 &
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
  - VS Code → **⟳** sync icon (SUITE_AGNOSTIC — detected at parse time)
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
  - VS Code → **⟳** sync icon (SUITE_AGNOSTIC — no network call needed)
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

Open **Tools → Check pre-update compatibility…**

**Expected:**
- Window opens with Xfwm4 titlebar
- System group shows current release and upgrade path
- Target release combo is populated from ubuntu.csv
- **Check compatibility** button is enabled

Select a target release and click **Check compatibility**.

**Expected:**
- PPA repos show spinners then resolve to status icons
- Suite-agnostic repos show sync icon immediately (no network call)
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

- Edit the `.repoman` file to add a fake repo entry with a URI not present on this system
- Reload it

**Expected:**
- Alert dialog "N repository/repositories not found" with Skip / Add all options
- "Add all N" → polkit prompt, file created in sources.list.d, sidebar refreshes
- "Skip" → dialog closes, no file created

---

## Phase 9 — Cleanup

```bash
sudo rm /etc/apt/sources.list.d/repoman-test-docker.sources \
        /etc/apt/sources.list.d/repoman-test-vscode.sources \
        /etc/apt/sources.list.d/repoman-test-fake.sources
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
- [ ] Step 1: SUITE_AGNOSTIC repos show sync icon
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
