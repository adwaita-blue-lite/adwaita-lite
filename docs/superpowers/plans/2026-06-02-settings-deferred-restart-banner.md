# Settings Deferred Restart Banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a translated Adwaita restart-session banner in Settings that appears when deferred panel/start-menu changes are pending.

**Architecture:** `SettingsStore` owns deferred-change detection by comparing current in-memory settings to the session-start snapshot. `SettingsWindow` displays an `Adw.Banner`, opens an `Adw.AlertDialog` confirmation, and starts `labwc --exit` on confirmation. Translation work updates the Settings POT/PO/MO catalogs for all supported locales.

**Tech Stack:** Python 3, GTK4/libadwaita via PyGObject, GNU gettext (`xgettext`, `msgmerge`, `msgfmt`), pytest.

---

## File Structure

- Modify `files/usr/lib/adwaita-lite/settings/settings_store.py`: add deferred-session key constants, session snapshot loading, pending-state comparison, and a callback for window UI refresh.
- Modify `files/usr/lib/adwaita-lite/settings/window.py`: add the `Adw.Banner`, confirmation dialog, restart-session command, and error toast path.
- Modify `tests/test_settings_store.py`: add real behavior tests for pending detection and callback refresh.
- Modify `tests/test_settings_app_logic.py`: add source-level tests for the Adwaita banner/dialog/restart command wiring.
- Modify `po/settings/adwaita-lite-settings.pot`, `po/settings/*.po`, and `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-settings.mo`: add and compile translated strings.
- Modify `tests/test_translation_catalogs.py`: add a focused guard that the new Settings restart strings are present and translated.

---

### Task 1: SettingsStore Deferred-Change State

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/settings_store.py`
- Test: `tests/test_settings_store.py`

- [ ] **Step 1: Write failing tests for snapshot comparison**

Add these tests after `test_waybar_apply_spawn_failure_reports_file_update_error` in `tests/test_settings_store.py`:

```python
def _write_session_snapshot(monkeypatch, tmp_path, data):
    runtime_dir = tmp_path / "runtime"
    snapshot = runtime_dir / "adwaita-lite/session-settings.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.delenv("ADWAITA_LITE_SESSION_SETTINGS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    return snapshot


def test_deferred_session_changes_detect_session_snapshot_difference(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom", "accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom", "accent": "blue"},
        existing={"edge": "top", "accent": "blue"},
    )

    assert store.has_deferred_session_changes() is True


def test_deferred_session_changes_hide_when_values_match_snapshot(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom", "accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom", "accent": "blue"},
        existing={"edge": "bottom", "accent": "blue"},
    )

    assert store.has_deferred_session_changes() is False


def test_deferred_session_changes_ignore_missing_or_invalid_snapshot(monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime"
    snapshot = runtime_dir / "adwaita-lite/session-settings.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{invalid", encoding="utf-8")
    monkeypatch.delenv("ADWAITA_LITE_SESSION_SETTINGS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom"},
        existing={"edge": "top"},
    )

    assert store.has_deferred_session_changes() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_settings_store.py::test_deferred_session_changes_detect_session_snapshot_difference tests/test_settings_store.py::test_deferred_session_changes_hide_when_values_match_snapshot tests/test_settings_store.py::test_deferred_session_changes_ignore_missing_or_invalid_snapshot
```

Expected: FAIL because `SettingsStore` has no `has_deferred_session_changes()` method.

- [ ] **Step 3: Implement pending-state comparison**

In `files/usr/lib/adwaita-lite/settings/settings_store.py`, add these constants near the imports/class definition:

```python
SESSION_SETTINGS_ENV = "ADWAITA_LITE_SESSION_SETTINGS"
SESSION_SETTINGS_NAME = "session-settings.json"
DEFERRED_SESSION_KEYS = frozenset({
    "edge",
    "layout",
    "density",
    "pinned",
    "panel_twilight",
    "accent",
    "theme",
    "high_contrast",
    "font_size",
    "scale",
})
```

In `SettingsStore.__init__`, add the deferred callback attribute after `_toast_callback`:

```python
        self._deferred_changes_callback = None
