# Wizard in labwc Session — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the setup wizard as a fullscreen GTK4 app inside a labwc session managed by greetd, replacing the broken cage-from-systemd approach.

**Architecture:** greetd auto-logs in root via `initial_session` when no users exist (UID >= 1000). A dedicated wizard session script launches labwc with a `ADWAITA_LITE_WIZARD=1` flag. The autostart checks this flag and launches only the wizard (bare — no desktop daemons). VM hardware cursor fix applied to all session scripts.

**Tech Stack:** greetd, labwc, GTK4, bash, systemd-detect-virt

**Spec:** `docs/superpowers/specs/2026-04-01-wizard-labwc-session-design.md`

---

### Task 1: Create wizard session script

**Files:**
- Create: `files/usr/libexec/adwaita-lite-wizard-session`

- [ ] **Step 1: Create the wizard session script**

```bash
#!/bin/bash
# Wizard-mode labwc session — launched by greetd's initial_session on
# first boot (DD path) when no user accounts exist.  Sets the flag that
# tells autostart to launch only the setup wizard in a bare environment.

set -euo pipefail

export ADWAITA_LITE_WIZARD=1
export XDG_CURRENT_DESKTOP="labwc"
export XDG_SESSION_DESKTOP="labwc"
export XDG_SESSION_TYPE="wayland"

# Fix wlroots hardware cursor rendering upside-down / misplaced in VMs.
if systemd-detect-virt -q; then
    export WLR_NO_HARDWARE_CURSORS=1
fi

# GTK 4.16+ defaults to the Vulkan renderer.  VMs and older Intel GPUs
# (Bay Trail, Haswell) lack Vulkan support — force GL to avoid blank windows.
if command -v vulkaninfo >/dev/null 2>&1 && vulkaninfo --summary >/dev/null 2>&1; then
    : # Vulkan works, let GTK choose
else
    export GSK_RENDERER=gl
fi

exec labwc
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/libexec/adwaita-lite-wizard-session
git commit -m "feat: add wizard-mode labwc session script"
```

---

### Task 2: Update greeter-setup to detect users and configure wizard mode

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-greeter-setup`

- [ ] **Step 1: Rewrite greeter-setup with user detection**

Replace the entire file with:

```bash
#!/bin/bash
# Generate greetd config.  On the DD install path (no user accounts),
# include an initial_session that auto-logs in root to the wizard.
# On Anaconda installs (user already exists), go straight to the greeter.

set -euo pipefail

CONFIG="/etc/greetd/config.toml"

has_users=$(getent passwd \
  | awk -F: '$3 >= 1000 && $3 < 65534 { found=1; exit } END { print found+0 }')

if [ "$has_users" -eq 0 ]; then
    cat > "$CONFIG" <<EOF
[terminal]
vt = 7

[default_session]
command = "/usr/libexec/adwaita-lite-greeter-launch"
user = "greetd"

[initial_session]
command = "/usr/libexec/adwaita-lite-wizard-session"
user = "root"
EOF
else
    cat > "$CONFIG" <<EOF
[terminal]
vt = 7

[default_session]
command = "/usr/libexec/adwaita-lite-greeter-launch"
user = "greetd"
EOF
fi
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/libexec/adwaita-lite-greeter-setup
git commit -m "feat: greeter-setup detects users, adds wizard initial_session for DD path"
```

---

### Task 3: Update autostart to launch wizard in bare mode

**Files:**
- Modify: `files/etc/xdg/labwc/autostart`

- [ ] **Step 1: Add wizard-mode early exit at the top of autostart**

Insert the following block at line 1 (before the existing `#!/bin/sh`), replacing the shebang:

```sh
#!/bin/sh

# Wizard mode: launch only the setup wizard, skip all desktop daemons.
# Keeps RAM minimal on 2 GB Chromebooks that use the DD install path.
if [ "${ADWAITA_LITE_WIZARD:-}" = "1" ]; then
    /usr/bin/adwaita-lite-setup-wizard &
    exit 0
fi
```

The rest of the file (from `# Export Wayland environment to D-Bus...` onward) stays unchanged.

- [ ] **Step 2: Commit**

```bash
git add files/etc/xdg/labwc/autostart
git commit -m "feat: autostart launches wizard in bare mode when ADWAITA_LITE_WIZARD=1"
```

---

### Task 4: Make the wizard fullscreen itself

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` (line 314)

- [ ] **Step 1: Add self.fullscreen() to the wizard window constructor**

In `SetupWizardWindow.__init__`, after the `set_default_size` call, add `self.fullscreen()`:

Change line 314 from:

```python
        self.set_default_size(800, 600)
