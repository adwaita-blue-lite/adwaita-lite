# Chrome Early-OOM Safety Valve Design

## Context

Adwaita-Lite targets low-memory Chromebooks where Chrome is a required project goal. On 2 GB zram-only systems, forcing Chrome into heavy memory pressure can leave an unresponsive Chrome surface even after `systemd-oomd` frees memory.

Recent investigation showed:

- `systemd-oomd` correctly killed one `app-flatpak-com.google.Chrome-*.scope` after swap exceeded the configured threshold.
- The Chrome Flatpak scope drop-in applied and exposed `OOMPolicy=kill`.
- Chrome had another active Flatpak scope that kept the hung window alive.
- Manually running `systemctl --user kill --kill-who=all <remaining Chrome scope>` removed the unresponsive surface.

The current `OnFailure=` cleanup hook is useful defense-in-depth, but it only runs after a Chrome scope has already failed. A better primary path is to close Chrome before the system reaches the crashy OOMD zone.

## Goal

Preserve desktop responsiveness on 2 GB systems by proactively closing Chrome Flatpak scopes when memory and swap are both critically low.

## Non-Goals

- Replace Chrome as the default browser.
- Disable `systemd-oomd`.
- Build a generic app killer for all desktop applications.
- Preserve Chrome tabs at all costs under extreme memory pressure.

## Approach

Add a Adwaita-Lite-specific early-OOM monitor rather than using stock `earlyoom`.

Stock `earlyoom` kills individual processes based on kernel OOM scoring. The observed failure is scope-level: Chrome may have multiple Flatpak scopes, and killing only one process or one scope can leave a hung browser surface. Adwaita-Lite needs an action that understands the Flatpak/systemd unit boundary and can close all active Chrome Flatpak scopes for the logged-in user.

## Components

### Early-OOM Monitor Service

Install a small system service that runs continuously with minimal overhead. It reads `/proc/meminfo` every 2 seconds and evaluates `MemAvailable` and `SwapFree`.

The monitor should trigger only when both conditions are true for consecutive samples:

- `MemAvailable < 200 MiB`
- `SwapFree < 300 MiB`

Requiring consecutive samples avoids killing Chrome on a single transient spike. After a kill, the monitor should enter a cooldown, initially 60 seconds, to avoid repeated actions while the desktop recovers.

### Chrome Scope Cleanup

When the threshold trips, the monitor should find logged-in users with active Chrome Flatpak scopes and kill all active or activating units matching:

```text
app-flatpak-com.google.Chrome-*.scope
```

The kill action should be equivalent to the manual recovery command that removed the hung surface:

```sh
systemctl --user kill --kill-who=all app-flatpak-com.google.Chrome-*.scope
```

From a system service, the implementation should invoke the matching user's systemd user manager rather than killing PIDs directly. The preferred implementation is `systemctl --user --machine=<uid>@ ...` if available in the image; if VM testing shows that is unavailable, use the smallest supported per-user invocation that still targets user units and is covered by tests.

### OOMD Fallback

Keep `systemd-oomd` enabled and keep the Chrome `OnFailure=` sibling cleanup hook. The new early-OOM monitor is the preferred Chrome-specific path, while OOMD remains the general fallback if the monitor misses a condition or another app causes pressure.

Because Chrome gets a targeted earlier safety valve, relax OOMD memory-pressure behavior slightly while keeping swap protection firm:

- Keep `SwapUsedLimit=80%`.
- Change `DefaultMemoryPressureLimit` from `50%` to `55%`.
- Change `DefaultMemoryPressureDurationSec` from `20s` to `25s`.
- Keep the existing `ManagedOOM` opt-ins enabled and align the explicit user-session `ManagedOOMMemoryPressureLimit` to `55%` so the runtime fallback matches the global policy.

This keeps OOMD earlier than Fedora's upstream defaults but reduces unnecessary non-Chrome app kills now that Chrome is handled before the broad fallback.

## Data Flow

1. Monitor reads `/proc/meminfo`.
2. Monitor converts `MemAvailable` and `SwapFree` to MiB.
3. If both values remain below threshold for two consecutive samples, monitor enumerates logged-in users.
4. For each user, monitor lists active Chrome Flatpak scopes through that user's systemd user manager.
5. Monitor kills all active or activating Chrome Flatpak scopes for that user.
6. Monitor logs the memory state, user, and killed scope names.
7. Monitor waits through cooldown before it can trigger again.
8. If memory pressure continues after Chrome closes, OOMD uses the relaxed `80%` swap and `55%/25s` pressure thresholds as the broad fallback.

## Error Handling

- Missing `/proc/meminfo` fields should be logged and treated as non-triggering.
- Failed user-manager queries should be logged and skipped for that sample.
- Failed scope kills should be logged, but other matching scopes and users should still be attempted.
- If no Chrome scopes exist, the monitor should take no action.

## Testing

- Unit test threshold parsing and decision logic with fake `meminfo` data.
- Unit test consecutive-sample behavior and cooldown behavior.
- Unit test scope enumeration and kill command generation with fake `systemctl` output.
- Config test that the monitor service is installed and enabled by the image build.
- Config test that OOMD keeps `SwapUsedLimit=80%` and uses the relaxed `DefaultMemoryPressureLimit=55%`, `ManagedOOMMemoryPressureLimit=55%`, and `DefaultMemoryPressureDurationSec=25s` fallback thresholds.
- Keep existing OOMD tests for `OOMPolicy=kill` and the `OnFailure=` fallback cleanup.

## Trade-Offs

This intentionally sacrifices Chrome earlier than `systemd-oomd` would. That is acceptable for the 2 GB public-preview target because closing Chrome is better than leaving the session wedged. The design is Chrome-specific by choice: Chrome is a project goal and the app proven to create this failure mode. Relaxing OOMD memory pressure from `50%/20s` to `55%/25s` slightly favors keeping non-Chrome applications alive, while the unchanged `80%` swap threshold preserves the last-resort zram exhaustion guardrail.

## Implementation Notes

- Prefer a simple shell or Python monitor with no new runtime dependency beyond the base image.
- Keep thresholds as constants in one place so they are easy to tune after VM testing.
- The implementation should avoid broad process matching such as killing every `chrome` PID directly; scope-level cleanup is the verified recovery action.
