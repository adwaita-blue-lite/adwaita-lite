# Settings app — Adwaita migration design

**Status:** Approved
**Date:** 2026-04-20
**Scope:** Convert the 16 pages of `adwaita-lite-settings` from hand-built `Gtk.Box` rows + custom CSS to the Adwaita preference patterns (`AdwPreferencesPage` / `AdwPreferencesGroup` / `Adw*Row`), with targeted UX improvements where libadwaita enables a genuinely better experience.

## Goals

- Pages look and behave like GNOME Settings: same row style, same hover / focus / selection states, same content-width clamping, same keyboard behaviour.
- Delete the parallel implementations we maintain today (`.setting-row`, `.boxed-list`, `.group-title`, `.toggle-card` CSS, plus `BasePage.make_*` widget factories).
- Cash in the UX wins libadwaita enables for free (status pages for empty states, banners for persistent warnings, navigation push for dialogs, expander rows for advanced sections, whole-row tappable switches for touch).
- Ship on 2GB Chromebook hardware without regressions in page correctness, D-Bus wiring, event-bus subscription lifecycles, or the store-save-and-apply mechanism that drives every setting.

## Non-goals

- Rewriting the sidebar / search / breakpoint infrastructure (already done in the prior libadwaita commit).
- Replacing pages' bespoke domain widgets (wallpaper grid, panel drag-drop layout editor, keyboard shortcut capture) with something Adwaita-only; those stay as-is, wrapped in an `AdwPreferencesGroup`.
- Rewriting settings-store or D-Bus helpers. Every page keeps its current `store.save_and_apply` / `store.save_debounced` / D-Bus subscription wiring.
- Adding tests. The app has no tests today and this migration does not introduce them (flagged as a separate concern).

## Architecture

### Class model (replaces `BasePage`)

```
BasePage (slimmed)                     Adw.PreferencesPage
    ├── search_keywords                    ├── add(AdwPreferencesGroup)
    ├── build() → Gtk.Widget               └── ...
    ├── subscribe(event, cb)
    ├── unsubscribe_all()
    └── setup_cleanup(widget)

        └── inherited by ──→ SettingsPage(BasePage, Adw.PreferencesPage)
                                  └── build() populates self and returns self
```

- `BasePage` loses every `make_*` widget factory (`make_page_box`, `make_group`, `make_setting_row`, `make_info_row`, `make_toggle_cards`). The five helpers above survive because they encode lifecycle contracts, not visual styling.
- `enable_escape_close` moves to `settings/utils.py` as a standalone function. It's a keyboard controller helper, not a page concern.
- Each page inherits from both `BasePage` and `Adw.PreferencesPage`. `build()` populates groups/rows via `self.add(group)` and returns `self`.
- Lazy build is preserved: `__init__` only stores refs, `build()` does the widget work on first navigation.

### Per-page UX recommendations

Strong defaults. Agents may push back with rationale and the controller decides.

#### Phase 0 — Pilot: `power_lock` (controller)

| Setting | Row type | Notes |
|---|---|---|
| `power_profile` | `AdwComboRow` | Options: Balanced / Power Saver / Performance |
| `lock_timeout` | `AdwSpinRow` | Minute units |
| `display_off_timeout` | `AdwSpinRow` | Minute units |
| `suspend_timeout` | `AdwSpinRow` | Minute units |
| `lid_close_action` | `AdwComboRow` | Suspend / Lock / Nothing |

Groups: *Power Profile*, *Automatic Suspend*, *Lid & Lock*.

#### Wave 1 — clean map (6 Sonnet agents, parallel)

**`mouse_touchpad`**
- Every `Gtk.Switch` → `AdwSwitchRow`.
- Pointer / scroll speed `Gtk.Scale` → `Gtk.Scale` as the suffix widget inside an `AdwActionRow` (Adw has no slider row; this is the canonical workaround — `set_size_request(200, -1)` + `set_draw_value(False)`).
- `accel_profile` toggle cards → `AdwComboRow` ("Adaptive / Flat").

