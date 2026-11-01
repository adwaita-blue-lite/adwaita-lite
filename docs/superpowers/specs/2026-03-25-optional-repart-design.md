# Optional Root Partition Expansion

**Date:** 2026-03-25
**Status:** Approved

## Overview

Make the automatic root partition expansion opt-in via the setup wizard instead of always-on at build time.

## Current Behavior

`systemd-repart.service` is enabled in `build_files/build.sh`. On first boot, it expands the root partition to fill all available disk space using the config in `files/etc/systemd/repart.d/10-root.conf` (`GrowFileSystem=yes`). Users who want to manage their own partition layout have no way to prevent this.

## New Behavior

The service is installed but **not enabled at build time**. The wizard's System page (Page 2) adds a checkbox:

- **Label:** "Expand root partition to fill disk"
- **Default:** Checked
- **Description text:** "Grows the root partition to use all available disk space on next boot."

When the user clicks "Set Up", `_step_configure_system` conditionally runs `systemctl enable systemd-repart.service` if the checkbox is checked. If unchecked, the service stays disabled and the partition remains at its build-time size (10 GiB).

## File Changes

| File | Change |
|------|--------|
| `build_files/build.sh` | Remove `systemctl enable systemd-repart.service` |
| `files/usr/bin/adwaita-lite-setup-wizard` | Add checkbox to System page, capture value in `_on_setup_clicked`, conditionally enable service in `_step_configure_system` |

The repart config files (`files/etc/systemd/repart.d/`) are unchanged -- they are inert without the service enabled.

**Anaconda ISO path:** Anaconda handles its own full-disk partitioning during install, so repart is unnecessary for ISO installs. The disabled-by-default state is correct for both install paths.

## Wizard Integration

**System page:** Add the checkbox after the "Root Password" field, before the end of the card. Uses the existing `.form-label` CSS class for consistency.

**Value capture:** `_on_setup_clicked` captures `self._setup_expand_root = self._expand_root_check.get_active()`.

**Step execution:** In `_step_configure_system`, after the swap configuration block:

```python
if self._setup_expand_root:
    try:
        subprocess.run(
            ["systemctl", "enable", "systemd-repart.service"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        return f"Failed to enable partition expansion: {exc.stderr.strip() or exc}"
```

**Confirm page:** Add a summary row showing "Yes" or "No" for partition expansion.