```

Add these methods after `show_toast()`:

```python
    def set_deferred_changes_callback(self, callback) -> None:
        self._deferred_changes_callback = callback

    def _runtime_dir(self) -> Path:
        return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")

    def _session_settings_candidates(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        session_settings = os.environ.get(SESSION_SETTINGS_ENV)
        if session_settings:
            candidates.append(Path(session_settings))
        candidates.append(self._runtime_dir() / "adwaita-lite" / SESSION_SETTINGS_NAME)
        return tuple(candidates)

    def _load_session_settings_snapshot(self) -> dict | None:
        for path in self._session_settings_candidates():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
        return None

    def has_deferred_session_changes(self) -> bool:
        snapshot = self._load_session_settings_snapshot()
        if snapshot is None:
            return False
        for key in DEFERRED_SESSION_KEYS:
            if self._data.get(key) != snapshot.get(key):
                return True
        return False

    def _notify_deferred_changes_changed(self) -> None:
        if self._deferred_changes_callback is not None:
            self._deferred_changes_callback(self.has_deferred_session_changes())
```

- [ ] **Step 4: Run snapshot comparison tests**

Run:

```bash
pytest -q tests/test_settings_store.py::test_deferred_session_changes_detect_session_snapshot_difference tests/test_settings_store.py::test_deferred_session_changes_hide_when_values_match_snapshot tests/test_settings_store.py::test_deferred_session_changes_ignore_missing_or_invalid_snapshot
```

Expected: PASS.

- [ ] **Step 5: Write failing tests for callback refresh after writes**

Add these tests after the snapshot comparison tests in `tests/test_settings_store.py`:

```python
def test_deferred_session_callback_runs_after_save_and_apply(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom"},
        existing={"edge": "bottom"},
    )
    states = []
    store.set_deferred_changes_callback(states.append)

    with patch.object(store, "_run_apply"):
        store.save_and_apply("edge", "top", mode="waybar")
        store.save_and_apply("edge", "bottom", mode="waybar")

    assert states == [True, False]


def test_deferred_session_callback_runs_after_restore_keys_and_flush(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"accent": "blue"},
        existing={"accent": "red"},
    )
    states = []
    store.set_deferred_changes_callback(states.append)

    with patch.object(store, "_run_apply"):
        assert store.restore_keys(["accent"], {"accent": "blue"}) is True
    with patch("settings.settings_store.GLib.timeout_add", return_value=123), \
         patch("settings.settings_store.GLib.source_remove"), \
         patch.object(store, "_run_apply"):
        store.save_debounced("accent", "red")
        store.flush_and_detach()

    assert states == [False, True]
```

- [ ] **Step 6: Run callback tests to verify they fail**

Run:

```bash
pytest -q tests/test_settings_store.py::test_deferred_session_callback_runs_after_save_and_apply tests/test_settings_store.py::test_deferred_session_callback_runs_after_restore_keys_and_flush
```

Expected: FAIL because write paths do not call `_notify_deferred_changes_changed()` yet.

- [ ] **Step 7: Refresh callback in write paths**

In `SettingsStore.save_and_apply()`, after a successful `_write()` and before `_run_apply(mode)`, add:

```python
        self._notify_deferred_changes_changed()
```

In `SettingsStore.save_dict_and_apply()`, after a successful `_write()` and before `_run_apply()`, add:

```python
        self._notify_deferred_changes_changed()
```

In `SettingsStore.restore_keys()`, after `self._data = next_data` and before the `if apply_now:` block, add:

```python
        self._notify_deferred_changes_changed()
```

In `SettingsStore.flush_and_detach()`, inside the `if pending_debounces:` block after `flushed_debounces = True`, add:

```python
                self._notify_deferred_changes_changed()
```

- [ ] **Step 8: Run SettingsStore tests**

Run:

```bash
pytest -q tests/test_settings_store.py
```

Expected: all SettingsStore tests pass.

- [ ] **Step 9: Commit Task 1**

Run:

```bash
git add files/usr/lib/adwaita-lite/settings/settings_store.py tests/test_settings_store.py
git commit -m "feat(settings): track deferred session changes"
```

---

### Task 2: Adwaita Restart Banner And Confirmation

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/window.py`
- Test: `tests/test_settings_app_logic.py`