**`accessibility`**
- All switches → `AdwSwitchRow`.
- Add an `AdwBanner` at the top of the page if high-contrast is active but the adw-gtk3 theme failed to apply. Current behaviour is silent failure.

**`datetime`**
- 24-hour clock → `AdwSwitchRow`.
- Timezone → `AdwActionRow` with `[go-next-symbolic]` suffix + push a searchable timezone list as an `AdwNavigationPage`. Current implementation is an in-page dropdown.

**`default_apps`**
- One `AdwComboRow` per default handler (Browser, File Manager, Terminal, Image Viewer), all in a single group.

**`language`**
- Current language → `AdwActionRow` with `[go-next-symbolic]` + push a language picker `AdwNavigationPage`. Current implementation is a 22-option dropdown.

**`sound`**
- Output / input device → `AdwComboRow` each.
- Volume / input level → `Gtk.Scale` in `AdwActionRow`.
- Mute → `AdwSwitchRow`.
- `AdwStatusPage` when no audio devices are found.

#### Wave 2 — mixed pages (4 Sonnet agents, parallel)

**`about`**
- System-info rows → `AdwActionRow` with the value in the subtitle.
- "Restore Defaults" → `AdwActionRow` with `.destructive-action` suffix button + push an `AdwNavigationPage` confirmation. Current is an inline dialog.

**`bluetooth`**
- Enabled → `AdwSwitchRow`.
- Device list → `AdwActionRow` per device (paired / connected state in subtitle, connect or disconnect action in suffix).
- `AdwBanner` at the top when Bluetooth is off.
- `AdwStatusPage` for the empty-during-scan state.

**`users`**
- User list → `AdwActionRow` per user with `AdwAvatar` in prefix.
- Group header-suffix "+" button to add a user.
- Edit user → push an `AdwNavigationPage` (was a modal dialog).

**`appearance`**
- Theme → `AdwSwitchRow` ("Dark mode").
- Accent picker → custom widget stays, wrapped in `AdwPreferencesGroup("Accent color")`.
- Wallpaper grid → custom widget stays, wrapped in `AdwPreferencesGroup("Wallpaper")`.
- Font size → `AdwComboRow` ("Small / Default / Large / Larger").

#### Wave 3 — heavy custom (4 Opus agents, parallel)

**`display`**
- Scale → `AdwComboRow` (100% / 125% / 150% / 200%). Agent may push back in favour of toggle-cards if a card layout is better for a touchpad Chromebook; defaults to ComboRow.
- Per-display resolution → `AdwComboRow` inside `AdwExpanderRow` per display (expanded by default if there are ≥ 2 displays).
- Night Light: `AdwSwitchRow` (enabled) + temperature `Gtk.Scale` in `AdwActionRow` + schedule `AdwComboRow`.
- Custom schedule → `AdwExpanderRow` with two `AdwActionRow`s using 24h time suffix labels. Agent decides: inline entry widgets vs. time-picker navigation push.
- Revert dialog → `AdwAlertDialog`.
- "Open wdisplays" → `AdwActionRow` with `[go-next-symbolic]` suffix.
- `AdwStatusPage` when no displays are detected.

**`network`**
- WiFi enabled → `AdwSwitchRow`.
- Network list → `AdwActionRow` per network, signal-strength icon in prefix, connection state in subtitle.
- Password entry → push an `AdwNavigationPage` (was a modal dialog).
- `AdwBanner` when the adapter is down or airplane mode is on.
- `AdwStatusPage` for "No networks found" mid-scan and for "No WiFi adapter".

**`panel`**
- Drag-drop layout editor → stays custom, wrapped in `AdwPreferencesGroup("Layout")`.
- Pinned apps list → `AdwActionRow` per pinned app with drag handle + remove button suffix.
- Group header-suffix "+" to add a pinned app.
- Behaviour settings (edge, density) → `AdwComboRow`.

**`keyboard`**
- Keyboard layout → `AdwComboRow` with `use_subtitle=True` (shows layout + variant).
- Repeat delay / repeat rate → `AdwSpinRow`.
- Shortcut list → `AdwActionRow` per shortcut with the keybinding in suffix; tap a row pushes a capture `AdwNavigationPage` (was a modal dialog).
- Caps Lock behavior → `AdwComboRow`.

