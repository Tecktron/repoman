# Repoman Wizard Dry-Run Test Plan

This plan verifies the full upgrade wizard flow using fake `.sources` files on your live `noble` system, without touching any real repos.

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

Docker publishes noble packages so the availability check should come back green.

```bash
sudo tee /etc/apt/sources.list.d/repoman-test-docker.sources <<'EOF'
# Docker CE (repoman test — stale codename)
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: jammy
Components: stable
Enabled: yes
X-Repolib-Name: Docker CE (test)
EOF
```

### File B — disabled repo, expects SUITE_AGNOSTIC (will be re-enabled)

`stable` is suite-agnostic so the codename won't be updated, but the repo will be re-enabled.

```bash
sudo tee /etc/apt/sources.list.d/repoman-test-vscode.sources <<'EOF'
# VS Code (repoman test — disabled)
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Enabled: no
X-Repolib-Name: VS Code (test)
EOF
```

### File C — fake URL, expects UNAVAILABLE (will be skipped)

Tests the "Skipped" section on the confirm page.

```bash
sudo tee /etc/apt/sources.list.d/repoman-test-fake.sources <<'EOF'
# Fake repo (repoman test — unavailable)
Types: deb
URIs: https://packages.nonexistent-repoman-test.example.com
Suites: jammy
Components: main
Enabled: yes
X-Repolib-Name: Fake Unavailable Repo (test)
EOF
```

---

## Phase 3 — Set up isolated test directory and launch

Create a temp directory and copy only the test files into it:

```bash
mkdir -p /tmp/repoman-test-sources
sudo cp /etc/apt/sources.list.d/repoman-test-*.sources /tmp/repoman-test-sources/
```

Launch the app pointed at that directory:

```bash
cd /home/craig/Projects/repoman
PYTHONPATH=/usr/lib/python3/dist-packages \
DISPLAY=:0 \
REPOMAN_HELPER_PATH=/home/craig/Projects/repoman/polkit-helper \
python3 -m repoman.main --sources-dir /tmp/repoman-test-sources > /tmp/repoman.log 2>&1 &
```

The app will only see the 3 test repos — your real `/etc/apt/sources.list.d/` is not touched.

---

## Phase 4 — Walk through the wizard

### 4a. Banner
**Expected:** Banner reads "3 repositories need review after upgrade"

### 4b. Open wizard
Click **Review** on the banner, or use **Tools → Run Upgrade Assistant**

**Expected:** Wizard opens with a normal Xfwm4 titlebar, showing "Select repositories"

### 4c. Step 1 — Select repositories
**Expected:**
- All 3 test repos listed with checkboxes, all pre-ticked
- "Check availability" button is active

**Try:**
- Untick all → "Check availability" should go grey/insensitive
- Re-tick at least one → button re-enables
- Leave all ticked and click **Check availability**

### 4d. Step 2 — Checking availability
**Expected:**
- All 3 rows show spinning indicators
- Docker (test) → resolves to green ✓ (**AVAILABLE**)
- VS Code (test) → resolves to sync icon (**SUITE_AGNOSTIC**)
- Fake (test) → resolves to warning ⚠ (**UNAVAILABLE**) — may take a few seconds to time out
- Once all resolve, "Next" button becomes active
- Description updates e.g. "2 of 3 available for noble"

Click **Next**

### 4e. Step 3 — Confirm changes
**Expected:**
- **"Will be re-enabled"** group: Docker (test) and VS Code (test), both with ✓ icons
- **"Skipped"** group: Fake Unavailable Repo (test) with ⚠ icon
- Auth row: "Administrator password required — Writes to /etc/apt/sources.list.d/" with lock icon
- "Apply changes" button is active

**Try (optional):** Close the wizard with the X button — verify it closes cleanly and can be re-opened fresh.

### 4f. Apply changes
Click **Apply changes**

**Expected:**
- polkit authentication dialog appears
- After authenticating: wizard closes, sidebar/banner refreshes

---

## Phase 5 — Verify the files were updated

The wizard writes back to wherever it read from — in this case `/tmp/repoman-test-sources/`.

```bash
cat /tmp/repoman-test-sources/repoman-test-docker.sources
```
**Expected:** `Suites: noble` (updated from `jammy`), `Enabled: yes`

```bash
cat /tmp/repoman-test-sources/repoman-test-vscode.sources
```
**Expected:** `Enabled: yes` (re-enabled), `Suites: stable` (unchanged)

```bash
cat /tmp/repoman-test-sources/repoman-test-fake.sources
```
**Expected:** Unchanged (it was skipped)

---

## Phase 6 — Edge case checks

### 6a. Cancel polkit
- Open the wizard again (only Fake repo should appear now if the others were fixed)
- Proceed to the confirm page, click **Apply changes**
- **Cancel** the polkit dialog

**Expected:** "Failed to apply: …" error toast, button re-enables, wizard stays open

### 6b. Close mid-check
- Open wizard, advance to step 2 while availability check is spinning
- Hit the X button

**Expected:** Wizard closes cleanly, no crash, no frozen window

### 6c. Re-open after completion
- Open the wizard a second time from the menu

**Expected:** Fresh wizard opens correctly (no stale state from prior run)

---

## Phase 7 — Cleanup

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

- [ ] Banner correctly counts 3 test repos on startup
- [ ] Wizard opens from banner and from Tools menu
- [ ] All 3 repos appear in step 1, all pre-ticked
- [ ] Availability check resolves all 3 with correct status icons
- [ ] Confirm page splits into "Will be re-enabled" (2) and "Skipped" (1)
- [ ] polkit prompt fires on "Apply changes"
- [ ] Docker and VS Code files updated correctly on disk
- [ ] Fake repo file is unchanged
- [ ] Banner/sidebar refreshes after wizard completes
- [ ] Cancel-polkit shows error toast and recovers cleanly
- [ ] Close mid-check doesn't crash
- [ ] Re-opening the wizard works cleanly after a prior run