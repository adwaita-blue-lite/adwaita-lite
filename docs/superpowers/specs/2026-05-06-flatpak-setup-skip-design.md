# First-Boot Flatpak Setup Skip Design

## Goal

Keep the first-boot default as "install selected Flatpaks before login," while giving users a clear, durable opt-out when their network is unreliable or they prefer to install apps manually later.

## User Experience

The greeter continues to show the existing `Finishing setup` overlay while `/var/lib/adwaita-lite/setup-done` exists and Flatpak setup has not completed.

Add a secondary `Skip app setup` action to that overlay. This action is available immediately, not only after a timeout or failure. The default path remains passive waiting: users who do nothing still get the current complete-before-login behavior.

When the user chooses to skip, show a confirmation prompt before applying the skip. The prompt must include this text:

`Selected apps will not be installed automatically. You can install them later with flatpak from the terminal.`

After confirmation, the greeter writes a durable skip marker and immediately reveals the login form.

## State Files

- `/var/lib/adwaita-lite/flatpak-setup.done`: initial Flatpak setup completed successfully.
- `/var/lib/adwaita-lite/flatpak-setup.skip`: user explicitly opted out of automatic initial Flatpak setup.
- `/run/adwaita-lite/flatpak-login-ready`: this boot may proceed to login after a temporary deferral, such as no network.
- `/run/adwaita-lite/flatpak-progress`: current human-readable setup status for the greeter overlay.

The skip marker is durable because the user intent should survive reboot. It is separate from the completion stamp so the system can distinguish "installed successfully" from "user opted out."

## Service Behavior

`adwaita-lite-flatpak-install.service` must not start when `/var/lib/adwaita-lite/flatpak-setup.skip` exists.

The script must also defensively exit early when the skip marker exists. This protects direct invocations and future unit changes from ignoring the user's opt-out.

The update service remains gated on `/var/lib/adwaita-lite/flatpak-setup.done`. Skipped systems must not run the every-boot update path until the initial automatic setup has actually completed. Users who opt out can manage Flatpaks manually with `flatpak`.

## Greeter Behavior

The greeter considers setup no longer blocking login when any of these is true:

- `/var/lib/adwaita-lite/flatpak-setup.done` exists.
- `/var/lib/adwaita-lite/flatpak-setup.skip` exists.
- `/run/adwaita-lite/flatpak-login-ready` exists.
- The existing overlay timeout expires.

The skip button writes `/var/lib/adwaita-lite/flatpak-setup.skip` with root privileges from the greeter process, then switches to the login card. The greeter must create `/var/lib/adwaita-lite` if needed, but in normal installs that directory already exists.

If writing the skip marker fails, the greeter must keep the setup overlay visible and show a short error message in the progress area. It must not silently reveal login if the durable opt-out was not recorded.

## Copy Rules

Do not mention Bazaar in this flow. Bazaar is one of the apps the automatic Flatpak setup may be installing, so users who skip cannot assume it is available out of the box.

Use `flatpak` as the manual install path in user-facing copy.

## Testing

Add contract tests for:

- The install service has `ConditionPathExists=!/var/lib/adwaita-lite/flatpak-setup.skip`.
- The setup script defines and honors the skip marker.
- The greeter defines the skip marker path and treats it as a non-blocking state.
- The greeter's skip copy mentions `flatpak` and does not mention Bazaar.

The existing Flatpak setup contract tests remain relevant and should continue to pass.

## Out Of Scope

- Building a graphical post-login Flatpak recovery UI.
- Automatically installing Bazaar by another mechanism.
- Changing the selected app defaults.
- Changing the 15-minute safety timeout.
- Running Flatpak installation in the background after an explicit skip.