### Conventions every page follows

- `search_keywords` stays as-is. The sidebar's per-page filter matches on those; Adw rows have their own search but the scope is wrong (per-page, not sidebar-scope).
- Pages inherit from `Adw.PreferencesPage`. `__init__` is cheap; `build()` populates groups/rows lazily on first show and returns `self`.
- Omit empty-string subtitles (rows auto-hide subtitle space); do not pass `""`.
- `Gtk.Scale` in `AdwActionRow` is the canonical slider workaround: `set_size_request(200, -1)` + `set_draw_value(False)`.
- Every signal handler and D-Bus subscription from the pre-migration version is preserved exactly. Reviewer subagents verify.

## Agent dispatch model

Uses `superpowers:subagent-driven-development`. For each wave:

1. Controller dispatches an implementer subagent per page with:
    - The pilot file (`power_lock.py`) as reference.
    - The target page's current code.
    - The per-page recommendations from this spec.
    - Explicit permission to push back on a recommendation with rationale — "these are strong defaults, not commandments."
2. The implementer subagent writes the conversion, runs a smoke check (Python syntax + `import settings.pages.<page>`), commits, reports status.
3. Spec-compliance reviewer subagent verifies work matches the spec (row types, UX touches) or flags deviations.
4. Code-quality reviewer subagent verifies signal wiring, store calls, event-bus subscriptions, imports are all clean.
5. Controller handles any disagreement: acks the alternative or insists on the original. Each implementer commit is a clean single-file change.

Parallel-within-wave is safe because each agent edits exactly one page file. Phase 0's infrastructure commit lands before any agent launches, so no shared file is touched concurrently.

## Phase sequencing

| Phase | Work | Commits | Parallel agents |
|---|---|---|---|
| 0 | Infrastructure: slim BasePage, extract utils, convert pilot `power_lock` | 1 | 0 (controller only) |
| 1 | Wave 1: 6 clean-map pages | 6 | 6 Sonnet |
| 2 | Wave 2: 4 mixed pages | 4 | 4 Sonnet |
| 3 | Wave 3: 4 heavy-custom pages | 4 | 4 Opus |
| 4 | Cleanup: dead CSS classes, unused imports | 1 | 0 (controller only) |

Sequential between phases. Each phase gets its own implementation plan via `superpowers:writing-plans`.

## Risks

- **Slider-in-row ergonomics.** `Gtk.Scale` as an `AdwActionRow` suffix can eat too much width in narrow layouts. Mitigation: agent verifies at 360px window width; we can add a CSS rule to cap the slider's max width if it misbehaves.
- **Navigation-push mental model.** Pushing dialogs to sub-pages changes "I'm in a modal" to "I'm on a sub-page". Revert is easy per page if a specific flow feels worse.
- **Event-bus / D-Bus wiring regressions.** The biggest correctness risk. The code-quality reviewer subagent's primary job is to verify `subscribe` / `unsubscribe_all` / `setup_cleanup` / store save/apply / D-Bus helper calls are all preserved in every page.
- **Opus-level judgment pages.** `display`, `network`, `panel`, `keyboard` have internal state that survives widget rebuilds. Opus handles these specifically because the conversion has to preserve state wiring that Sonnet might break.
- **No test coverage.** The app has no automated tests. Validation is manual: after each wave lands, user opens settings, tabs through every converted page, exercises at least one control per page, confirms the setting actually applies.

## Open questions

None at spec approval time. The plan skills will surface specific row-type or layout questions per wave.

## Success criteria

- All 16 pages inherit from `Adw.PreferencesPage`.
- `BasePage.make_*` widget factories are gone.
- All `.setting-row` / `.boxed-list` / `.group-title` / `.toggle-card` / `.setting-subtitle` CSS rules deleted.
- Every page's settings still apply on user input (manual verification per page).
- Settings app opens and navigates between pages at 360×300 minimum window size without clipping.
- Settings app opens and navigates between pages at 1366×768 (Chromebook native) without ballooning.
- Sidebar search still filters categories by page keywords.
