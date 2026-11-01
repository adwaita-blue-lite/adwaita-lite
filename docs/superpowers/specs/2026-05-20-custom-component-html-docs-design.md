# Custom Component HTML Documentation Design

## Context

Adwaita-Lite has substantial custom UI code across the setup wizard, settings app, app menu, greeter, and shared theming layer. Existing documentation is useful but uneven for future contributors and agents:

- `README.md` is a user-facing project overview.
- `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md` is the closest thing to a component pattern library, but it is specific to the settings app's libadwaita migration.
- There are no existing `.html` documentation pages.
- The largest bespoke UI surface is `files/usr/bin/adwaita-lite-setup-wizard` at roughly 4.7k lines.
- Other custom UI surfaces include `adwaita-lite-app-menu`, `adwaita-lite-greeter`, settings pages such as `appearance`, `panel`, `keyboard`, `display`, and `network`, plus shared palette/CSS behavior.

The goal is to document custom components for future contributors and agents, not end users. HTML is preferred over Markdown because each component area can use whichever presentation best communicates its structure: flow diagrams, annotated layouts, state tables, styling maps, or dense source-linked cards.

Visual quality and information density are first-class requirements. These pages should not look like plain exported Markdown; each page should use HTML deliberately to make relationships, ownership, flow, and safe-edit guidance faster to scan.

## Goal

Create contributor/agent-oriented static HTML documentation for Adwaita-Lite custom components. The work should proceed area-first, starting with the setup wizard, but the implementation is not complete until all known custom component areas have HTML documentation.

The setup wizard page should prove the documentation format early. The same implementation effort should then continue through the remaining custom UI areas so the final result is a complete component documentation set, not just a starter index.

## Non-Goals

- Ship the docs inside the OS image.
- Add docs to the runtime applications or UI.
- Build a generated documentation system.
- Define a rigid visual template before inspecting each component's information shape.
- Accept low-density, plain-prose pages when tables, diagrams, cards, or annotated blocks would communicate the component better.
- Replace existing design specs, implementation plans, or user-facing README content.

## Recommended Approach

Use an area-first, template-light rollout.

Start with `adwaita-lite-setup-wizard` because it has the highest concentration of bespoke UI: multi-page flow, card layout, custom dark CSS, language and keyboard selection, network rows, disk and memory-management controls, app rows, confirmation, progress, log display, install state, validation, and skip behavior.

The setup wizard doc should establish only minimal shared conventions. Future pages should not be forced into the wizard's layout; each HTML page should be shaped around the component being documented.

## Documentation Structure

Add a new documentation area:

```text
docs/components/
  index.html
  setup-wizard.html
```

Additional pages should include:

```text
docs/components/app-menu.html
docs/components/greeter.html
docs/components/settings.html
docs/components/theme-system.html
```

`index.html` should be a contributor/agent landing page. It should list every known custom component area, link to completed docs, and make coverage status visible while the work is in progress. At the end of implementation, all known custom component areas should link to completed pages.

`setup-wizard.html` should be the first complete deep page.

## Setup Wizard Page Content

The setup wizard doc should help a contributor or agent safely locate and edit wizard UI without rereading all of `adwaita-lite-setup-wizard` first.

It should include:

- Source reference: `files/usr/bin/adwaita-lite-setup-wizard`.
- Purpose: USB installer wizard launched in the live environment when no user accounts exist.
- Flow map: language, network, disk, account, system setup, apps, summary/confirmation, progress.
- Component map: card shell, step indicator, status label, navigation buttons, form entries, dark list rows, Wi-Fi rows, keyboard panel, disk/memory controls, app rows, confirmation acknowledgement, progress controls, details/log view.
- State/data hooks: install config fields, page validation, skip behavior, async install execution, network state, selected apps, selected disk/filesystem/memory strategy.
- Styling map: CSS classes and the UI elements that own them, including `card`, `welcome-title`, `welcome-subtitle`, `form-entry`, `form-label`, `form-description`, `dark-list`, `wifi-row`, `wifi-ssid`, `wifi-detail`, `wifi-connected`, `keyboard-toggle`, `keyboard-panel`, `setting-row`, `app-row`, `app-name`, `app-description`, `warning-label`, `status-label`, `status-error`, `back-button`, `create-button`, `details-toggle`, and `log-view`.
- Safe-edit guidance: preserve translation markers, validation, async subprocess behavior, atomic writes, install flow ordering, low-memory safeguards, and accessibility labels/tooltips where present.
- Relevant tests: link to existing tests that cover wizard behavior, smoke construction, i18n, app selection, installer mount handling, ISO install contract, and Flatpak setup contracts where applicable.