- [ ] **Step 1: Write failing source tests for banner wiring**

Add these tests after `test_window_close_holds_application_until_apply_work_drains` in `tests/test_settings_app_logic.py`:

```python
def test_settings_window_uses_adw_banner_for_deferred_restart_prompt():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/window.py"
    ).read_text(encoding="utf-8")

    assert "self._deferred_restart_banner = Adw.Banner()" in source
    assert '_("Restart your session to apply panel and start menu changes.")' in source
    assert '_("Restart Session")' in source
    assert 'connect("button-clicked", self._on_restart_session_clicked)' in source
    assert "content_toolbar.add_top_bar(self._deferred_restart_banner)" in source
    assert "store.set_deferred_changes_callback(self._set_deferred_restart_banner_revealed)" in source
    assert "self._store.set_deferred_changes_callback(None)" in source
    assert "store.has_deferred_session_changes()" in source


def test_settings_window_confirms_and_runs_session_restart():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/window.py"
    ).read_text(encoding="utf-8")

    assert "def _on_restart_session_clicked" in source
    assert "Adw.AlertDialog.new" in source
    assert '_("Restart Session?")' in source
    assert '_("This will close your apps and return you to the sign-in screen.")' in source
    assert 'dialog.add_response("cancel", _("Cancel"))' in source
    assert 'dialog.add_response("restart", _("Restart Session"))' in source
    assert 'dialog.set_response_appearance("restart", Adw.ResponseAppearance.DESTRUCTIVE)' in source
    assert '["labwc", "--exit"]' in source
    assert "stdin=subprocess.DEVNULL" in source
    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source
    assert '_("Could not restart session: {detail}")' in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_settings_app_logic.py::test_settings_window_uses_adw_banner_for_deferred_restart_prompt tests/test_settings_app_logic.py::test_settings_window_confirms_and_runs_session_restart
```

Expected: FAIL because `SettingsWindow` does not create a deferred restart banner or restart dialog yet.

- [ ] **Step 3: Implement banner construction**

In `files/usr/lib/adwaita-lite/settings/window.py`, add `subprocess` to the imports:

```python
import subprocess
```

After creating `self._search_bar`, create the banner:

```python
        self._deferred_restart_banner = Adw.Banner()
        self._deferred_restart_banner.set_title(
            _("Restart your session to apply panel and start menu changes.")
        )
        self._deferred_restart_banner.set_button_label(_("Restart Session"))
        self._deferred_restart_banner.connect(
            "button-clicked", self._on_restart_session_clicked
        )
        self._deferred_restart_banner.set_revealed(
            store.has_deferred_session_changes()
        )
```

After `content_toolbar.add_top_bar(self._search_bar)`, add:

```python
        content_toolbar.add_top_bar(self._deferred_restart_banner)
```

After `store.set_toast_callback(self._show_toast)`, add:

```python
        store.set_deferred_changes_callback(self._set_deferred_restart_banner_revealed)
```

- [ ] **Step 4: Implement banner visibility and restart flow**

Add these methods after `_on_close_request()` in `SettingsWindow`:

```python
    def _set_deferred_restart_banner_revealed(self, revealed: bool) -> None:
        self._deferred_restart_banner.set_revealed(bool(revealed))

    def _on_restart_session_clicked(self, _banner: Adw.Banner) -> None:
        dialog = Adw.AlertDialog.new(
            _("Restart Session?"),
            _("This will close your apps and return you to the sign-in screen."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restart", _("Restart Session"))
        dialog.set_response_appearance("restart", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_restart_session_response)
        dialog.present(self)

    def _on_restart_session_response(self, _dialog, response_id: str) -> None:
        if response_id != "restart":
            return
        self._restart_session()

    def _restart_session(self) -> None:
        try:
            subprocess.Popen(
                ["labwc", "--exit"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            detail = str(exc) or exc.__class__.__name__
            self._show_toast(
                _("Could not restart session: {detail}").format(detail=detail),
                True,
            )
```