```

to:

```python
        self.set_default_size(800, 600)
        self.fullscreen()
```

The `set_default_size` is kept as a fallback if unfullscreen is ever called.

- [ ] **Step 2: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: wizard fullscreens itself (previously cage forced this)"
```

---

### Task 5: Add VM hardware cursor fix to normal session and greeter

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-session` (lines 1-13)
- Modify: `files/usr/libexec/adwaita-lite-greeter-launch` (line 27)

- [ ] **Step 1: Add VM cursor detection to the normal session script**

Replace the entire file with:

```bash
#!/bin/bash
set -euo pipefail

export ADWAITA_LITE=1
export XDG_CURRENT_DESKTOP="labwc"
export XDG_SESSION_DESKTOP="labwc"
export XDG_SESSION_TYPE="wayland"
export GTK_USE_PORTAL=1

# Fix wlroots hardware cursor rendering upside-down / misplaced in VMs.
if systemd-detect-virt -q; then
    export WLR_NO_HARDWARE_CURSORS=1
fi

# Write theme configs before the compositor starts (no Wayland socket needed).
/usr/libexec/adwaita-lite-apply-settings

exec labwc
```

- [ ] **Step 2: Update greeter-launch to conditionally set hardware cursor flag**

In `files/usr/libexec/adwaita-lite-greeter-launch`, change line 27 from:

```bash
env WLR_NO_HARDWARE_CURSORS=1 cage -s -- /usr/bin/adwaita-lite-greeter
```

to:

```bash
# Fix wlroots hardware cursor rendering upside-down / misplaced in VMs.
if systemd-detect-virt -q; then
    export WLR_NO_HARDWARE_CURSORS=1
fi

cage -s -- /usr/bin/adwaita-lite-greeter
```

This makes the hardware cursor fix conditional on VM detection rather than always-on (bare metal hardware cursors work fine).

- [ ] **Step 3: Commit**

```bash
git add files/usr/libexec/adwaita-lite-session files/usr/libexec/adwaita-lite-greeter-launch
git commit -m "fix: conditionally disable hardware cursors only in VMs"
```

---

### Task 6: Update build.sh — cleanup old cage service, add new script

**Files:**
- Modify: `build_files/build.sh`

- [ ] **Step 1: Replace wizard-launch chmod with wizard-session in the chmod block**

Change line 149:

```bash
    /usr/libexec/adwaita-lite-wizard-launch \
```

to:

```bash
    /usr/libexec/adwaita-lite-wizard-session \
```

- [ ] **Step 2: Remove the systemctl enable for the old first-boot service**

Delete line 158:

```bash
systemctl enable adwaita-lite-first-boot.service
```

- [ ] **Step 3: Commit**

```bash
git add build_files/build.sh
git commit -m "build: swap wizard-launch for wizard-session, drop first-boot service enable"
```

---

### Task 7: Delete obsolete files

**Files:**
- Delete: `files/etc/systemd/system/adwaita-lite-first-boot.service`
- Delete: `files/etc/pam.d/adwaita-lite-first-boot`
- Delete: `files/usr/libexec/adwaita-lite-wizard-launch`

- [ ] **Step 1: Remove the three obsolete files**

```bash
rm files/etc/systemd/system/adwaita-lite-first-boot.service
rm files/etc/pam.d/adwaita-lite-first-boot
rm files/usr/libexec/adwaita-lite-wizard-launch
```

- [ ] **Step 2: Commit**

```bash
git add -A files/etc/systemd/system/adwaita-lite-first-boot.service \
          files/etc/pam.d/adwaita-lite-first-boot \
          files/usr/libexec/adwaita-lite-wizard-launch
git commit -m "cleanup: remove cage-based wizard service, PAM config, and launcher"
```

---

### Task 8: Verify build

- [ ] **Step 1: Confirm no dangling references to removed files**

```bash
grep -r "adwaita-lite-first-boot" files/ build_files/
grep -r "adwaita-lite-wizard-launch" files/ build_files/
```

Expected: no output. If anything is found, update or remove it.

- [ ] **Step 2: Confirm wizard-session is referenced where needed**

```bash
grep -r "adwaita-lite-wizard-session" files/ build_files/
```

Expected: matches in `greeter-setup` and `build.sh` (chmod).

- [ ] **Step 3: Confirm autostart has the wizard-mode block**

```bash
head -7 files/etc/xdg/labwc/autostart
```

Expected: shebang followed by the `ADWAITA_LITE_WIZARD` check.
