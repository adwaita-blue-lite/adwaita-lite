# Installer Locale Selection — Design Spec

## Problem

The installer hardcodes `LANG=en_US.UTF-8`.  A user who doesn't read English
cannot navigate the wizard.  The image ships 22 langpacks but never asks which
language to use.

## Solution

Add a Language page as the very first page of the installer (Page 0).  The
user picks their language, the wizard immediately re-renders all UI text in
that language, and the selected locale is written to the installed system.

This is a UI + config feature only — it does not change the install pipeline,
first-boot service, or sysroot configuration logic (beyond writing the correct
locale to `locale.conf`).

## Page 0 — Language

### Layout

Scrollable list of the 22 shipped languages.  Each row shows:

- **Native name** (bold, left-aligned) — always in the language's own script
- **Translated name** (dimmer, right-aligned) — in the *currently selected*
  language

Default selection: English, highlighted.  English stays in the list like any
other language — it is not privileged in the UI.

Example with English selected:

    **English**                                English
    **Deutsch**                                German
    **日本語**                                  Japanese
    **العربية**                                Arabic
    **Português**                              Portuguese

After selecting Japanese:

    **English**                                英語
    **Deutsch**                                ドイツ語
    **日本語**                                  日本語
    **العربية**                                アラビア語
    **Português**                              ポルトガル語

### Regional Variants

Languages with meaningful regional variants expand on selection (same animated
expand pattern as the WiFi password rows).  The most common variant is
pre-selected; the user can tap a different one or just proceed.

Languages with only one practical variant select directly with no expansion.

| Langpack | Native Name    | Default Locale   | Variants (expand)                                      |
|----------|---------------|------------------|--------------------------------------------------------|
| am       | አማርኛ           | am_ET.UTF-8      | —                                                      |
| ar       | العربية         | ar_EG.UTF-8      | ar_SA, ar_MA, ar_DZ, ar_TN, ar_IQ, ar_JO, ar_LB, ar_SY |
| de       | Deutsch        | de_DE.UTF-8      | de_AT, de_CH                                           |
| en       | English        | en_US.UTF-8      | en_GB, en_AU, en_CA                                    |
| es       | Español        | es_ES.UTF-8      | es_MX, es_AR, es_CO, es_CL, es_PE                     |
| fa       | فارسی           | fa_IR.UTF-8      | —                                                      |
| fr       | Français       | fr_FR.UTF-8      | fr_CA, fr_BE, fr_CH                                    |
| ha       | Hausa          | ha_NG.UTF-8      | —                                                      |
| hi       | हिन्दी           | hi_IN.UTF-8      | —                                                      |
| it       | Italiano       | it_IT.UTF-8      | —                                                      |
| ja       | 日本語          | ja_JP.UTF-8      | —                                                      |
| ko       | 한국어          | ko_KR.UTF-8      | —                                                      |
| nl       | Nederlands     | nl_NL.UTF-8      | nl_BE                                                  |
| pl       | Polski         | pl_PL.UTF-8      | —                                                      |
| pt       | Português      | pt_BR.UTF-8      | pt_PT                                                  |
| ru       | Русский        | ru_RU.UTF-8      | —                                                      |
| sv       | Svenska        | sv_SE.UTF-8      | —                                                      |
| sw       | Kiswahili      | sw_KE.UTF-8      | sw_TZ                                                  |
| th       | ไทย            | th_TH.UTF-8      | —                                                      |
| tr       | Türkçe         | tr_TR.UTF-8      | —                                                      |
| vi       | Tiếng Việt     | vi_VN.UTF-8      | —                                                      |
| yo       | Yorùbá         | yo_NG.UTF-8      | —                                                      |
| zh       | 中文            | zh_CN.UTF-8      | zh_TW, zh_HK                                           |

For zh, the expanded variants should display as 简体中文 (Simplified) and
繁體中文 (Traditional) / 繁體中文 (Hong Kong) rather than raw locale codes.
Similarly, pt variants display as Português (Brasil) / Português (Portugal).

### Interaction

1. User taps a language row
2. If the language has variants: row animates open showing variant sub-rows
   with the default pre-selected.  If no variants: selects directly.
