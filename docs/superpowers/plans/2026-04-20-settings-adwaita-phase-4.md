# Settings Adwaita Migration — Phase 4 Cleanup Plan

> **For agentic workers:** Single-commit controller-run task. No subagent dispatch — the whole phase is mechanical deletion confirmed by prior-phase grep audits. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove the scaffolding left behind by Phases 0–3. Every `BasePage.make_*` widget factory is now unreferenced; several CSS classes and one standalone helper module are orphans. Delete them and ship a noticeably smaller, simpler settings package.

**Architecture:** One atomic commit on `main` — this is the terminal phase of the migration. No code changes to any page file; only the shared modules (`base.py`, `css/style.css`, `utils.py`, optionally `window.py`) are touched.

**Tech stack:** Python 3.13, GTK 4, libadwaita.

**References:**
- Design: `docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md`
- Phases 0–3 plans (for context on what migrated where).

## Dead-code audit (run as part of Task 1)

All audits below were sampled while writing this plan. Agents/controllers executing the plan should re-run them to confirm nothing has changed since.

```bash
# Zero callers of the 5 widget factories:
grep -rnE 'self\.make_(page_box|group|setting_row|info_row|toggle_cards)' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
# Expected: no output

# Zero callers of BasePage.enable_escape_close:
grep -rn 'BasePage\.enable_escape_close' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
# Expected: no output

# Zero importers of settings.utils:
grep -rn 'from .*utils import\|settings\.utils' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
# Expected: no output (enable_escape_close is standalone but no one calls it -
# all pages replaced Gtk.Window with AdwAlertDialog / nav-push)
```

## File plan

| File | Change | Purpose |
|---|---|---|
| `files/usr/lib/adwaita-lite/settings/base.py` | Slim | Remove the 5 dead widget factory staticmethods + the dead `enable_escape_close` staticmethod. What's left: the `BasePage.__init__` store/event_bus wiring, `search_keywords` property, `build()` abstract, `subscribe`, `unsubscribe_all`, `setup_cleanup` — the pure page-protocol contract. |
| `files/usr/lib/adwaita-lite/settings/utils.py` | **Delete** | Zero importers. We added this file in Phase 0 to host `enable_escape_close` — but every page that would have needed it has since migrated to Adwaita-native dismissal (AdwAlertDialog handles Escape natively, AdwNavigationView handles back-button/Escape on sub-pages). A 20-line helper with no callers is noise; if we need standalone helpers later a new module is trivial to create. |
| `files/usr/lib/adwaita-lite/settings/css/style.css` | Trim | Delete rules whose classes now have zero callers: `.content-page`, `.setting-row`, `.toggle-card`, `.boxed-list`. The `.setting-subtitle` class keeps one caller in `window.py`'s error-fallback label; drop that one caller (just use a plain `Gtk.Label` without the class) and delete the rule. The `.group-title` class keeps one caller in `panel.py`'s bespoke module-layout editor section headers — keep the rule for that. Every `accent-*`, `wallpaper-*`, `category-*`, `content-area`, `dialog-*` (dialog-* already deleted in wave 2) stays or stays-deleted as noted. |
| `files/usr/lib/adwaita-lite/settings/window.py` | Touch-up | Drop the single `widget.add_css_class("setting-subtitle")` in the failed-to-load fallback (Task 3). Outer `Gtk.ScrolledWindow` wrapping the page stack is **kept** — it enables scroll-position reset on page switch via `_content_scroll.get_vadjustment().set_value(0)`, which AdwPreferencesPage doesn't expose a simple equivalent for. Not a Phase 4 regression. |

---

## Task 1: Re-audit and confirm the dead list

**Files:**
- None modified. Verification only.

- [ ] **Step 1: Re-run the three audits from the "Dead-code audit" section above**

Commands:
```bash
cd /var/home/race/ublue-mike

grep -rnE 'self\.make_(page_box|group|setting_row|info_row|toggle_cards)' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
# Expected: (empty)

grep -rn 'BasePage\.enable_escape_close' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
# Expected: (empty)

grep -rn 'from .*utils import\|settings\.utils' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
# Expected: (empty)
```

