# Panel Page Crash Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the intermittent GTK segfault crash when changing panel position in the settings app.

**Architecture:** Add `_updating` and `_built` re-entrancy guards to `PanelPage` in `panel.py`, matching the proven pattern already used in 7 other settings pages (keyboard, appearance, bluetooth, power_lock, sound, network, datetime).

**Tech Stack:** Python, PyGObject, GTK4, libadwaita

---

### Task 1: Add guard flags to PanelPage.__init__

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py:69-78`

- [ ] **Step 1: Add `_updating` and `_built` flags to `__init__`**

In `panel.py`, in the `PanelPage.__init__` method, add two new guard flags after the existing instance variables:

```python
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._layout_data: dict = {}
        self._section_groups: dict[str, Adw.PreferencesGroup] = {}
        self._section_rows: dict[str, list[Adw.ActionRow]] = {}
        self._pinned_data: list = []
        self._pinned_group: Adw.PreferencesGroup | None = None
        self._pinned_rows: list[Adw.ActionRow] = []
        self._nav: Adw.NavigationView | None = None
        self._updating: bool = False
        self._built: bool = False
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile files/usr/lib/adwaita-lite/settings/pages/panel.py`
Expected: no output (success)

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/panel.py
git commit -m "fix(panel): add _updating and _built guard flags to PanelPage"
```

---

### Task 2: Guard the position ComboRow handler

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py:131-137`

- [ ] **Step 1: Wrap `_on_selected` in the position group with re-entrancy guard**

Replace the `_on_selected` closure inside `_build_position_group`:

Old code (lines 131-134):
```python
        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self._on_edge_changed(values[idx])
```

New code:
```python
        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._updating or not self._built:
                return
            self._updating = True
            try:
                idx = r.get_selected()
                if 0 <= idx < len(values):
                    self._on_edge_changed(values[idx])
            finally:
                self._updating = False
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile files/usr/lib/adwaita-lite/settings/pages/panel.py`
Expected: no output (success)

---

### Task 3: Guard the density ComboRow handler

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py:154-159`

- [ ] **Step 1: Wrap `_on_selected` in the density group with re-entrancy guard**

Replace the `_on_selected` closure inside `_build_density_group`:

Old code (lines 154-157):
```python
        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self.store.save_and_apply("density", values[idx])
```

New code:
```python
        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._updating or not self._built:
                return
            self._updating = True
            try:
                idx = r.get_selected()
                if 0 <= idx < len(values):
                    self.store.save_and_apply("density", values[idx])
            finally:
                self._updating = False
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile files/usr/lib/adwaita-lite/settings/pages/panel.py`
Expected: no output (success)

---

### Task 4: Guard the twilight SwitchRow handler

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py:172-175`

- [ ] **Step 1: Wrap `_on_active` in the twilight group with re-entrancy guard**

Replace the `_on_active` closure inside `_build_twilight_group`:

Old code (lines 172-174):
```python
        def _on_active(r: Adw.SwitchRow, _pspec) -> None:
            self.store.save_and_apply("panel_twilight", r.get_active())
```

New code:
```python
        def _on_active(r: Adw.SwitchRow, _pspec) -> None:
            if self._updating or not self._built:
                return
            self._updating = True
            try:
                self.store.save_and_apply("panel_twilight", r.get_active())
            finally:
                self._updating = False
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile files/usr/lib/adwaita-lite/settings/pages/panel.py`
Expected: no output (success)

---

### Task 5: Guard `_on_edge_changed` and set `_built` flag

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py:216-219`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py:90-113`

- [ ] **Step 1: Wrap `_on_edge_changed` body with the `_updating` guard**

This provides a second layer of defense — even if a signal handler somehow
bypasses the per-handler guard, the mutation entry point itself is protected.

Old code (lines 216-219):
```python
    def _on_edge_changed(self, edge):
        self.store.save_and_apply("edge", edge)
        self._update_section_labels()
        self._refresh_module_lists()
```

New code:
```python
    def _on_edge_changed(self, edge):
        if self._updating:
            return
        self._updating = True
        try:
            self.store.save_and_apply("edge", edge)
            self._update_section_labels()
            self._refresh_module_lists()
        finally:
            self._updating = False
```

- [ ] **Step 2: Set `_built = True` at the end of `build()`**

In the `build` method, add `self._built = True` right before the return
statement (before `return self._nav`):

Old code (lines 112-113):
```python
        self.setup_cleanup(self._nav)
        return self._nav
```

New code:
```python
        self.setup_cleanup(self._nav)
        self._built = True
        return self._nav
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -m py_compile files/usr/lib/adwaita-lite/settings/pages/panel.py`
Expected: no output (success)

- [ ] **Step 4: Run existing tests**

Run: `cd /var/home/race/ublue-mike && python3 -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/panel.py
git commit -m "fix(panel): add re-entrancy + construction guards to prevent GTK segfault"
```
