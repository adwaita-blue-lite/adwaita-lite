# Setup Wizard Multi-Page Redesign

## Context

The setup wizard currently puts all fields on a single scrolling page, which is a poor experience on low-resolution Chromebook screens (typically 1366x768). The wizard needs to be split into 3 pages with navigation. Runs inside cage (kiosk Wayland compositor) at first boot, using GTK4 with custom Adwaita-inspired CSS (no libadwaita).

## Design

### Page Structure

**Page 1: Welcome + Account**
- Title: "Welcome to Adwaita-Lite"
- Subtitle: "Create your account to get started"
- Fields: Full Name, Username, Password, Confirm Password
- Button: **Next**

**Page 2: System Setup**
- Title: "System Setup"
- Fields: Timezone dropdown, Memory management dropdown (zram vs zswap), Swap size controls (visible only when zswap selected), Administrator checkbox (default on), Root password (optional)
- Buttons: **Back**, **Next**

**Page 3: Ready to Go**
- Title: "Ready to Go"
- Read-only summary: name, username, timezone, memory strategy (including swap size if zswap), admin status, root password status (set/not set)
- Buttons: **Back**, **Set Up** (primary action)
- Status/error display below the button

### Layout Hierarchy

```
Gtk.ApplicationWindow (default_size 800x600)
└── Gtk.Box (vertical, centered)
    ├── Step indicator ("Step 1 of 3" text label)
    ├── Gtk.Stack (crossfade transition)
    │   ├── Page 1 card (Gtk.Box with .card class)
    │   ├── Page 2 card (Gtk.Box with .card class)
    │   └── Page 3 card (Gtk.Box with .card class)
    ├── Status label (error/success messages)
    └── Button row (Gtk.Box, horizontal, end-aligned)
        ├── Back button (.back-button, flat style)
        └── Next/Set Up button (.create-button, filled primary)
```

The step indicator, status label, and button row are **outside** the stack — they stay fixed while card content fades. The button row's primary button label changes: "Next" on pages 1-2, "Set Up" on page 3. Back button is hidden on page 1.

Each page card is individually scrollable (`Gtk.ScrolledWindow` wrapping the card) to handle overflow on very small screens.

### Navigation

- `Gtk.Stack` with `CROSSFADE` transition
- Step indicator: text label "Step 1 of 3" / "Step 2 of 3" / "Step 3 of 3", `#aaaaaa` color
- Next validates current page before advancing; shows error in the status label
- Back never validates — always allowed
- On page transition, focus moves to the first input on the new page
- Enter key in the last field of a page triggers Next/Set Up

### Validation

- **Page 1 → 2**: Full name required, username valid (lowercase, starts with letter, ≤32 chars), password not empty, password matches confirmation
- **Page 2 → 3**: If zswap + custom size, must be positive integer. If admin unchecked and no root password, lockout warning
- **Page 3 submit**: No re-validation — reads field values and runs account creation in background thread (same logic as current)

### Summary Page Population

`_build_confirm_page()` creates empty `Gtk.Label` widgets for each summary item at init time. A separate `_populate_summary()` method is called from `_go_next()` when transitioning to page 3 — it reads current field values and updates the labels.

### User Groups

No changes needed:
- `video` (always) — brightness, graphics
- `wheel` (when admin checked) — sudo access
- Audio, bluetooth, USB, network, printing all handled by polkit + systemd-logind

### Styling

Custom CSS, no libadwaita. Adwaita-inspired:
- Colors: `#242424` bg, `#3584e4` primary, `#62a0ea` hover, `#ff6b6b` error, `#57e389` success
- Card: 480px wide, `border-radius: 16px`, padding 40px
- `.back-button`: transparent background, `#aaaaaa` text, no border. On hover: `#dddddd` text
- `.create-button`: filled `#3584e4`, white text (same as current)
- Step indicator: `font-size: 14px`, `#aaaaaa`, centered above card
- Summary labels: `.summary-value` class, `#ffffff` text, left-aligned

### File Changes

- `files/usr/bin/adwaita-lite-setup-wizard` — rewrite UI layout to multi-page; business logic (useradd, chpasswd, swap config, timezone) unchanged