The page should avoid duplicating large source blocks. Short snippets are acceptable only when they clarify ownership or flow.

## Shared HTML Conventions

Use hand-authored static HTML. Keep infrastructure minimal:

- Inline CSS per page is acceptable in the first pass.
- Avoid JavaScript unless the page genuinely benefits from interaction.
- Use relative links between docs pages.
- Prefer dense, scannable sections over prose-heavy explanations.
- Use visual hierarchy deliberately: compact tables, grouped cards, flow strips, callouts, and annotated maps where they improve comprehension.
- Reference exact source paths and major classes/functions.
- Let each component page choose its own visual structure.

The only shared content expectations are:

- Title.
- Source file references.
- Purpose.
- Component map.
- Behavior/state notes.
- Styling notes.
- Accessibility/i18n notes.
- Safe-edit guidance for future contributors and agents.

Every page should include at least one content-specific visual structure beyond headings and paragraphs. Examples include a flow strip for the setup wizard, layout/model cards for the app menu, an IPC/state map for the greeter, custom-surface tables for settings, and token relationship maps for the theme system.

## Coverage Plan

Implementation order:

1. Create `docs/components/index.html`.
2. Create `docs/components/setup-wizard.html`.
3. Use the setup wizard page to validate the adaptive, template-light HTML approach.
4. Create `docs/components/app-menu.html`.
5. Create `docs/components/greeter.html`.
6. Create `docs/components/settings.html`.
7. Create `docs/components/theme-system.html`.
8. Update `index.html` so every known custom component area is marked documented and linked.

The non-wizard pages should cover:

- App menu: layer-shell behavior, sizing modes, app model, search/filtering, grid/tile rendering, frequent apps, power confirmation, twilight theming.
- Greeter: kiosk login layout, theme/accent loading, session selector, greetd IPC flow, login/error states.
- Settings: Adw page structure plus custom surfaces such as wallpaper tiles, accent swatches, panel layout editor, pinned apps picker, keyboard shortcut capture, network sub-pages, display revert dialogs, and page-specific CSS.
- Theme system: shared palette data, generated CSS, GTK/Waybar/greeter/app-menu relationships, accent behavior, dark/light/twilight conventions.

## Testing And Verification

This is documentation-only work.

Verification should include:

- Confirm `docs/components/index.html` links to every component page.
- Confirm every component page links back to `index.html`.
- Confirm referenced source paths exist.
- Confirm the setup wizard page covers the major page builders and CSS classes currently present in `adwaita-lite-setup-wizard`.
- Confirm the app menu, greeter, settings, and theme-system pages cover their major custom component surfaces at a comparable source-navigation level.
- Confirm each page uses an HTML structure that improves scan speed or visual understanding for that component area, rather than merely wrapping Markdown-like prose in HTML.
- If an existing HTML checker is available, use it. Do not introduce a new dependency solely for this first documentation pass.

## Risks And Mitigations

- Risk: HTML pages drift from source. Mitigation: include exact source paths/functions and make coverage status visible in `index.html`.
- Risk: a rigid template blocks useful visualization. Mitigation: keep only minimal shared conventions; allow each page to choose tables, diagrams, annotated blocks, or cards.
- Risk: first page becomes too large. Mitigation: focus on navigation, ownership, state, styling, and safe edits rather than exhaustive source explanation.
- Risk: future agents miss undocumented areas. Mitigation: list all known custom component areas in the index throughout the implementation and finish with every listed area linked to a completed page.