3. The wizard immediately re-renders all visible text in the new language
   (page title, subtitle, button labels, the translated-name column in the
   list, and the step indicator)
4. The Next button advances to Page 1 (Network)

### What It Writes

During `_step_configure_user()`, the selected locale (e.g., `pt_BR.UTF-8`) is
written to `{sysroot}/etc/locale.conf` as `LANG=<locale>`.  This replaces the
current hardcoded `en_US.UTF-8`.

## Translation Infrastructure

### gettext Integration

All user-facing strings in the wizard are wrapped in `gettext.gettext()`
(aliased as `_()`).  This covers:

- Page titles and subtitles
- Form labels ("Full Name", "Username", "Password", etc.)
- Button labels ("Next", "Back", "Install", "Reboot")
- Status and error messages
- Summary labels and values
- Progress step labels
- Dropdown option text (swap strategies, filesystem names)

### Translation Files

- `po/adwaita-lite-setup-wizard.pot` — source template extracted from Python
  source via `xgettext`
- `po/<lang>.po` — one per language, containing translated strings
- Compiled `.mo` files installed to
  `/usr/share/locale/<lang>/LC_MESSAGES/adwaita-lite-setup-wizard.mo`

The `.po` files are generated via AI translation (Claude for high/medium
confidence languages, web-assisted tools for Amharic, Hausa, Swahili, Yoruba).
Community review is sought for the low-confidence languages.

### Runtime Language Switching

When the user selects a language:

1. `gettext.translation('adwaita-lite-setup-wizard', languages=[lang]).install()`
   sets the active translation catalog
2. A `_retranslate()` method on `SetupWizardWindow` re-sets every widget's
   text by re-calling `_()` on the original English string
3. The language list itself re-renders its translated-name column

The `_retranslate()` method iterates all translatable widgets stored as
instance attributes (already the case — `self._fullname_entry`,
`self._status_label`, etc.) and re-applies their text.  Labels that are
created but not stored as instance attributes need to be stored for
retranslation.

### Language Name Matrix

A data structure maps each language to its name in every other language:

```python
LANGUAGE_NAMES = {
    "en": {"en": "English", "de": "Englisch", "ja": "英語", ...},
    "de": {"en": "German", "de": "Deutsch", "ja": "ドイツ語", ...},
    ...
}
```

This is a 22×22 matrix (~484 entries).  It lives in a separate data file
(`po/language-names.json` or a Python dict in the wizard) to keep the main
wizard code clean.  Language names are well-standardized strings that every
translation service handles well.

## Page Flow Update

The wizard becomes 8 pages:

| Page | Name     | Notes                                    |
|------|----------|------------------------------------------|
| 0    | Language | New — always shown, never skipped        |
| 1    | Network  | Existing — auto-skipped if online        |
| 2    | Disk     | Target drive, filesystem, memory mgmt    |
| 3    | Account  | Name, username, password                 |
| 4    | System   | Timezone, admin, root password           |
| 5    | Apps     | Flatpak selection                        |
| 6    | Confirm  | Summary                                  |
| 7    | Progress | Install execution                        |

Page constants shift: `PAGE_LANGUAGE = 0`, `PAGE_NETWORK = 1`, etc.

## What Stays the Same

- Install pipeline (bootc, sysroot writes, Flatpak rsync)
- First-boot service
- Encrypted swap architecture
- All existing page UI (just wrapped in `_()`)
- Same CSS, same visual style
- Same greetd/labwc session management

## What Changes

- Every user-facing string wrapped in `_()`
- New Language page (Page 0)
- `locale.conf` writes the user's selected locale instead of hardcoded en_US
- Page constants shift by 1 (again)
- New translation files (.pot, .po, .mo) in build
- Labels that aren't currently stored as instance attributes get stored for
  `_retranslate()`

## Out of Scope

- Layering langpacks not shipped on the USB image (future feature — first-boot
  service could detect and layer via bootc)
- Keyboard layout selection (could pair with language but is a separate concern)
- Right-to-left (RTL) layout for Arabic/Farsi/Hebrew — GTK4 handles RTL
  automatically based on locale direction, so this should work out of the box
  but is not explicitly designed or tested here
