# Release Translation Audit and Start Menu i18n Design

## Goal

Prepare Adwaita-Lite for release by improving first-run usability for
non-English users. The work updates existing wizard and settings/greeter
translations, adds translation coverage for the start menu, and verifies that
all shipped gettext catalogs build cleanly.

## Current State

Adwaita-Lite already ships gettext catalogs for 22 non-English locale codes:

`am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh`

Existing gettext domains:

- `adwaita-lite-setup-wizard`: source files in `po/*.po`, template at
  `po/adwaita-lite-setup-wizard.pot`, compiled catalogs under
  `files/usr/share/locale/<lang>/LC_MESSAGES/adwaita-lite-setup-wizard.mo`.
- `adwaita-lite-settings`: source files in `po/settings/*.po`, template at
  `po/settings/adwaita-lite-settings.pot`, compiled catalogs under
  `files/usr/share/locale/<lang>/LC_MESSAGES/adwaita-lite-settings.mo`.

The greeter intentionally shares the `adwaita-lite-settings` domain.

The start menu at `files/usr/bin/adwaita-lite-app-menu` currently has
hardcoded English shell UI strings and is not included in `po/Makefile`.
Installed application names and generic names are read from `Gio.AppInfo`; those
should continue to rely on each application's translated `.desktop` metadata
where available.

## Scope

In scope:

- Audit and update existing wizard translations.
- Audit and update existing settings/greeter translations.
- Add a separate start menu gettext domain named `adwaita-lite-app-menu`.
- Translate the start menu's own shell UI strings.
- Compile and verify all gettext catalogs.
- Preserve placeholders, punctuation that affects behavior, and gettext syntax.

Out of scope:

- Human-quality localization review by native speakers.
- Translating third-party application names outside their `.desktop` metadata.
- Adding new supported locale codes.
- Reworking the language picker matrix beyond validation and incidental fixes.

## Architecture

Add a new gettext domain for the start menu instead of reusing the settings
domain. This keeps catalog ownership clear:

- Wizard strings remain in `adwaita-lite-setup-wizard`.
- Settings and greeter strings remain in `adwaita-lite-settings`.
- Start menu shell strings move into `adwaita-lite-app-menu`.

The start menu will initialize gettext near the top of
`files/usr/bin/adwaita-lite-app-menu`, bind `adwaita-lite-app-menu` to
`/usr/share/locale`, and alias gettext as `_`. User-visible string literals in
the start menu shell UI will be wrapped in `_()`.

`po/Makefile` will gain an app-menu section with:

- `APP_MENU_DOMAIN = adwaita-lite-app-menu`
- `APP_MENU_SOURCE = ../files/usr/bin/adwaita-lite-app-menu`
- `APP_MENU_POT = app-menu/$(APP_MENU_DOMAIN).pot`
- `APP_MENU_PO = $(LANGUAGES:%=app-menu/%.po)`
- `APP_MENU_MO = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(APP_MENU_DOMAIN).mo)`

Combined targets `pot`, `po`, `mo`, and `all` will include app-menu targets.

## Start Menu Strings

Translate the start menu's own shell UI, including:

- Category and filter labels: `All Apps`, `Accessories`, `Development`, `Games`,
  `Graphics`, `Internet`, `Multimedia`, `Settings`, `System`, `Other`.
- Search/filter affordances: `Search apps…`, `Search apps`,
  `Filter by category`, `Frequent`.
- Power actions: `Lock`, `Log Out`, `Restart`, `Shut Down`.
- Confirmation UI: `Cancel`, `Confirm`, `Log out now?`,
  `Restart the computer?`, `Shut down the computer?`.
- Accessible labels that include placeholders, such as `Launch {app}`.

Use gettext-friendly formatting for placeholder strings, for example
`_("Launch {app}").format(app=item.accessible_name)`. Translators must preserve
placeholder names exactly.