In `_on_close_request()`, before `self._store.flush_and_detach()`, clear the deferred callback so a reused store cannot call into a destroyed banner:

```python
        self._store.set_deferred_changes_callback(None)
```

- [ ] **Step 5: Run window tests**

Run:

```bash
pytest -q tests/test_settings_app_logic.py::test_settings_window_uses_adw_banner_for_deferred_restart_prompt tests/test_settings_app_logic.py::test_settings_window_confirms_and_runs_session_restart tests/test_settings_app_logic.py::test_window_close_holds_application_until_apply_work_drains
```

Expected: all selected Settings window tests pass.

- [ ] **Step 6: Run Settings logic tests**

Run:

```bash
pytest -q tests/test_settings_app_logic.py
```

Expected: all Settings app logic tests pass.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add files/usr/lib/adwaita-lite/settings/window.py tests/test_settings_app_logic.py
git commit -m "feat(settings): show deferred restart banner"
```

---

### Task 3: Settings Translation Catalog Updates

**Files:**
- Modify: `po/settings/adwaita-lite-settings.pot`
- Modify: `po/settings/am.po`
- Modify: `po/settings/ar.po`
- Modify: `po/settings/de.po`
- Modify: `po/settings/es.po`
- Modify: `po/settings/fa.po`
- Modify: `po/settings/fr.po`
- Modify: `po/settings/ha.po`
- Modify: `po/settings/hi.po`
- Modify: `po/settings/it.po`
- Modify: `po/settings/ja.po`
- Modify: `po/settings/ko.po`
- Modify: `po/settings/nl.po`
- Modify: `po/settings/pl.po`
- Modify: `po/settings/pt.po`
- Modify: `po/settings/ru.po`
- Modify: `po/settings/sv.po`
- Modify: `po/settings/sw.po`
- Modify: `po/settings/th.po`
- Modify: `po/settings/tr.po`
- Modify: `po/settings/vi.po`
- Modify: `po/settings/yo.po`
- Modify: `po/settings/zh.po`
- Modify: `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-settings.mo`
- Test: `tests/test_translation_catalogs.py`

- [ ] **Step 1: Write failing focused translation test**

Add this test after `test_all_compiled_mo_files_exist_after_build` in `tests/test_translation_catalogs.py`:

```python
def test_settings_deferred_restart_strings_are_translated():
    required = {
        "Restart your session to apply panel and start menu changes.": (),
        "Restart Session": (),
        "Restart Session?": (),
        "This will close your apps and return you to the sign-in screen.": (),
        "Could not restart session: {detail}": ("{detail}",),
    }
    pot_entries = {
        "".join(entry["msgid"])
        for entry in _parse_po_entries(ROOT / "po/settings/adwaita-lite-settings.pot")
    }
    for msgid in required:
        assert msgid in pot_entries

    for lang in LANGUAGES:
        entries = {
            "".join(entry["msgid"]): "".join(entry["msgstr"])
            for entry in _parse_po_entries(ROOT / "po/settings" / f"{lang}.po")
        }
        for msgid, placeholders in required.items():
            msgstr = entries.get(msgid, "")
            assert msgstr.strip(), f"{lang} missing translation for {msgid!r}"
            for placeholder in placeholders:
                assert placeholder in msgstr, f"{lang} missing {placeholder} in {msgid!r}"
