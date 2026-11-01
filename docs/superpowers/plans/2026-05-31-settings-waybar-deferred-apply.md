# Settings Waybar Deferred Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Settings from live-reloading Waybar, keep transactional Waybar file writes, and tell users in every Settings language that panel changes apply after restarting the session.

**Architecture:** `SettingsStore` keeps the detached `mode="waybar"` worker but treats it as save-and-defer, not live apply. `adwaita-lite-apply-settings` continues rendering and atomically replacing Waybar config/CSS, while both `--mode waybar` and full/live Settings applies avoid `reload_waybar()`. Panel and Appearance pages show a persistent restart-session notice, and gettext catalogs carry the new copy for all supported locales.

**Tech Stack:** Python 3.14, GTK/Adwaita via PyGObject, GNU gettext PO/POT/MO files, pytest, existing `adwaita-lite-apply-settings` script.

---

## File Map

- Modify `files/usr/libexec/adwaita-lite-apply-settings`: remove Settings-driven Waybar lifecycle calls from `apply_waybar_transaction()` and `_sync_live_session()` while preserving transactional writes.
- Modify `files/usr/lib/adwaita-lite/settings/settings_store.py`: show restart-session success toast for detached Waybar applies and update the spawn-failure copy.
- Modify `files/usr/lib/adwaita-lite/settings/pages/panel.py`: add a persistent restart-session notice to the Panel page.
- Modify `files/usr/lib/adwaita-lite/settings/pages/appearance.py`: add the same persistent notice near accent color because accent changes affect panel styling.
- Modify `tests/test_apply_settings.py`: update transactional Waybar tests and add coverage that live sync ignores `waybar_changed` for reload purposes.
- Modify `tests/test_settings_store.py`: add coverage for the restart-session toast and updated spawn-failure toast.
- Modify `tests/test_settings_app_logic.py`: add source-level coverage for the persistent Panel and Appearance notices.
- Modify `po/settings/adwaita-lite-settings.pot`: add the new translatable Settings strings.
- Modify `po/settings/*.po`: add non-empty translations for every supported Settings language.
- Modify `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-settings.mo`: rebuild compiled Settings catalogs.

---

### Task 1: Remove Settings-Driven Waybar Reloads

**Files:**
- Modify: `tests/test_apply_settings.py`
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Replace the transactional reload expectation with a failing no-reload test**

In `tests/test_apply_settings.py`, replace `test_waybar_transaction_commits_then_reloads` with this test:

```python
def test_waybar_transaction_commits_without_reloading(monkeypatch, tmp_path):
    monkeypatch.setattr(apply_settings, "WAYBAR_DIR", tmp_path)
    monkeypatch.setattr(
        apply_settings,
        "_render_waybar_files",
        lambda tokens: ('{"layer": "top"}\n', "window#waybar {}\n"),
    )
    monkeypatch.setattr(
        apply_settings,
        "reload_waybar",
        lambda: (_ for _ in ()).throw(
            AssertionError("Settings must not reload Waybar")
        ),
    )

    assert apply_settings.apply_waybar_transaction(_make_tokens()) is True
    assert json.loads((tmp_path / "config.jsonc").read_text(encoding="utf-8")) == {
        "layer": "top"
    }
    assert (tmp_path / "style.css").read_text(encoding="utf-8") == "window#waybar {}\n"
```

- [ ] **Step 2: Add a failing live-sync no-reload regression test**

Add these tests after the Waybar transaction tests in `tests/test_apply_settings.py`:

```python
def test_live_sync_skips_waybar_reload_when_waybar_files_changed(monkeypatch):
    calls = []
    settings = _make_settings(suspend_timeout=0)
    tokens = _make_tokens(wallpaper="/same-wallpaper.svg")

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setattr(
        apply_settings,
        "write_gtk_settings",
        lambda tokens_arg, sync_live=True: calls.append(("gtk", sync_live)),
    )
    monkeypatch.setattr(
        apply_settings,
        "_sync_power_profile",
        lambda settings_arg: calls.append(("power", settings_arg)),
    )
    monkeypatch.setattr(
        apply_settings,
        "_sync_lid_action",
        lambda settings_arg: calls.append(("lid", settings_arg)),
    )
    monkeypatch.setattr(
        apply_settings,
        "_current_swaybg_wallpaper",
        lambda: "/same-wallpaper.svg",
    )
    monkeypatch.setattr(
        apply_settings,
        "_swap_swaybg_wallpaper",
        lambda wallpaper, theme="light": calls.append(("wallpaper", wallpaper, theme)),
    )
    monkeypatch.setattr(
        apply_settings,
        "reload_waybar",
        lambda: (_ for _ in ()).throw(
            AssertionError("Settings must not reload Waybar")
        ),
    )
    monkeypatch.setattr(
        apply_settings,
        "_run_best_effort",
        lambda cmd, **kwargs: calls.append(("run", tuple(cmd), kwargs)) or True,
    )
    monkeypatch.setattr(
        apply_settings,
        "restart_program",
        lambda name, cmd: calls.append(("restart", name, tuple(cmd))),
    )

    apply_settings._sync_live_session(
        settings,
        tokens,
        {"waybar_changed": True, "mako_changed": False, "labwc_changed": False},
    )

    assert ("gtk", True) in calls
    assert all(call[0] != "wallpaper" for call in calls)


def test_apply_settings_has_no_waybar_reload_call_sites():
    source = _SCRIPT.read_text(encoding="utf-8")
    call_sites = [
        line.strip()
        for line in source.splitlines()
        if line.strip() == "reload_waybar()"
    ]

    assert call_sites == []
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:

```bash
pytest -q tests/test_apply_settings.py::test_waybar_transaction_commits_without_reloading tests/test_apply_settings.py::test_live_sync_skips_waybar_reload_when_waybar_files_changed tests/test_apply_settings.py::test_apply_settings_has_no_waybar_reload_call_sites
```

Expected: FAIL. The first test fails because `apply_waybar_transaction()` calls `reload_waybar()` after changed writes. The second test fails because `_sync_live_session()` calls `reload_waybar()` when `changes["waybar_changed"]` is true. The static call-site test also fails until both direct call lines are removed.

- [ ] **Step 4: Remove reload calls from Settings-driven apply paths**

In `files/usr/libexec/adwaita-lite-apply-settings`, change `apply_waybar_transaction()` to:

```python
def apply_waybar_transaction(tokens: dict) -> bool:
    config_text, css_text = _render_waybar_files(tokens)
    _validate_waybar_files(config_text, css_text)
    return _write_waybar_files_transactionally(config_text, css_text)
```

In `_sync_live_session()`, remove this block entirely:

```python
        if changes.get("waybar_changed"):
            reload_waybar()
```

Do not remove `reload_waybar()` in this task. Keeping the helper avoids a larger unrelated deletion; the acceptance criterion is that Settings-driven paths do not call it.

- [ ] **Step 5: Run the focused tests again**

Run:

```bash
pytest -q tests/test_apply_settings.py::test_waybar_transaction_commits_without_reloading tests/test_apply_settings.py::test_live_sync_skips_waybar_reload_when_waybar_files_changed tests/test_apply_settings.py::test_apply_settings_has_no_waybar_reload_call_sites
```

Expected: PASS.

- [ ] **Step 6: Run the apply-settings tests**

Run:

```bash
pytest -q tests/test_apply_settings.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "fix(settings): defer waybar reloads"
```

---

### Task 2: Add Restart-Session Toasts For Waybar Saves

**Files:**
- Modify: `tests/test_settings_store.py`
- Modify: `files/usr/lib/adwaita-lite/settings/settings_store.py`

- [ ] **Step 1: Add failing success-toast coverage for Waybar-only saves**

Add this test after `test_save_and_apply_waybar_dispatches_detached_without_tracking` in `tests/test_settings_store.py`:

```python
def test_waybar_apply_reports_restart_session_message(monkeypatch, tmp_path):
    calls = []
    toasts = []

    class Proc:
        returncode = 0

        def communicate(self, timeout=None):
            raise AssertionError("detached waybar apply must not be waited on")

    monkeypatch.setattr(
        "settings.settings_store.subprocess.Popen",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or Proc(),
    )

    store = _make_store(tmp_path)
    store.set_toast_callback(lambda message, is_error: toasts.append((message, is_error)))
    store.save_and_apply("layout", {"start": [], "center": [], "end": []}, mode="waybar")

    assert calls[0][0] == ["/bin/true", "--mode", "waybar"]
    assert toasts == [(
        "Panel changes saved. Restart your session to apply them.",
        False,
    )]