If ANY of these produce output, STOP. A page missed the migration. Do not proceed with Phase 4 until the miss is identified and the page's migration finishes (or the deletion target is narrowed).

- [ ] **Step 2: Audit CSS classes to confirm the "dead" list**

```bash
for cls in 'content-page' 'setting-row' 'toggle-card' 'boxed-list'; do
    count=$(grep -rnE "add_css_class\(\"$cls\"\)" \
        files/usr/lib/adwaita-lite/settings/ 2>/dev/null \
        | grep -v pycache | grep -v base.py | wc -l)
    printf "%-20s non-base.py callers: %d\n" "$cls" "$count"
done
```

Expected output:
```
content-page         non-base.py callers: 0
setting-row          non-base.py callers: 0
toggle-card          non-base.py callers: 0
boxed-list           non-base.py callers: 0
```

(`.setting-row` may show 1 caller in `window.py`'s error fallback; we clean that up in Task 3 before removing the rule. If there are OTHER callers outside base.py / window.py, STOP and investigate.)

---

## Task 2: Slim `base.py`

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/base.py`

- [ ] **Step 1: Replace `base.py` with the slim version**

Full replacement content:

```python
from gettext import gettext as _

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: F401 - kept so subclasses can still import Gtk symbols via `from ..base import Gtk` if any do

from .events import EventBus
from .settings_store import SettingsStore


class BasePage:
    """Minimal shared protocol every settings page implements.

    This used to be the home for a pile of Gtk widget factory
    staticmethods (make_page_box, make_group, make_setting_row,
    make_info_row, make_toggle_cards) that each page pulled from
    to build its hand-rolled Gtk.Box layouts. After the libadwaita
    migration (Phases 0-3), every page inherits from Adw.Preferences
    Page and builds its UI from native Adw.*Row widgets, so the
    factories have no callers. Phase 4 dropped them along with the
    enable_escape_close dialog helper (no Gtk.Window dialogs remain
    in any page - everything is AdwAlertDialog or AdwNavigationView
    push).
    """

    def __init__(self, store: SettingsStore, event_bus: EventBus) -> None:
        self.store = store
        self.event_bus = event_bus
        self._subscriptions: list[tuple[str, object]] = []

    @property
    def search_keywords(self) -> list[tuple[str, str]]:
        return []

    def build(self) -> Gtk.Widget:
        raise NotImplementedError

    def refresh(self) -> None:
        pass

    def subscribe(self, event: str, callback) -> None:
        """Subscribe to an event and track it for cleanup on unmap."""
        self.event_bus.subscribe(event, callback)
        self._subscriptions.append((event, callback))

    def unsubscribe_all(self) -> None:
        """Unsubscribe every tracked callback."""
        for event, callback in self._subscriptions:
            self.event_bus.unsubscribe(event, callback)
        self._subscriptions.clear()

    def setup_cleanup(self, widget: Gtk.Widget) -> None:
        """Connect the widget's unmap signal to unsubscribe_all.

        Call this from build() on whichever widget actually leaves
        the visible tree when the user navigates away from the page
        - for most pages that's self (the PreferencesPage); for pages
        wrapped in an AdwNavigationView, it's self._nav, because the
        PreferencesPage itself unmaps when sub-pages are pushed.
        """
        widget.connect("unmap", lambda _: self.unsubscribe_all())
```

- [ ] **Step 2: Syntax-check**

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/base.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify the file shrunk and protocol is intact**

```bash
wc -l files/usr/lib/adwaita-lite/settings/base.py
# Expected: ~50 (down from 161)

grep -cE 'def (subscribe|unsubscribe_all|setup_cleanup|build|refresh|__init__)' \
    files/usr/lib/adwaita-lite/settings/base.py
# Expected: 6

grep -cE 'def (make_|enable_escape_close)' \
    files/usr/lib/adwaita-lite/settings/base.py
# Expected: 0
```

- [ ] **Step 4: Stage**

```bash
git add files/usr/lib/adwaita-lite/settings/base.py
```

Do NOT commit yet. Phase 4 commits atomically at the end of Task 5.

---

## Task 3: Prune dead CSS + window.py touch-up

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/css/style.css`
- Modify: `files/usr/lib/adwaita-lite/settings/window.py`

- [ ] **Step 1: Read the current `style.css` to identify the dead rules**

Run:
```bash
grep -nE '^\.(content-page|setting-row|setting-subtitle|toggle-card|boxed-list)\b' \
    files/usr/lib/adwaita-lite/settings/css/style.css
```

Expected output lists each class as a CSS selector (one per dead rule). Note the line numbers — you'll be deleting the rule blocks (from the selector line through the closing `}`).

- [ ] **Step 2: Delete the dead CSS rule blocks**

Open `files/usr/lib/adwaita-lite/settings/css/style.css` and remove the complete rule blocks for each of:

- `.content-page { … }`
- `.setting-row { … }` (if present — may already have been dropped mid-migration; no-op if so)
- `.setting-subtitle { … }`
- `.toggle-card { … }`
- `.boxed-list { … }`

Leave `.group-title`, `.accent-*`, `.wallpaper-*`, `.category-icon`, `.category-label`, `.content-area` rules alone — they still have live callers (panel's bespoke editor, appearance's accent picker, appearance's wallpaper grid, window.py's sidebar, window.py's outer scrolled).

- [ ] **Step 3: Drop the `setting-subtitle` class usage from `window.py`**

The only remaining caller of `.setting-subtitle` was the failed-to-load fallback label. Since we've deleted the CSS rule, drop the class application — the plain Gtk.Label renders fine with default theme styling.

Edit `files/usr/lib/adwaita-lite/settings/window.py` around the `_ensure_page_built` method. Find the fallback widget construction (it constructs a Gtk.Label("Failed to load {label}") and adds the class). Remove just the `widget.add_css_class("setting-subtitle")` line.

- [ ] **Step 4: Re-run the CSS audit to verify cleanup is complete**

```bash
for cls in 'content-page' 'setting-row' 'setting-subtitle' 'toggle-card' 'boxed-list'; do
    class_count=$(grep -rnE "add_css_class\(\"$cls\"\)" \
        files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache | wc -l)
    rule_count=$(grep -nE "^\.$cls\b" \
        files/usr/lib/adwaita-lite/settings/css/style.css | wc -l)
    printf "%-20s callers: %d  rules: %d\n" "$cls" "$class_count" "$rule_count"
done
```

Expected:
```
content-page         callers: 0  rules: 0
setting-row          callers: 0  rules: 0
setting-subtitle     callers: 0  rules: 0
toggle-card          callers: 0  rules: 0
boxed-list           callers: 0  rules: 0
```

If any line has callers > 0 or rules > 0, the edit missed something. Fix before proceeding.

- [ ] **Step 5: Stage**

```bash
git add files/usr/lib/adwaita-lite/settings/css/style.css \
        files/usr/lib/adwaita-lite/settings/window.py
```

---

## Task 4: Delete `settings/utils.py`

**Files:**
- Delete: `files/usr/lib/adwaita-lite/settings/utils.py`

- [ ] **Step 1: Final audit — confirm zero importers**

```bash
grep -rn 'from .*utils import\|settings\.utils\|from settings\.utils' \
    files/usr/lib/adwaita-lite/settings/ 2>/dev/null | grep -v pycache
```

Expected: empty.

If any line shows up, STOP. A page still needs the helper; either keep the file or migrate that page to an Adwaita-native dismissal path first.

- [ ] **Step 2: Delete the file**

```bash
git rm files/usr/lib/adwaita-lite/settings/utils.py
```

- [ ] **Step 3: Clean up the adjacent `__pycache__` stale entry if present**

```bash
rm -f files/usr/lib/adwaita-lite/settings/__pycache__/utils.cpython-*.pyc
```

(The build regenerates pycaches, but removing this one locally prevents confusion during review.)

---

## Task 5: Atomic Phase 4 commit

**Files:**
- None modified. Commit only.

- [ ] **Step 1: Confirm staged changes**

```bash
git diff --cached --name-status
```

Expected output:
```
M   files/usr/lib/adwaita-lite/settings/base.py
M   files/usr/lib/adwaita-lite/settings/css/style.css
M   files/usr/lib/adwaita-lite/settings/window.py
D   files/usr/lib/adwaita-lite/settings/utils.py
```

If anything else is staged, unstage it with `git reset HEAD <path>` before committing.

- [ ] **Step 2: Syntax + import smoke check on the modified Python files**

```bash
python3 -c "
import ast
for p in [
    'files/usr/lib/adwaita-lite/settings/base.py',
    'files/usr/lib/adwaita-lite/settings/window.py',
]:
    ast.parse(open(p).read())
    print(f'{p}: OK')
"
```

Expected: both `OK`.

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(settings): Phase 4 cleanup — drop dead BasePage factories + CSS

Final sweep of the libadwaita migration. Every settings page now
inherits from Adw.PreferencesPage (Phases 0-3); the hand-rolled
Gtk.Box factories that BasePage used to host for them are orphan
code, as are the CSS rules that styled those layouts and a
standalone Gtk.Window dismissal helper whose last caller was
removed when wave-3 landed AdwAlertDialog + AdwNavigationView
pushes.

Removes:

  - BasePage.make_page_box / make_group / make_setting_row /
    make_info_row / make_toggle_cards  (5 widget factories, 0
    callers)
  - BasePage.enable_escape_close          (0 callers — all
    Gtk.Window dialogs replaced with Adw alternatives)
  - settings/utils.py                      (0 importers — the
    standalone enable_escape_close helper lost its purpose
    with wave 3)
  - CSS rules: .content-page, .setting-row, .setting-subtitle,
    .toggle-card, .boxed-list  (0 callers after the base.py slim)
  - window.py: the `.setting-subtitle` class on the failed-to-
    load fallback label (the rule above was deleted)

Keeps (still referenced):

  - BasePage protocol: __init__, search_keywords, build, refresh,
    subscribe, unsubscribe_all, setup_cleanup
  - CSS: .group-title (panel's module-layout editor section
    headers), .accent-* (appearance's accent picker), .wallpaper-*
    (appearance's wallpaper grid), .category-icon / .category-label
    (window.py sidebar rows), .content-area (window.py outer
    scrolled window)

Brings base.py from 161 lines to ~50, the CSS file from 192 lines
to smaller, and ends the migration. Settings app surface is now
fully Adwaita-native: Adw.Application, Adw.ApplicationWindow,
Adw.NavigationSplitView, AdwToastOverlay, Adw.PreferencesPage on
every page, Adw.AlertDialog for every confirmation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Push**

```bash
git push
```

Expected: push completes, commit visible on `origin/main`.

- [ ] **Step 5: Post-build hardware smoke test**

After CI finishes (~4 min), update the target machine and open the settings app. Verify:

1. Every sidebar category still opens its page (all 16: Appearance, Display, Network, Bluetooth, Panel, Mouse & Touchpad, Keyboard, Sound, Power & Lock, Accessibility, Date & Time, Users, Language & Region, Default Apps, About).
2. No Python stack-trace in `journalctl --user -b | grep adwaita-lite-settings` from the slimmer BasePage (missing method / import errors).
3. Panel's Module Layout section headers still render with the bold uppercase styling (that's `.group-title`, kept).
4. Appearance's accent circles still render with color backgrounds (`.accent-*`, kept).
5. Appearance's wallpaper tiles still render with their custom overlays (`.wallpaper-*`, kept).

If anything is off, `git revert HEAD && git push` and investigate which class was removed prematurely.

---

## Completion criteria

- `base.py` shrunk to ~50 lines, retains only the page-protocol surface.
- `settings/utils.py` deleted.
- Dead CSS rules purged; kept rules still have live callers.
- Single atomic commit on `origin/main`.
- Hardware smoke test passes on all 16 pages.
- Migration complete.
