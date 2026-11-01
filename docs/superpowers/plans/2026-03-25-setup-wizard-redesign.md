# Setup Wizard Multi-Page Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the setup wizard from a single scrolling page to a 3-page wizard with navigation, keeping all business logic unchanged.

**Architecture:** Single file rewrite of `files/usr/bin/adwaita-lite-setup-wizard`. The UI is restructured around a `Gtk.Stack` with 3 page cards. Step indicator, status label, and button row live outside the stack so they stay fixed during transitions. Business logic (useradd, chpasswd, swap config, timezone) is preserved verbatim.

**Tech Stack:** Python 3, GTK4 (gi.repository), no libadwaita

**Spec:** `docs/superpowers/specs/2026-03-25-setup-wizard-redesign.md`

---

### Task 1: Rewrite the setup wizard

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

This is a single-task rewrite since it's one file with tightly coupled UI code. The business logic functions are preserved exactly.

- [ ] **Step 1: Write the complete rewritten wizard**

Replace the entire file content. The new structure:

1. **CSS**: Update stylesheet — add `.back-button`, `.step-indicator`, `.summary-row`, `.summary-value` classes. Remove `.separator`, `.section-header` (no longer needed). Keep all existing form classes.

2. **Constants**: Keep `USERNAME_RE`, `SWAP_STRATEGIES`, `SWAP_SIZES`, `_load_timezones()` unchanged.

3. **`SetupWizardWindow.__init__`**: Build the outer layout:
   - `set_default_size(800, 600)` (down from 750)
   - Outer vertical box (centered, with margins)
   - Step indicator label (`"Step 1 of 3"`, `.step-indicator` class)
   - `Gtk.Stack` with `CROSSFADE` transition (200ms)
   - Status label (shared across pages, below stack)
   - Button row: Back (`.back-button`, hidden on page 1) + Next/Set Up (`.create-button`)

4. **`_build_account_page()`**: Returns a `Gtk.ScrolledWindow` wrapping a `.card` box containing:
   - Title: "Welcome to Adwaita-Lite"
   - Subtitle: "Create your account to get started"
   - Full Name entry, Username entry, Password entry, Confirm Password entry
   - Connect Enter on confirm_entry to `_go_next()`

5. **`_build_system_page()`**: Returns a `Gtk.ScrolledWindow` wrapping a `.card` box containing:
   - Title: "System Setup"
   - Timezone dropdown, Memory management dropdown
   - Swap size controls (conditional visibility — same logic as current)
   - Administrator checkbox, Root password entry
   - Connect Enter on root_password_entry to `_go_next()`

6. **`_build_confirm_page()`**: Returns a `Gtk.ScrolledWindow` wrapping a `.card` box containing:
   - Title: "Ready to Go"
   - Summary rows (label + value pairs): Name, Username, Timezone, Memory, Admin, Root password (set/not set)
   - Summary labels stored as `self._summary_*` for later population

7. **`_populate_summary()`**: Called from `_go_next()` when transitioning to page 3. Reads all field values and updates `self._summary_*` labels.

8. **`_go_next()`**: Validates current page, advances stack. Page tracking via `self._current_page` (0/1/2). Updates step indicator text, button label ("Next" vs "Set Up"), back button visibility.

9. **`_go_back()`**: Decrements page, updates stack/indicator/buttons. Clears status. No validation.

10. **`_validate_page(page_index)`**: Split validation:
    - Page 0: fullname, username, password, confirm
    - Page 1: swap config, admin/root lockout check

11. **`_on_setup_clicked()`**: Same as current `_on_create_clicked()` — reads all fields, runs `_create_account()` in background thread. No re-validation.

12. **Business logic**: `_create_account()`, `_on_done()`, `_reboot()` — copy verbatim from current implementation.

13. **`SetupWizardApp`** and **`main()`** — unchanged.

- [ ] **Step 2: Verify the file is syntactically valid**

Run: `python3 -c "import py_compile; py_compile.compile('files/usr/bin/adwaita-lite-setup-wizard', doraise=True)"`
Expected: No output (success)

- [ ] **Step 3: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: redesign setup wizard as 3-page flow

Split the single scrolling form into three pages:
  Page 1: Account creation (name, username, password)
  Page 2: System setup (timezone, memory, admin/root)
  Page 3: Summary and confirmation

Uses Gtk.Stack with crossfade transitions, step indicator,
and Back/Next navigation. Business logic unchanged."
```

### Task 2: Commit spec and plan docs

- [ ] **Step 1: Commit documentation**

```bash
git add docs/superpowers/
git commit -m "docs: add setup wizard redesign spec and plan"
```

### Task 3: Push and verify CI

- [ ] **Step 1: Push to remote**

```bash
git push
```

- [ ] **Step 2: Verify CI starts building**

Check that the container image build workflow triggers.
