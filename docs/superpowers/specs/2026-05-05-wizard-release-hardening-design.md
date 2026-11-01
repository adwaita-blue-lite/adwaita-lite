# Wizard Release Hardening Design

Date: 2026-05-05

## Context

The installer wizard recently failed in a VM with a blank labwc screen and cursor. The compositor was running, but `/tmp/wizard-crash.log` showed the wizard crashed during account-page construction because `Gtk.PasswordEntry` did not expose `set_activates_default()` in the shipped runtime. That crash is fixed, but the follow-up audit found additional release-risk issues around GTK API drift, GLib source lifecycle handling, startup coverage, and installer-state recovery.

Current documentation consulted:

- `docs.gtk.org` GTK 4 `Gtk.PasswordEntry`, `Gtk.MessageDialog`, `Gtk.AlertDialog`, `Gtk.Accessible.announce`, `Gtk.AccessibleProperty`, `Gtk.DropDown`, `Gtk.ScrolledWindow`, and `Gtk.StyleContext` pages.
- `api.pygobject.gnome.org` PyGObject GObject property and GLib/PyGObject threading guidance.
- `docs.gtk.org/glib` `GLib.Source.remove` and main-loop source lifecycle documentation.

## Goal

Make a release-safe hardening pass over `files/usr/bin/adwaita-lite-setup-wizard` that fixes concrete runtime hazards and adds regression coverage without taking on a large startup architecture refactor immediately before release.

## Non-Goals

- Do not redesign the wizard UX.
- Do not split the 4k-line wizard into modules in this pass.
- Do not perform the full lazy/asynchronous page-construction refactor unless the targeted fixes and smoke coverage still show startup blank-screen risk.
- Do not force GTK Vulkan or change renderer policy for wizard/greeter.

## Findings To Address

1. Stale GLib source ID risk: `_rescan_timer_id` is not cleared when the rescan cooldown timeout removes itself, so later `GLib.source_remove()` could target a reused source ID.

2. Install button can become inert: `_on_setup_clicked()` sets `_installing = True` before password hashing; if hashing fails, the handler returns without clearing `_installing`.

3. Accessibility live-region code is inert: `_mark_live_assertive()` references `Gtk.AccessibleProperty.LIVE` and `Gtk.AccessibleLive.ASSERTIVE`, which are not current GTK 4 APIs. Current GTK provides `Gtk.Accessible.announce()` since 4.14.

4. Deprecated close warning dialog: `_on_close_request()` uses `Gtk.MessageDialog`, deprecated since GTK 4.10. Current GTK recommends `Gtk.AlertDialog` for alerts.

5. Test coverage gap: current wizard tests mainly cover pure helpers or fake GTK namespaces. They do not prove the real GTK startup/page-construction path avoids known missing/deprecated APIs.

6. Startup responsiveness risk: the wizard builds all pages before `win.present()`, including some synchronous probes. This remains a known architectural risk, but the release-safe pass should first add coverage and fix concrete hazards before attempting a larger lazy-loading refactor.

## Design

### GLib Source Lifecycle

Update `_enable_rescan()` so it resets `_rescan_timer_id` before returning `GLib.SOURCE_REMOVE`. This keeps the stored source ID valid only while the timeout is actually installed. Add a focused unit test for this behavior, either by directly invoking the method on a minimal `SetupWizardWindow.__new__()` instance or with static coverage if real GLib is unavailable.

### Install State Recovery

Move `_installing = True` until after preflight password hashing succeeds, or clear it on every early failure path before returning. The preferred implementation is to set `_installing` only once all synchronous preflight reads/hashes have succeeded and the progress flow is ready to start. Add a test that simulates `_hash_password()` failure and verifies a second install attempt is not blocked by stale `_installing`.

### Accessibility Announcements

Replace the inert live-region helper with a current helper that announces important status messages through `Gtk.Accessible.announce()` when available. Keep graceful fallback for older GTK builds or environments without accessibility support. The helper should not crash if `announce` or `Gtk.AccessibleAnnouncementPriority` is absent.

Use the helper from `_set_status()` or the central status-update path rather than scattering announcements across every caller. Use medium priority for validation/status messages and reserve high priority for critical install failures if needed.

### Alert Dialog Modernization

Replace the install-in-progress `Gtk.MessageDialog` with `Gtk.AlertDialog` when available. Because `Gtk.AlertDialog` is available since GTK 4.10, include a small compatibility fallback to a lightweight transient `Gtk.Window` or the existing `Gtk.MessageDialog` only if the runtime lacks `Gtk.AlertDialog`. The normal supported path should be the current API.

Add a test that rejects direct unconditional `Gtk.MessageDialog` use in the wizard. If a fallback remains, make the test require the fallback to be guarded by `hasattr(Gtk, "AlertDialog")` or a wrapper helper.

### GTK Compatibility Coverage

Extend static compatibility tests to catch known release-risk API patterns:

- `Gtk.PasswordEntry.set_activates_default()` should remain disallowed.
- Unconditional `Gtk.MessageDialog` use should be disallowed.
- `Gtk.AccessibleProperty.LIVE` and `Gtk.AccessibleLive` should be disallowed.
- `Gtk.DropDown.set_search_match_mode()` is allowed because current docs show it since GTK 4.12, which is within Fedora 43+ targets.
- `Gtk.ScrolledWindow.set_max_content_height()` is allowed by current GTK docs.
- `Gtk.StyleContext.add_provider_for_display()` may remain for now because the type function remains documented even though the class is deprecated; do not churn this unless a safe current replacement exists in PyGObject.

Add the best feasible real-GTK smoke test without destructive system changes. The target is to catch startup/page-construction crashes like the `PasswordEntry` issue. If the CI/runtime lacks a display or GTK typelib, the test may skip with a clear reason. It should not run disk partitioning or install steps.

### Startup Responsiveness

Do not refactor startup page construction in this pass. Instead:

- Document the risk in this spec.
- Ensure smoke coverage exercises the current startup path enough to catch immediate crashes.
- Revisit lazy page construction only if smoke tests or VM testing still show blank-screen startup after the concrete fixes.

## Testing Plan

Run these checks after implementation:

- New focused regression tests for rescan timer cleanup, install preflight failure recovery, accessibility API denylist, and alert dialog modernization.
- Wizard-related tests: `pytest -q tests/test_setup_wizard_app_selection.py tests/test_installer_mount_handling.py tests/test_wizard_i18n.py`.
- Full suite: `pytest -q`.
- Syntax check: `python -m py_compile files/usr/bin/adwaita-lite-setup-wizard`.
- Manual VM check after rebuild: boot the raw image, confirm the wizard window appears, navigate through language/account/system pages, and verify `/tmp/wizard-crash.log` remains empty or contains only non-fatal portal warnings.

## Release Criteria

- No known startup-crashing GTK API calls remain in the wizard.
- Deprecated `Gtk.MessageDialog` is not used on the normal supported path.
- Stale GLib source IDs are not retained after one-shot timeout callbacks remove themselves.
- Install preflight failures leave the wizard interactive and retryable.
- The regression suite catches the API class that caused the VM blank screen.
