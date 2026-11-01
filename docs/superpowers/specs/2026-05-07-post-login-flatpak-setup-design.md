# Post-Login Flatpak Setup Design

## Goal

Replace fragile first-boot Flatpak installation with a reliable post-login app setup experience that matches Adwaita Lite's Adwaita-inspired and ChromeOS-inspired design language.

## Problem

Installing Flatpaks before login depends on first-boot systemd ordering, VM networking, DNS, Flathub availability, Flatpak remote setup, and greeter coordination. Repeated VM boots have shown this path is not reliable enough for onboarding. A failed pre-login install makes the system feel broken even when the desktop itself is usable.

## User Experience

After the user logs in for the first time, Adwaita Lite shows a centered welcome card over the desktop.

Title:

`Set up your apps`

Subtitle:

`Install the apps you selected during setup. You can keep using the desktop while this runs.`

Primary action:

`Install apps`

Secondary action:

`Not now`

Low-emphasis opt-out:

`Don't ask again`

The UI must not call this "first boot". To users, it is app setup.

## Visual Design Requirements

The card must fit the current Adwaita Lite visual system:

- Adwaita-style rounded card with subtle border or elevation.
- Shared Adwaita Lite palette tokens and dark/light theme behavior.
- Typography hierarchy consistent with the greeter and Settings surfaces.
- Centered card, not full-screen, with a maximum width around 420-480 px.
- Text wraps safely on small laptop displays.
- No terminal-like logs in the primary UI.
- Progress uses calm Adwaita-style status treatment: spinner or progress bar plus compact status text.
- Error states use warning/error styling with plain-language copy and retry actions.
- `Install apps` is the suggested/accent action.
- `Not now` is neutral.
- `Don't ask again` is low-emphasis text/destructive-adjacent, not a scary red button.

The look should feel like a ChromeOS welcome/OOBE card adapted to GTK/Adwaita, not like a package manager window.

## States

### Ready

Shown when selected apps exist and neither the done stamp nor skip stamp exists.

Content includes:

- Title and subtitle.
- Optional app preview list limited to a small number of friendly names.
- Network status line: `Connected` or `Waiting for network...`.
- Actions: `Install apps`, `Not now`, `Don't ask again`.

### Installing

Shown after the user chooses `Install apps`.

Content includes:

- Title: `Installing apps`.
- Status text such as `Installing 2 of 4: Bazaar`.
- Spinner or progress bar.
- Action: `Run in background`.

The user can keep using the desktop while installation continues.

### No Network

Shown when installation cannot start because network is unavailable.

Copy:

`No network connection`

`Connect to Wi-Fi or Ethernet, then try again.`

Actions: `Try again`, `Not now`.

### Partial Failure

Shown when one or more selected apps fail to install.

Copy:

`Some apps couldn't be installed`

The detail area lists failed friendly names or app IDs.

Actions: `Retry failed apps`, `Close`.

### Complete

Shown when every selected app is installed.

Copy:

`Apps installed`

`Your selected apps are ready to use.`

Action: `Done`.

## Persistence And State Files

Continue using these existing state files:

- `/var/lib/adwaita-lite/flatpak-apps`: selected app IDs written by the wizard or ISO seed.
- `/var/lib/adwaita-lite/flatpak-setup.done`: app setup completed successfully.
- `/var/lib/adwaita-lite/flatpak-setup.skip`: user chose `Don't ask again`.

`Not now` does not write either durable stamp. The prompt can return on the next login.

`Don't ask again` writes the skip stamp and prevents future prompts.

Successful completion writes the done stamp.

## Control Flow

The desktop session starts normally. Flatpak setup must not block greetd, labwc, or login.

At session startup, a small first-run app setup component checks:

- App list exists and is non-empty.
- Done stamp does not exist.
- Skip stamp does not exist.

If those conditions hold, it shows the centered card.

When installation starts, it should install the selected app IDs using the existing system Flatpak behavior where possible. The install path should be idempotent and skip already-installed refs.

The first-run card owns the user-visible progress. Background systemd logs are not the primary UX.

## Error Handling

- No network: show the no-network state and allow retry.
- Flathub remote setup failure: show a plain error and allow retry later.
- Individual app failure: continue attempting remaining apps, then show partial failure.
- User closes/runs in background: keep install running if already started, but do not block the session.
- User chooses `Don't ask again`: stop prompting and do not run automatic installs.

## Non-Goals

- No pre-login Flatpak installation gate.
- No claim that apps are ready before first login.
- No Bazaar-specific recovery path; Bazaar may itself be one of the selected apps.
- No terminal-like package logs in the main UI.
- No full package-manager replacement.

## Testing

Automated tests should cover:

- Prompt appears only when app list exists, done stamp absent, and skip stamp absent.
- `Not now` leaves durable state unchanged.
- `Don't ask again` writes skip stamp.
- Successful install writes done stamp.
- Empty app list does not prompt.
- Already-installed refs are skipped.
- Partial failures are reported without marking done.
- UI copy includes `flatpak` only where manual terminal install is intended and does not promise Bazaar is available.
- CSS/static tests enforce Adwaita-style card constraints: bounded width, rounded card, accent primary action, neutral secondary action, and no terminal log block in the main card.

Manual verification after image rebuild:

- Boot a VM and log in without waiting for Flatpak setup.
- Confirm the centered card appears after login.
- Confirm `Install apps`, `Not now`, and `Don't ask again` behave as specified.
- Test no-network behavior in a VM with networking disabled.
- Test successful install on a networked VM.

## Acceptance Criteria

- First login is not blocked by Flatpak installation.
- The app setup prompt visually fits the existing Adwaita/ChromeOS-inspired Adwaita Lite UI.
- Users can install now, defer, or opt out permanently.
- Failures are visible and retryable.
- The system no longer depends on live Flathub installs during the pre-login boot path.