```

- [ ] **Step 2: Add failing spawn-failure copy coverage**

Add this test after the success-toast test in `tests/test_settings_store.py`:

```python
def test_waybar_apply_spawn_failure_reports_file_update_error(monkeypatch, tmp_path):
    toasts = []

    def fail_popen(_cmd, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("settings.settings_store.subprocess.Popen", fail_popen)

    store = _make_store(tmp_path)
    store.set_toast_callback(lambda message, is_error: toasts.append((message, is_error)))
    store.save_and_apply("layout", {"start": [], "center": [], "end": []}, mode="waybar")

    assert toasts == [(
        "Panel changes saved, but panel files could not be updated: boom",
        True,
    )]
    assert store._last_apply_spawn_failed is True
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:

```bash
pytest -q tests/test_settings_store.py::test_waybar_apply_reports_restart_session_message tests/test_settings_store.py::test_waybar_apply_spawn_failure_reports_file_update_error
```

Expected: FAIL. The first test fails because the detached Waybar path currently shows no success toast. The second test fails because the current error text is `Saved, but failed to apply panel changes: {detail}`.

- [ ] **Step 4: Update detached Waybar apply messaging**

In `files/usr/lib/adwaita-lite/settings/settings_store.py`, update `_run_waybar_apply_detached()` to:

```python
    def _run_waybar_apply_detached(self) -> None:
        command = [self._apply_script, "--mode", "waybar"]
        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            self._last_apply_spawn_failed = True
            if self._toast_callback:
                detail = str(exc) or exc.__class__.__name__
                self._toast_callback(
                    _(
                        "Panel changes saved, but panel files could not be updated: {detail}"
                    ).format(detail=detail),
                    True,
                )
            return
        self._last_apply_spawn_failed = False
        if self._toast_callback:
            self._toast_callback(
                _("Panel changes saved. Restart your session to apply them."),
                False,
            )
```

- [ ] **Step 5: Run the focused tests again**

Run:

```bash
pytest -q tests/test_settings_store.py::test_waybar_apply_reports_restart_session_message tests/test_settings_store.py::test_waybar_apply_spawn_failure_reports_file_update_error
```

Expected: PASS.

- [ ] **Step 6: Run SettingsStore tests**

Run:

```bash
pytest -q tests/test_settings_store.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

Run:

```bash
git add files/usr/lib/adwaita-lite/settings/settings_store.py tests/test_settings_store.py
git commit -m "fix(settings): explain deferred panel applies"
```

---

### Task 3: Add Persistent Restart Notices To Panel-Affecting UI

**Files:**
- Modify: `tests/test_settings_app_logic.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/appearance.py`

- [ ] **Step 1: Add failing Panel-page notice coverage**

Add this test after `test_panel_sanitize_layout_filters_unknowns_and_duplicates` in `tests/test_settings_app_logic.py`:

```python
def test_panel_page_shows_restart_session_notice():
    source = Path(panel.__file__).read_text(encoding="utf-8")
    position_body = source.split("def _build_position_group", 1)[1].split(
        "def _build_density_group", 1
    )[0]

    assert 'PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")' in source
    assert "group.set_description(PANEL_RESTART_NOTICE)" in position_body
```

- [ ] **Step 2: Add failing Appearance accent notice coverage**

Add this test after `test_accent_change_applies_with_waybar_mode` in `tests/test_settings_app_logic.py`:

```python
def test_appearance_accent_shows_panel_restart_session_notice():
    source = Path(appearance.__file__).read_text(encoding="utf-8")
    accent_body = source.split("# -- Group 2: Accent color --", 1)[1].split(
        "# -- Group 3: Font size --", 1
    )[0]

    assert 'PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")' in source
    assert "accent_group.set_description(PANEL_RESTART_NOTICE)" in accent_body
```

- [ ] **Step 3: Run the focused tests to verify they fail**

Run:

```bash
pytest -q tests/test_settings_app_logic.py::test_panel_page_shows_restart_session_notice tests/test_settings_app_logic.py::test_appearance_accent_shows_panel_restart_session_notice
```

Expected: FAIL because neither page declares or displays `PANEL_RESTART_NOTICE` yet.

- [ ] **Step 4: Add the Panel page notice**

In `files/usr/lib/adwaita-lite/settings/pages/panel.py`, add this constant after `DENSITY_OPTIONS`:

```python
PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")
```

In `_build_position_group()`, after `group.set_title(_("Position"))`, add:

```python
        group.set_description(PANEL_RESTART_NOTICE)
```

- [ ] **Step 5: Add the Appearance accent notice**

In `files/usr/lib/adwaita-lite/settings/pages/appearance.py`, add this constant before `class AppearancePage`:

```python
PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")
```

In `AppearancePage.build()`, after `accent_group.set_title(_("Accent color"))`, add:

```python
        accent_group.set_description(PANEL_RESTART_NOTICE)
```

- [ ] **Step 6: Run the focused tests again**

Run:

```bash
pytest -q tests/test_settings_app_logic.py::test_panel_page_shows_restart_session_notice tests/test_settings_app_logic.py::test_appearance_accent_shows_panel_restart_session_notice
```

Expected: PASS.

- [ ] **Step 7: Run Settings app logic tests**

Run:

```bash
pytest -q tests/test_settings_app_logic.py
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add files/usr/lib/adwaita-lite/settings/pages/panel.py files/usr/lib/adwaita-lite/settings/pages/appearance.py tests/test_settings_app_logic.py
git commit -m "fix(settings): show panel restart notice"
```

---

### Task 4: Update Settings Translations

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

- [ ] **Step 1: Refresh Settings POT and PO catalogs**

Run:

```bash
make -C po pot-settings po-settings
```

Expected: `po/settings/adwaita-lite-settings.pot` contains these msgids, and every `po/settings/*.po` contains matching untranslated entries:

```po
msgid "Panel changes saved. Restart your session to apply them."
msgstr ""

msgid "Panel changes saved, but panel files could not be updated: {detail}"
msgstr ""

msgid "Panel changes apply after you restart your session."
msgstr ""
```

- [ ] **Step 2: Fill every new PO entry using this translation table**

For the `Panel changes saved. Restart your session to apply them.` entry, use these `msgstr` values:

| Locale | msgstr |
| --- | --- |
| `am` | `የፓነል ለውጦች ተቀምጠዋል። እነሱን ለመተግበር ክፍለ-ጊዜዎን እንደገና ያስጀምሩ።` |
| `ar` | `تم حفظ تغييرات اللوحة. أعد تشغيل جلستك لتطبيقها.` |
| `de` | `Panel-Änderungen gespeichert. Starten Sie Ihre Sitzung neu, um sie anzuwenden.` |
| `es` | `Cambios del panel guardados. Reinicia tu sesión para aplicarlos.` |
| `fa` | `تغییرات پنل ذخیره شد. برای اعمال آن‌ها نشست خود را دوباره راه‌اندازی کنید.` |
| `fr` | `Modifications du panneau enregistrées. Redémarrez votre session pour les appliquer.` |
| `ha` | `An ajiye canje-canjen fanel. Sake fara zaman ka don aiwatar da su.` |
| `hi` | `पैनल बदलाव सहेजे गए। उन्हें लागू करने के लिए अपना सत्र फिर से शुरू करें।` |
| `it` | `Modifiche al pannello salvate. Riavvia la sessione per applicarle.` |
| `ja` | `パネルの変更を保存しました。適用するにはセッションを再起動してください。` |
| `ko` | `패널 변경 사항을 저장했습니다. 적용하려면 세션을 다시 시작하세요.` |
| `nl` | `Paneelwijzigingen opgeslagen. Start uw sessie opnieuw om ze toe te passen.` |
| `pl` | `Zmiany panelu zapisane. Uruchom ponownie sesję, aby je zastosować.` |
| `pt` | `Alterações do painel salvas. Reinicie a sessão para aplicá-las.` |
| `ru` | `Изменения панели сохранены. Перезапустите сеанс, чтобы применить их.` |
| `sv` | `Paneländringarna har sparats. Starta om sessionen för att tillämpa dem.` |
| `sw` | `Mabadiliko ya paneli yamehifadhiwa. Anzisha upya kipindi chako ili kuyatumia.` |
| `th` | `บันทึกการเปลี่ยนแปลงแผงแล้ว รีสตาร์ทเซสชันของคุณเพื่อใช้การเปลี่ยนแปลง` |
| `tr` | `Panel değişiklikleri kaydedildi. Uygulamak için oturumunuzu yeniden başlatın.` |
| `vi` | `Đã lưu các thay đổi bảng điều khiển. Khởi động lại phiên của bạn để áp dụng chúng.` |
| `yo` | `Àwọn àyípadà pánẹ́ẹ̀lì ti fipamọ́. Tun ìgbà iṣẹ́ rẹ bẹ̀rẹ̀ láti lò wọ́n.` |
| `zh` | `面板更改已保存。请重新启动会话以应用它们。` |

For the `Panel changes saved, but panel files could not be updated: {detail}` entry, use these `msgstr` values and preserve `{detail}` exactly:

| Locale | msgstr |
| --- | --- |
| `am` | `የፓነል ለውጦች ተቀምጠዋል፣ ግን የፓነል ፋይሎች ሊዘመኑ አልቻሉም፦ {detail}` |
| `ar` | `تم حفظ تغييرات اللوحة، لكن تعذّر تحديث ملفات اللوحة: {detail}` |
| `de` | `Panel-Änderungen gespeichert, aber die Panel-Dateien konnten nicht aktualisiert werden: {detail}` |
| `es` | `Cambios del panel guardados, pero no se pudieron actualizar los archivos del panel: {detail}` |
| `fa` | `تغییرات پنل ذخیره شد، اما پرونده‌های پنل به‌روزرسانی نشدند: {detail}` |
| `fr` | `Modifications du panneau enregistrées, mais les fichiers du panneau n'ont pas pu être mis à jour : {detail}` |
| `ha` | `An ajiye canje-canjen fanel, amma ba a iya sabunta fayilolin fanel ba: {detail}` |
| `hi` | `पैनल बदलाव सहेजे गए, लेकिन पैनल फ़ाइलें अपडेट नहीं की जा सकीं: {detail}` |
| `it` | `Modifiche al pannello salvate, ma non è stato possibile aggiornare i file del pannello: {detail}` |
| `ja` | `パネルの変更を保存しましたが、パネルファイルを更新できませんでした: {detail}` |
| `ko` | `패널 변경 사항을 저장했지만 패널 파일을 업데이트할 수 없습니다: {detail}` |
| `nl` | `Paneelwijzigingen opgeslagen, maar de paneelbestanden konden niet worden bijgewerkt: {detail}` |
| `pl` | `Zmiany panelu zapisane, ale nie udało się zaktualizować plików panelu: {detail}` |
| `pt` | `Alterações do painel salvas, mas não foi possível atualizar os arquivos do painel: {detail}` |
| `ru` | `Изменения панели сохранены, но не удалось обновить файлы панели: {detail}` |
| `sv` | `Paneländringarna har sparats, men panelfilerna kunde inte uppdateras: {detail}` |
| `sw` | `Mabadiliko ya paneli yamehifadhiwa, lakini faili za paneli hazikuweza kusasishwa: {detail}` |
| `th` | `บันทึกการเปลี่ยนแปลงแผงแล้ว แต่ไม่สามารถอัปเดตไฟล์แผงได้: {detail}` |
| `tr` | `Panel değişiklikleri kaydedildi, ancak panel dosyaları güncellenemedi: {detail}` |
| `vi` | `Đã lưu các thay đổi bảng điều khiển, nhưng không thể cập nhật tệp bảng điều khiển: {detail}` |
| `yo` | `Àwọn àyípadà pánẹ́ẹ̀lì ti fipamọ́, ṣùgbọ́n a kò lè ṣe imudojuiwọn àwọn fáìlì pánẹ́ẹ̀lì: {detail}` |
| `zh` | `面板更改已保存，但无法更新面板文件：{detail}` |

For the `Panel changes apply after you restart your session.` entry, use these `msgstr` values:

| Locale | msgstr |
| --- | --- |
| `am` | `የፓነል ለውጦች ክፍለ-ጊዜዎን እንደገና ካስጀመሩ በኋላ ይተገበራሉ።` |
| `ar` | `تُطبق تغييرات اللوحة بعد إعادة تشغيل جلستك.` |
| `de` | `Panel-Änderungen werden nach dem Neustart Ihrer Sitzung angewendet.` |
| `es` | `Los cambios del panel se aplican después de reiniciar tu sesión.` |
| `fa` | `تغییرات پنل پس از راه‌اندازی دوباره نشست شما اعمال می‌شوند.` |
| `fr` | `Les modifications du panneau s'appliquent après le redémarrage de votre session.` |
| `ha` | `Canje-canjen fanel suna aiki bayan ka sake fara zaman ka.` |
| `hi` | `पैनल बदलाव आपका सत्र फिर से शुरू करने के बाद लागू होते हैं।` |
| `it` | `Le modifiche al pannello si applicano dopo il riavvio della sessione.` |
| `ja` | `パネルの変更はセッションの再起動後に適用されます。` |
| `ko` | `패널 변경 사항은 세션을 다시 시작한 후 적용됩니다.` |
| `nl` | `Paneelwijzigingen worden toegepast nadat u uw sessie opnieuw start.` |
| `pl` | `Zmiany panelu zostaną zastosowane po ponownym uruchomieniu sesji.` |
| `pt` | `As alterações do painel são aplicadas depois que você reinicia a sessão.` |
| `ru` | `Изменения панели применяются после перезапуска сеанса.` |
| `sv` | `Paneländringar tillämpas efter att du startar om sessionen.` |
| `sw` | `Mabadiliko ya paneli hutumika baada ya kuanzisha upya kipindi chako.` |
| `th` | `การเปลี่ยนแปลงแผงจะมีผลหลังจากคุณรีสตาร์ทเซสชัน` |
| `tr` | `Panel değişiklikleri oturumunuzu yeniden başlattıktan sonra uygulanır.` |
| `vi` | `Các thay đổi bảng điều khiển sẽ áp dụng sau khi bạn khởi động lại phiên.` |
| `yo` | `Àwọn àyípadà pánẹ́ẹ̀lì máa ṣiṣẹ lẹ́yìn tí o bá tún ìgbà iṣẹ́ rẹ bẹ̀rẹ̀.` |
| `zh` | `面板更改会在您重新启动会话后应用。` |

- [ ] **Step 3: Rebuild compiled Settings catalogs**

Run:

```bash
make -C po mo-settings
```

Expected: `files/usr/share/locale/<lang>/LC_MESSAGES/adwaita-lite-settings.mo` is updated for every language listed in `po/Makefile`.

- [ ] **Step 4: Run translation catalog tests**

Run:

```bash
pytest -q tests/test_translation_catalogs.py
```

Expected: PASS. If this fails, fix the exact PO entry reported by the test before continuing.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add po/settings files/usr/share/locale
git commit -m "i18n(settings): translate deferred panel apply notice"
```

---

### Task 5: Final Verification And Integration

**Files:**
- Verify: repository working tree

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
pytest -q tests/test_apply_settings.py::test_waybar_transaction_commits_without_reloading tests/test_apply_settings.py::test_live_sync_skips_waybar_reload_when_waybar_files_changed tests/test_apply_settings.py::test_apply_settings_has_no_waybar_reload_call_sites tests/test_settings_store.py::test_waybar_apply_reports_restart_session_message tests/test_settings_store.py::test_waybar_apply_spawn_failure_reports_file_update_error tests/test_settings_app_logic.py::test_panel_page_shows_restart_session_notice tests/test_settings_app_logic.py::test_appearance_accent_shows_panel_restart_session_notice
```

Expected: PASS.

- [ ] **Step 2: Run full focused files**

Run:

```bash
pytest -q tests/test_apply_settings.py tests/test_settings_store.py tests/test_settings_app_logic.py tests/test_translation_catalogs.py
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run:

```bash
pytest -q
```

Expected: PASS. The known `PyGIDeprecationWarning: GLib.unix_signal_add_full is deprecated; use GLibUnix.signal_add_full instead` may appear and is not part of this task.

- [ ] **Step 4: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Confirm no Settings path calls Waybar reload**

Run:

```bash
python - <<'PY'
from pathlib import Path
source = Path('files/usr/libexec/adwaita-lite-apply-settings').read_text(encoding='utf-8')
call_sites = [
    line for line in source.splitlines()
    if 'reload_waybar()' in line and not line.lstrip().startswith('def reload_waybar')
]
assert call_sites == [], call_sites
PY
```

Expected: no output and exit code 0.

- [ ] **Step 6: Review final git state**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: no unstaged implementation changes. Recent commits should include the Task 1 through Task 4 commits.

- [ ] **Step 7: Push main after verification**

Run:

```bash
git push origin main
```

Expected: push succeeds.

---

## Manual Verification On The Affected Desktop

After the pushed build is available, verify the behavior in the labwc session that reproduced the bug:

- Launch Settings from the start menu and change Panel position, density, twilight, module layout, and pinned apps.
- Launch Settings from a terminal and repeat one Panel change.
- Change Appearance accent color.
- Confirm Settings stays open.
- Confirm the launching terminal stays open.
- Confirm Waybar does not reload immediately.
- Confirm Settings shows `Panel changes saved. Restart your session to apply them.` for panel-affecting changes.
- Restart the session and confirm the saved panel config appears.
