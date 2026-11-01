# Continue Button UX & Button Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Continue button so it appears when bootc finishes (not before), add a disabled placeholder while bootc runs, polish all wizard button CSS to Adwaita+ChromeOS quality.

**Architecture:** Single-file change to the wizard script — CSS constant + widget setup + loop logic. Translation updates across 22 `.po` files + `.mo` recompile via `make mo-wizard`.

**Tech Stack:** Python 3, GTK4 (CSS), gettext (`.po`/`.mo`)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `files/usr/bin/adwaita-lite-setup-wizard` | Modify | CSS constant (lines 71-180), button widget setup (~line 1518), `_step_install_system` loop (~line 2453), `_bootc_continue_clicked` handler (~line 3191) |
| `po/*.po` (22 files) | Modify | Add `"Waiting for install..."` translation entry |
| `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo` (22 files) | Regenerate | Compiled from `.po` via `make mo-wizard` |

---

### Task 1: Polish button CSS

Replace all three button class definitions in the `CSS` constant with Adwaita dark + ChromeOS styling. Add `@keyframes pop-in`, destructive disabled state, and transitions.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:119-180` (CSS button block)

- [ ] **Step 1: Replace the button CSS block**

In `files/usr/bin/adwaita-lite-setup-wizard`, replace lines 119–180 (from `button.create-button {` through `button.back-button:hover label {`) with:

```css
button.create-button {
    font-family: "Roboto", sans-serif;
    font-size: 16px;
    font-weight: bold;
    padding: 12px 32px;
    border-radius: 10px;
    background: #3584e4;
    color: #ffffff;
    border: none;
    box-shadow: 0 1px 2px rgba(0,0,0,0.3);
    min-height: 36px;
    transition: background 200ms ease, box-shadow 200ms ease, opacity 200ms ease;
}

button.create-button label {
    color: #ffffff;
}

button.create-button:hover {
    background: #62a0ea;
}

button.create-button:active {
    background: #1c71d8;
    box-shadow: none;
}

button.create-button:disabled {
    background: #3d3d3d;
    color: #888888;
    box-shadow: none;
}

button.create-button:disabled label {
    color: #888888;
}

button.destructive-button {
    font-family: "Roboto", sans-serif;
    font-size: 16px;
    font-weight: bold;
    padding: 12px 32px;
    border-radius: 10px;
    background: #c01c28;
    color: #ffffff;
    border: none;
    box-shadow: 0 1px 2px rgba(0,0,0,0.3);
    min-height: 36px;
    transition: background 200ms ease, box-shadow 200ms ease, opacity 200ms ease;
}

button.destructive-button label {
    color: #ffffff;
}

button.destructive-button:hover {
    background: #e01b24;
}

button.destructive-button:active {
    background: #a51d2d;
    box-shadow: none;
}

button.destructive-button:disabled {
    background: #3d3d3d;
    color: #888888;
    box-shadow: none;
}

button.destructive-button:disabled label {
    color: #888888;
}

@keyframes pop-in {
    from { opacity: 0; }
    to   { opacity: 1; }
}

.pop-in {
    animation: pop-in 300ms ease-out;
}

button.back-button {
    font-family: "Roboto", sans-serif;
    font-size: 16px;
    padding: 12px 32px;
    border-radius: 10px;
    background: transparent;
    border: none;
    box-shadow: none;
    color: #aaaaaa;
    min-height: 36px;
    transition: background 200ms ease, color 200ms ease;
}

button.back-button label {
    color: #aaaaaa;
}

button.back-button:hover {
    background: rgba(255,255,255,0.08);
}

button.back-button:hover label {
    color: #dddddd;
}

button.back-button:active {
    background: rgba(255,255,255,0.04);
}

button.back-button:active label {
    color: #bbbbbb;
}
```

- [ ] **Step 2: Verify no other CSS references break**

Run: `grep -n 'create-button\|destructive-button\|back-button' files/usr/bin/adwaita-lite-setup-wizard | grep -v '^[0-9]*:.*CSS'`

Expected: Only widget `.add_css_class()` calls — no hardcoded style overrides elsewhere.

- [ ] **Step 3: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "style(wizard): polish button CSS to Adwaita dark + ChromeOS feel

Add transitions, active/pressed states, box-shadow depth, disabled
states for destructive buttons, and pop-in keyframe animation.
Standardise font-size to 16px and border-radius to 10px across all
button classes."
```

---

### Task 2: Rewrite Continue button behavior

Change the button from "visible immediately, disappears on proc exit" to "visible-but-disabled immediately, enables on proc exit or 10-min timeout, hidden after click".

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1518-1523` (button widget setup)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:2453-2484` (`_step_install_system` loop)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:~3191` (`_bootc_continue_clicked` handler)

- [ ] **Step 1: Update button widget setup to start disabled with "Waiting for install..." label**

In `_build_progress_page`, replace:

```python
        self._progress_continue_btn = Gtk.Button(label=_("Continue"))
        self._progress_continue_btn.add_css_class("destructive-button")
        self._progress_continue_btn.set_visible(False)
        self._progress_continue_btn.connect("clicked", lambda _: self._bootc_continue_clicked())
        self._retranslatable.append((self._progress_continue_btn.set_label, "Continue"))
        btn_box.append(self._progress_continue_btn)
```

with:

```python
        self._progress_continue_btn = Gtk.Button(label=_("Waiting for install..."))
        self._progress_continue_btn.add_css_class("destructive-button")
        self._progress_continue_btn.set_visible(False)
        self._progress_continue_btn.set_sensitive(False)
        self._progress_continue_btn.connect("clicked", lambda _: self._bootc_continue_clicked())
        self._retranslatable.append((self._progress_continue_btn.set_label, "Waiting for install..."))
        btn_box.append(self._progress_continue_btn)
```

- [ ] **Step 2: Rewrite the `_step_install_system` wait loop**

Replace the block from `# Show Continue button for user to signal bootc completion` through `GLib.idle_add(self._progress_continue_btn.set_visible, False)` (lines 2453-2484) with:

```python
        # Show disabled Continue button — enables when bootc exits or after timeout
        self._bootc_continue_event = threading.Event()

        def _show_disabled_continue():
            self._progress_continue_btn.set_label(_("Waiting for install..."))
            self._progress_continue_btn.set_sensitive(False)
            self._progress_continue_btn.set_visible(True)
            self._progress_continue_btn.remove_css_class("pop-in")

        def _enable_continue():
            self._progress_continue_btn.set_label(_("Continue"))
            self._progress_continue_btn.set_sensitive(True)
            self._progress_continue_btn.add_css_class("pop-in")

        GLib.idle_add(_show_disabled_continue)

        bootc_exited = False
        enabled = False
        fallback_timeout = 600  # 10 minutes
        start_time = time.time()
        deadline = start_time + 3600  # 1-hour hard limit

        while time.time() < deadline:
            # Check if bootc exited — enable button if so
            if not bootc_exited and proc.poll() is not None:
                bootc_exited = True
                if not enabled:
                    enabled = True
                    GLib.idle_add(_enable_continue)

            # Fallback: enable after 10 minutes even if bootc still running
            if not enabled and (time.time() - start_time) >= fallback_timeout:
                enabled = True
                GLib.idle_add(_enable_continue)

            # Wait for user click
            if self._bootc_continue_event.wait(timeout=5):
                # User clicked Continue — kill bootc if still alive
                if proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        proc.wait(timeout=10)
                    except (subprocess.TimeoutExpired, ProcessLookupError):
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                break
        else:
            # 1-hour hard deadline — force kill
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

        GLib.idle_add(self._progress_continue_btn.set_visible, False)
```

- [ ] **Step 3: Update `_bootc_continue_clicked` handler**

The handler at ~line 3191 is fine as-is — it sets the event and hides the button. No changes needed. Verify it reads:

```python
    def _bootc_continue_clicked(self) -> None:
        """User confirmed bootc is done — signal the worker thread to proceed."""
        if hasattr(self, "_bootc_continue_event"):
            self._bootc_continue_event.set()
        self._progress_continue_btn.set_visible(False)
```

- [ ] **Step 4: Update `_start_step_runner` button reset**

Verify the reset block includes the continue button and also resets sensitivity. Replace:

```python
        self._progress_back_btn.set_visible(False)
        self._progress_skip_btn.set_visible(False)
        self._progress_retry_btn.set_visible(False)
        self._progress_continue_btn.set_visible(False)
        self._progress_reboot_btn.set_visible(False)
```

with:

```python
        self._progress_back_btn.set_visible(False)
        self._progress_skip_btn.set_visible(False)
        self._progress_retry_btn.set_visible(False)
        self._progress_continue_btn.set_visible(False)
        self._progress_continue_btn.set_sensitive(False)
        self._progress_reboot_btn.set_visible(False)
```

- [ ] **Step 5: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "fix(wizard): Continue button appears on bootc exit, not before

Button starts visible-but-disabled ('Waiting for install...') when
bootc launches.  Enables with pop-in animation when bootc exits
(happy path) or after 10-minute fallback timeout (hang path).
Process is only killed if still alive when user clicks Continue."
```

---

### Task 3: Add "Waiting for install..." translations

Add the new translatable string to all 22 `.po` files and recompile.

**Files:**
- Modify: `po/am.po`, `po/ar.po`, `po/de.po`, `po/es.po`, `po/fa.po`, `po/fr.po`, `po/ha.po`, `po/hi.po`, `po/it.po`, `po/ja.po`, `po/ko.po`, `po/nl.po`, `po/pl.po`, `po/pt.po`, `po/ru.po`, `po/sv.po`, `po/sw.po`, `po/th.po`, `po/tr.po`, `po/vi.po`, `po/yo.po`, `po/zh.po`
- Regenerate: `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo` (22 files)

- [ ] **Step 1: Add translation entries to all 22 `.po` files**

Append the following entry to the END of each `.po` file (before any trailing newline). Use the Edit tool on each file.

| File | msgstr |
|------|--------|
| `po/am.po` | `"ጭነት በመጠባበቅ ላይ..."` |
| `po/ar.po` | `"في انتظار التثبيت..."` |
| `po/de.po` | `"Warte auf Installation..."` |
| `po/es.po` | `"Esperando la instalación..."` |
| `po/fa.po` | `"در انتظار نصب..."` |
| `po/fr.po` | `"En attente de l'installation..."` |
| `po/ha.po` | `"Ana jiran shigarwa..."` |
| `po/hi.po` | `"इंस्टॉल की प्रतीक्षा..."` |
| `po/it.po` | `"In attesa dell'installazione..."` |
| `po/ja.po` | `"インストールを待機中..."` |
| `po/ko.po` | `"설치 대기 중..."` |
| `po/nl.po` | `"Wachten op installatie..."` |
| `po/pl.po` | `"Oczekiwanie na instalację..."` |
| `po/pt.po` | `"Aguardando a instalação..."` |
| `po/ru.po` | `"Ожидание установки..."` |
| `po/sv.po` | `"Väntar på installation..."` |
| `po/sw.po` | `"Inasubiri usakinishaji..."` |
| `po/th.po` | `"กำลังรอการติดตั้ง..."` |
| `po/tr.po` | `"Kurulum bekleniyor..."` |
| `po/vi.po` | `"Đang chờ cài đặt..."` |
| `po/yo.po` | `"Nduro fun ifi sori ẹrọ..."` |
| `po/zh.po` | `"等待安装中..."` |

Each entry format:

```
#: files/usr/bin/adwaita-lite-setup-wizard:1518
msgid "Waiting for install..."
msgstr "TRANSLATED_STRING"
```

- [ ] **Step 2: Recompile `.mo` files**

Run: `cd po && make mo-wizard`

Expected: All 22 `.mo` files regenerated under `files/usr/share/locale/*/LC_MESSAGES/`.

- [ ] **Step 3: Commit**

```bash
git add po/*.po po/adwaita-lite-setup-wizard.pot files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo
git commit -m "i18n(wizard): add 'Waiting for install...' translations for 22 locales"
```