```

- [ ] **Step 2: Run translation test to verify it fails**

Run:

```bash
pytest -q tests/test_translation_catalogs.py::test_settings_deferred_restart_strings_are_translated
```

Expected: FAIL because the new restart banner strings are not in the Settings POT/PO files yet.

- [ ] **Step 3: Regenerate Settings POT and merge PO files**

Run:

```bash
make -C po pot-settings po-settings
```

Expected: `po/settings/adwaita-lite-settings.pot` and every `po/settings/*.po` now contain entries for the five new msgids, initially untranslated or fuzzy.

- [ ] **Step 4: Fill translations for all supported Settings locales**

Run this script from the repository root to set exact msgstr values and clear fuzzy flags only on the new entries:

```bash
python - <<'PY'
import json
from pathlib import Path

messages = [
    "Restart your session to apply panel and start menu changes.",
    "Restart Session",
    "Restart Session?",
    "This will close your apps and return you to the sign-in screen.",
    "Could not restart session: {detail}",
]

translations = {
    "am": [
        "የፓነል እና የጀምር ምናሌ ለውጦችን ለመተግበር ክፍለ ጊዜዎን እንደገና ያስጀምሩ።",
        "ክፍለ ጊዜ ዳግም አስጀምር",
        "ክፍለ ጊዜ ዳግም ይጀመር?",
        "ይህ መተግበሪያዎችዎን ይዘጋል እና ወደ መግቢያ ማያ ገጽ ይመልስዎታል።",
        "ክፍለ ጊዜ መጀመር አልተቻለም፦ {detail}",
    ],
    "ar": [
        "أعد تشغيل الجلسة لتطبيق تغييرات اللوحة وقائمة البدء.",
        "إعادة تشغيل الجلسة",
        "إعادة تشغيل الجلسة؟",
        "سيؤدي هذا إلى إغلاق تطبيقاتك وإعادتك إلى شاشة تسجيل الدخول.",
        "تعذرت إعادة تشغيل الجلسة: {detail}",
    ],
    "de": [
        "Starten Sie Ihre Sitzung neu, um Änderungen an Leiste und Startmenü anzuwenden.",
        "Sitzung neu starten",
        "Sitzung neu starten?",
        "Dadurch werden Ihre Apps geschlossen und Sie kehren zum Anmeldebildschirm zurück.",
        "Sitzung konnte nicht neu gestartet werden: {detail}",
    ],
    "es": [
        "Reinicia la sesión para aplicar los cambios del panel y del menú de inicio.",
        "Reiniciar sesión",
        "¿Reiniciar sesión?",
        "Esto cerrará tus aplicaciones y te devolverá a la pantalla de inicio de sesión.",
        "No se pudo reiniciar la sesión: {detail}",
    ],
    "fa": [
        "برای اعمال تغییرات پنل و منوی شروع، نشست خود را دوباره شروع کنید.",
        "شروع دوباره نشست",
        "نشست دوباره شروع شود؟",
        "این کار برنامه‌های شما را می‌بندد و شما را به صفحه ورود برمی‌گرداند.",
        "شروع دوباره نشست ممکن نشد: {detail}",
    ],
    "fr": [
        "Redémarrez votre session pour appliquer les changements du panneau et du menu Démarrer.",
        "Redémarrer la session",
        "Redémarrer la session ?",
        "Cela fermera vos applications et vous ramènera à l’écran de connexion.",
        "Impossible de redémarrer la session : {detail}",
    ],
    "ha": [
        "Sake farawa da zaman ku don amfani da canje-canjen panel da menu na farawa.",
        "Sake Fara Zama",
        "A sake fara zaman?",
        "Wannan zai rufe manhajojinku kuma ya mayar da ku zuwa allon shiga.",
        "Ba a iya sake fara zama ba: {detail}",
    ],
    "hi": [
        "पैनल और स्टार्ट मेनू बदलाव लागू करने के लिए अपना सत्र पुनः शुरू करें।",
        "सत्र पुनः शुरू करें",
        "सत्र पुनः शुरू करें?",
        "यह आपके ऐप्स बंद करेगा और आपको साइन-इन स्क्रीन पर वापस ले जाएगा।",
        "सत्र पुनः शुरू नहीं किया जा सका: {detail}",
    ],
    "it": [
        "Riavvia la sessione per applicare le modifiche al pannello e al menu Start.",
        "Riavvia sessione",
        "Riavviare la sessione?",
        "Questo chiuderà le applicazioni e ti riporterà alla schermata di accesso.",
        "Impossibile riavviare la sessione: {detail}",
    ],
    "ja": [
        "パネルとスタートメニューの変更を適用するには、セッションを再起動してください。",
        "セッションを再起動",
        "セッションを再起動しますか?",
        "アプリを閉じてサインイン画面に戻ります。",
        "セッションを再起動できませんでした: {detail}",
    ],
    "ko": [
        "패널 및 시작 메뉴 변경 사항을 적용하려면 세션을 다시 시작하세요.",
        "세션 다시 시작",
        "세션을 다시 시작할까요?",
        "앱을 닫고 로그인 화면으로 돌아갑니다.",
        "세션을 다시 시작할 수 없습니다: {detail}",
    ],
    "nl": [
        "Start je sessie opnieuw om wijzigingen aan het paneel en startmenu toe te passen.",
        "Sessie herstarten",
        "Sessie herstarten?",
        "Dit sluit je apps en brengt je terug naar het aanmeldscherm.",
        "Kan sessie niet herstarten: {detail}",
    ],
    "pl": [
        "Uruchom sesję ponownie, aby zastosować zmiany panelu i menu Start.",
        "Uruchom sesję ponownie",
        "Uruchomić sesję ponownie?",
        "Spowoduje to zamknięcie aplikacji i powrót do ekranu logowania.",
        "Nie można uruchomić sesji ponownie: {detail}",
    ],
    "pt": [
        "Reinicie a sessão para aplicar as alterações do painel e do menu Iniciar.",
        "Reiniciar sessão",
        "Reiniciar sessão?",
        "Isto fechará os seus aplicativos e retornará à tela de início de sessão.",
        "Não foi possível reiniciar a sessão: {detail}",
    ],
    "ru": [
        "Перезапустите сеанс, чтобы применить изменения панели и меню «Пуск».",
        "Перезапустить сеанс",
        "Перезапустить сеанс?",
        "Это закроет ваши приложения и вернёт вас на экран входа.",
        "Не удалось перезапустить сеанс: {detail}",
    ],
    "sv": [
        "Starta om sessionen för att tillämpa ändringar i panelen och startmenyn.",
        "Starta om session",
        "Starta om sessionen?",
        "Detta stänger dina appar och tar dig tillbaka till inloggningsskärmen.",
        "Kunde inte starta om sessionen: {detail}",
    ],
    "sw": [
        "Anzisha upya kikao chako ili kutumia mabadiliko ya paneli na menyu ya kuanza.",
        "Anzisha Upya Kikao",
        "Uanzishe upya kikao?",
        "Hii itafunga programu zako na kukurudisha kwenye skrini ya kuingia.",
        "Imeshindwa kuanzisha upya kikao: {detail}",
    ],
    "th": [
        "เริ่มเซสชันใหม่เพื่อใช้การเปลี่ยนแปลงของแผงและเมนูเริ่ม",
        "เริ่มเซสชันใหม่",
        "เริ่มเซสชันใหม่หรือไม่?",
        "การดำเนินการนี้จะปิดแอปของคุณและพาคุณกลับไปยังหน้าจอลงชื่อเข้าใช้",
        "ไม่สามารถเริ่มเซสชันใหม่ได้: {detail}",
    ],
    "tr": [
        "Panel ve başlat menüsü değişikliklerini uygulamak için oturumunuzu yeniden başlatın.",
        "Oturumu Yeniden Başlat",
        "Oturum yeniden başlatılsın mı?",
        "Bu, uygulamalarınızı kapatır ve sizi oturum açma ekranına döndürür.",
        "Oturum yeniden başlatılamadı: {detail}",
    ],
    "vi": [
        "Khởi động lại phiên để áp dụng các thay đổi cho bảng điều khiển và menu bắt đầu.",
        "Khởi động lại phiên",
        "Khởi động lại phiên?",
        "Thao tác này sẽ đóng ứng dụng của bạn và đưa bạn về màn hình đăng nhập.",
        "Không thể khởi động lại phiên: {detail}",
    ],
    "yo": [
        "Tún ìgbà rẹ bẹ̀rẹ̀ láti lo àwọn ayípadà pánẹ́lì àti mẹ́nù ìbẹ̀rẹ̀.",
        "Tún Ìgbà Bẹ̀rẹ̀",
        "Ṣé kí a tún ìgbà bẹ̀rẹ̀?",
        "Èyí yóò pa àwọn app rẹ, yóò sì dá ọ padà sí ojú ìwọlé.",
        "Kò le tún ìgbà bẹ̀rẹ̀: {detail}",
    ],
    "zh": [
        "重启会话以应用面板和开始菜单更改。",
        "重启会话",
        "重启会话？",
        "这将关闭你的应用并返回登录屏幕。",
        "无法重启会话：{detail}",
    ],
}

def po_string(value):
    return json.dumps(value, ensure_ascii=False)

for lang, values in translations.items():
    path = Path("po/settings") / f"{lang}.po"
    replacements = dict(zip(messages, values))
    blocks = path.read_text(encoding="utf-8").split("\n\n")
    next_blocks = []
    for block in blocks:
        updated = block
        for msgid, msgstr in replacements.items():
            marker = f"msgid {po_string(msgid)}"
            if marker not in updated:
                continue
            lines = []
            for line in updated.splitlines():
                if line.startswith("#, "):
                    flags = [
                        flag.strip()
                        for flag in line[3:].split(",")
                        if flag.strip() != "fuzzy"
                    ]
                    if flags:
                        lines.append("#, " + ", ".join(flags))
                    continue
                lines.append(line)
            for index, line in enumerate(lines):
                if line.startswith("msgstr "):
                    lines[index] = f"msgstr {po_string(msgstr)}"
                    break
            updated = "\n".join(lines)
        next_blocks.append(updated)
    path.write_text("\n\n".join(next_blocks), encoding="utf-8")
PY
```

- [ ] **Step 5: Compile Settings MO catalogs**

Run:

```bash
make -C po mo-settings
```

Expected: `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-settings.mo` are updated.

- [ ] **Step 6: Run translation tests**

Run:

```bash
pytest -q tests/test_translation_catalogs.py
```

Expected: all translation catalog tests pass.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add tests/test_translation_catalogs.py po/settings files/usr/share/locale
git commit -m "i18n(settings): translate deferred restart banner"
```

---

### Task 4: Final Verification

**Files:**
- Verify: `files/usr/lib/adwaita-lite/settings/settings_store.py`
- Verify: `files/usr/lib/adwaita-lite/settings/window.py`
- Verify: `tests/test_settings_store.py`
- Verify: `tests/test_settings_app_logic.py`
- Verify: `tests/test_translation_catalogs.py`
- Verify: `po/settings/*`
- Verify: `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-settings.mo`

- [ ] **Step 1: Run focused regressions**

Run:

```bash
pytest -q \
  tests/test_settings_store.py::test_deferred_session_changes_detect_session_snapshot_difference \
  tests/test_settings_store.py::test_deferred_session_changes_hide_when_values_match_snapshot \
  tests/test_settings_store.py::test_deferred_session_changes_ignore_missing_or_invalid_snapshot \
  tests/test_settings_store.py::test_deferred_session_callback_runs_after_save_and_apply \
  tests/test_settings_store.py::test_deferred_session_callback_runs_after_restore_keys_and_flush \
  tests/test_settings_app_logic.py::test_settings_window_uses_adw_banner_for_deferred_restart_prompt \
  tests/test_settings_app_logic.py::test_settings_window_confirms_and_runs_session_restart \
  tests/test_translation_catalogs.py::test_settings_deferred_restart_strings_are_translated
```

Expected: all focused regression tests pass.

- [ ] **Step 2: Run affected test files**

Run:

```bash
pytest -q tests/test_settings_store.py tests/test_settings_app_logic.py tests/test_translation_catalogs.py
```

Expected: all affected test files pass.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
pytest -q
```

Expected: full suite passes. The existing `PyGIDeprecationWarning` is acceptable if it remains the only warning.

- [ ] **Step 4: Check whitespace and final status**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` prints no output. `git status --short` is clean after commits.

- [ ] **Step 5: Manual desktop verification**

In a Adwaita-Lite session, change a Panel setting that uses `mode="waybar"`. Expected: the existing toast appears, and the Settings banner appears with `Restart Session`. Close and reopen Settings in the same session. Expected: the banner is still visible. Click `Restart Session`. Expected: an Adwaita confirmation dialog appears. Click `Cancel`. Expected: session continues and banner remains. Click `Restart Session` again and confirm. Expected: the labwc session exits to the sign-in screen. After logging back in, reopen Settings. Expected: the banner is hidden if the session snapshot now matches `settings.json`.