Use the Unicode ellipsis in UI strings where the existing UI uses it. The source
currently uses `Search apps…`; the POT should preserve that exact text unless an
implementation pass deliberately normalizes it.

## Orchestration

Use a coordinator-plus-language-subagents model.

The coordinator owns shared structure and final verification:

- Baseline audit of POT freshness, PO status, fuzzy/untranslated/obsolete counts,
  and current `msgfmt` validity.
- Source changes for start menu gettext wiring.
- `po/Makefile` updates.
- POT regeneration and initial PO merge.
- Canonical terminology guidance for subagents.
- Integration review of all language changes.
- Final `make` and test verification.

Language subagents own non-overlapping locale files only. Each subagent may edit
only these paths for its assigned languages:

- `po/<lang>.po`
- `po/settings/<lang>.po`
- `po/app-menu/<lang>.po`

Suggested groups:

- Group A: `de es fr it nl pt sv`
- Group B: `pl ru tr`
- Group C: `ja ko zh`
- Group D: `ar fa hi`
- Group E: `am ha sw yo`
- Group F: `th vi`

Subagents must prioritize first-run clarity over literary polish. They should
avoid broad rewrites unless a string is wrong, awkward enough to harm setup, or
inconsistent with nearby terminology.

## Translation Rules

All agents must follow these rules:

- Preserve every `msgid` exactly.
- Preserve placeholder names exactly, including braces such as `{username}` and
  `{app}`.
- Preserve escape sequences and line breaks.
- Do not translate command names, paths, environment variables, package names,
  or project names unless they are clearly descriptive UI labels.
- Keep product name `Adwaita-Lite` unchanged.
- Keep technical terms understandable for first-run users; prefer common UI terms
  over literal technical jargon.
- Do not mark entries fuzzy as a substitute for deciding on a translation.
- Do not edit `.mo` files by hand; regenerate them from PO files.

Core terminology should be consistent within each language across wizard,
settings, greeter, and start menu for:

- Settings
- Apps
- Install
- Password
- Back
- Next
- Restart
- Shut Down
- Log Out
- Search
- Language

## Data Flow

1. Coordinator regenerates POT templates from source.
2. Coordinator merges POT changes into PO files with `msgmerge --update` through
   `po/Makefile` targets.
3. Language subagents update their assigned PO files.
4. Coordinator compiles `.mo` files with `make mo` or `make all` in `po/`.
5. Runtime applications load compiled catalogs from `/usr/share/locale`.

## Error Handling

Translation validation must catch:

- Syntax errors in PO files.
- Broken placeholders.
- Missing app-menu catalogs for supported languages.
- Fuzzy or untranslated entries left after the release pass.
- Accidental edits to unassigned locale files.

If a translation is uncertain, prefer a simple, understandable translation over
leaving the entry empty. If no safe translation can be produced, leave a clear
coordinator note rather than silently shipping an empty string.

## Verification

Coordinator verification should include:

- `make all` from `po/`.
- Per-file `msgfmt --check --statistics --output-file=/dev/null` for wizard,
  settings, and app-menu PO files.
- A check for fuzzy and untranslated entries in all shipped PO files.
- `python -m pytest tests/test_language_names.py tests/test_wizard_i18n.py tests/test_app_menu_css.py`.
- Spot-check that compiled `.mo` files exist for all 22 languages and all three
  domains.

If start menu tests need to be extended, add a focused test that verifies the
source is wired into gettext extraction and the expected app-menu POT strings are
present after extraction.

## Release Acceptance Criteria

The release translation pass is complete when:

- The start menu has its own gettext domain and compiled catalogs for all 22
  supported non-English languages.
- Wizard, settings/greeter, and app-menu PO files have no syntax errors.
- No release-shipped PO file has fuzzy or untranslated entries.
- Placeholders compile and are preserved across translations.
- The targeted i18n and app-menu tests pass.
- Any remaining concerns are documented as human localization review follow-ups,
  not hidden in the build output.
