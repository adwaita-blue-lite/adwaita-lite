# DX Goblin Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DX-only `ujust goblin` easter egg that launches a compact terminal roguelike with reliable room-and-corridor procedural generation.

**Architecture:** Implement the game as one executable Python 3 script with pure generation/game-state helpers above a small `curses` UI loop. Keep the shell integration in the existing DX justfile and validate the DX contract through static tests plus non-interactive Python unit tests for map generation.

**Tech Stack:** Python 3 standard library (`curses`, `dataclasses`, `random`, `collections`), Just/ujust recipes, pytest.

---

## File Structure

- Create: `files/usr/bin/adwaita-lite-goblin`
  - Executable Python script.
  - Owns procedural generation, turn resolution, rendering, controls, and terminal-size fallback.
  - Exposes pure helpers (`generate_floor`, `reachable_tiles`, `new_game`, `move_player`, `enemy_turn`) so tests can load it without starting curses.
- Modify: `files/usr/share/ublue-os/just/90-adwaita-lite.just`
  - Add a DX-only `goblin` recipe that runs `/usr/bin/adwaita-lite-goblin`.
- Modify: `tests/test_dx_payload.py`
  - Assert the DX payload includes the goblin script and `ujust goblin` recipe.
- Create: `tests/test_goblin_mode.py`
  - Load the executable script as a Python module and test generation/reachability/combat helpers without curses.

## Task 1: Add Failing DX Contract Tests

**Files:**
- Modify: `tests/test_dx_payload.py`

- [ ] **Step 1: Add the failing DX payload test**

Add this test near the existing DX file/recipe tests:

```python
def test_dx_includes_goblin_mode_easter_egg():
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")

    assert (ROOT / "files/usr/bin/adwaita-lite-goblin").exists()
    assert "goblin:" in justfile
    assert "/usr/bin/adwaita-lite-goblin" in justfile
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/test_dx_payload.py::test_dx_includes_goblin_mode_easter_egg -v`

Expected: FAIL because `files/usr/bin/adwaita-lite-goblin` does not exist yet.

## Task 2: Add Pure Generator Tests

**Files:**
- Create: `tests/test_goblin_mode.py`

- [ ] **Step 1: Create non-interactive tests for the script module**

Create `tests/test_goblin_mode.py` with this content:

```python
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-goblin"


def _load_goblin():
    spec = importlib.util.spec_from_file_location("adwaita_lite_goblin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generated_floor_is_connected_and_places_stairs_far_from_start():
    goblin = _load_goblin()

    floor = goblin.generate_floor(width=50, height=22, depth=3, seed=1234)
    reachable = goblin.reachable_tiles(floor.tiles, floor.start)

    assert floor.start in reachable
    assert floor.stairs in reachable
    assert floor.stairs != floor.start
    assert goblin.manhattan(floor.start, floor.stairs) >= 15
    assert len(floor.rooms) >= 6

    for enemy in floor.enemies:
        assert enemy.pos in reachable
        assert enemy.pos not in floor.start_room.tiles()

    for loot in floor.loot:
        assert loot in reachable
        assert loot not in floor.start_room.tiles()


def test_generation_is_deterministic_for_seed():
    goblin = _load_goblin()

    one = goblin.generate_floor(width=50, height=22, depth=2, seed=99)
    two = goblin.generate_floor(width=50, height=22, depth=2, seed=99)

    assert one.tiles == two.tiles
    assert one.start == two.start
    assert one.stairs == two.stairs
    assert [(enemy.kind, enemy.pos) for enemy in one.enemies] == [
        (enemy.kind, enemy.pos) for enemy in two.enemies
    ]
    assert one.loot == two.loot


def test_bump_combat_defeats_enemy_and_preserves_player_position():
    goblin = _load_goblin()
    state = goblin.new_game(width=50, height=22, seed=7)
    enemy = state.floor.enemies[0]
    state.player = goblin.Point(enemy.pos.x - 1, enemy.pos.y)
    enemy.hp = 1

    result = goblin.move_player(state, 1, 0)

    assert result == "You bonk the goblin."
    assert state.player == goblin.Point(enemy.pos.x - 1, enemy.pos.y)
    assert enemy not in state.floor.enemies
```

- [ ] **Step 2: Run the tests and verify they fail before implementation**

Run: `pytest tests/test_goblin_mode.py -v`

Expected: FAIL because `files/usr/bin/adwaita-lite-goblin` does not exist yet.

## Task 3: Implement Generator and Game State Helpers

**Files:**
- Create: `files/usr/bin/adwaita-lite-goblin`

- [ ] **Step 1: Add the executable Python script**

Create `files/usr/bin/adwaita-lite-goblin` with a shebang and these public helpers/classes:

```python
#!/usr/bin/env python3
from __future__ import annotations

import curses
import random
from collections import deque
from dataclasses import dataclass, field


WALL = "#"
FLOOR = "."
STAIRS = ">"
PLAYER = "@"
LOOT = "$"


@dataclass(frozen=True, order=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> Point:
        return Point(self.x + self.width // 2, self.y + self.height // 2)

    def intersects(self, other: "Room") -> bool:
        return not (
            self.x + self.width + 1 < other.x
            or other.x + other.width + 1 < self.x
            or self.y + self.height + 1 < other.y
            or other.y + other.height + 1 < self.y
        )

    def tiles(self) -> set[Point]:
        return {
            Point(x, y)
            for y in range(self.y, self.y + self.height)
            for x in range(self.x, self.x + self.width)
        }


@dataclass
class Enemy:
    kind: str
    pos: Point
    hp: int
    damage: int


@dataclass
class Floor:
    tiles: list[list[str]]
    rooms: list[Room]
    start_room: Room
    start: Point
    stairs: Point
    enemies: list[Enemy]
    loot: set[Point]


@dataclass
class GameState:
    width: int
    height: int
    seed: int
    depth: int = 1
    hp: int = 12
    scraps: int = 0
    won: bool = False
    lost: bool = False
    message: str = "Recover the golden image."
    player: Point = field(default_factory=lambda: Point(0, 0))
    floor: Floor | None = None


def manhattan(a: Point, b: Point) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def carve_room(tiles: list[list[str]], room: Room) -> None:
    for point in room.tiles():
        tiles[point.y][point.x] = FLOOR


def carve_corridor(tiles: list[list[str]], start: Point, end: Point, rng: random.Random) -> None:
    if rng.choice((True, False)):
        corners = (Point(end.x, start.y),)
    else:
        corners = (Point(start.x, end.y),)
    path = (start, *corners, end)
    for current, target in zip(path, path[1:]):
        x_step = 1 if target.x >= current.x else -1
        for x in range(current.x, target.x + x_step, x_step):
            tiles[current.y][x] = FLOOR
        y_step = 1 if target.y >= current.y else -1
        for y in range(current.y, target.y + y_step, y_step):
            tiles[y][target.x] = FLOOR


def reachable_tiles(tiles: list[list[str]], start: Point) -> set[Point]:
    seen = {start}
    queue = deque([start])
    while queue:
        point = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = Point(point.x + dx, point.y + dy)
            if nxt in seen:
                continue
            if tiles[nxt.y][nxt.x] == WALL:
                continue
            seen.add(nxt)
            queue.append(nxt)
    return seen
```

Implement `generate_floor`, `new_game`, `move_player`, and `enemy_turn` in the same script using the spec rules: 6-10 rooms, connected L-corridors, flood-fill validation, farthest reachable stairs, floor-scaled enemy/loot placement, and deterministic seeds.

- [ ] **Step 2: Make the script executable**

Run: `chmod +x files/usr/bin/adwaita-lite-goblin`

Expected: command exits 0.

- [ ] **Step 3: Run generator tests**

Run: `pytest tests/test_goblin_mode.py -v`

Expected: PASS.

## Task 4: Add Curses UI Loop

**Files:**
- Modify: `files/usr/bin/adwaita-lite-goblin`

- [ ] **Step 1: Add rendering and controls**

Add functions named `draw`, `show_help`, `run`, and `main`. `main` must only call `curses.wrapper(run)` under `if __name__ == "__main__":` so test imports do not start curses.

Required control mapping:

```python
MOVE_KEYS = {
    ord("w"): (0, -1),
    ord("a"): (-1, 0),
    ord("s"): (0, 1),
    ord("d"): (1, 0),
    curses.KEY_UP: (0, -1),
    curses.KEY_LEFT: (-1, 0),
    curses.KEY_DOWN: (0, 1),
    curses.KEY_RIGHT: (1, 0),
}
```

`run` must enforce minimum terminal dimensions of 50 columns by 22 rows. If smaller, draw `Goblin Mode needs at least 50x22.` and wait for `q` or Escape.

- [ ] **Step 2: Run syntax and import checks**

Run: `python3 -m py_compile files/usr/bin/adwaita-lite-goblin`

Expected: PASS with no output.

Run: `pytest tests/test_goblin_mode.py -v`

Expected: PASS.

## Task 5: Wire Into DX ujust Recipes

**Files:**
- Modify: `files/usr/share/ublue-os/just/90-adwaita-lite.just`

- [ ] **Step 1: Add the `goblin` recipe**

Append this recipe after `dx-group`:

```just
# Launch the DX-only Goblin Mode easter egg.
goblin:
    /usr/bin/adwaita-lite-goblin
```

- [ ] **Step 2: Run contract tests**

Run: `pytest tests/test_dx_payload.py::test_dx_includes_goblin_mode_easter_egg -v`

Expected: PASS.

Run: `just --unstable --fmt --check -f files/usr/share/ublue-os/just/90-adwaita-lite.just`

Expected: PASS.

## Task 6: Final Verification

**Files:**
- Verify only; no new files.

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/test_goblin_mode.py tests/test_dx_payload.py -v`

Expected: PASS.

- [ ] **Step 2: Run broader branch-relevant tests**

Run: `pytest tests/test_branch_channels.py tests/test_dx_payload.py tests/test_goblin_mode.py -v`

Expected: PASS.

- [ ] **Step 3: Run static checks**

Run: `python3 -m py_compile files/usr/bin/adwaita-lite-goblin`

Expected: PASS.

Run: `git diff --check`

Expected: PASS with no output.

## Self-Review

- Spec coverage: The plan covers DX-only entry point, Python curses implementation, 5-floor roguelike scope, modern controls, no extra dependencies, refined room/corridor generation, flood-fill validation, terminal-size fallback, and static/pure tests.
- Placeholder scan: The only intentionally flexible implementation detail is the full body of the game script inside Task 3/4, because the exact script is generated during implementation and then verified by concrete tests. There are no TBD/TODO markers.
- Type consistency: The plan consistently uses `Point`, `Room`, `Enemy`, `Floor`, `GameState`, `generate_floor`, `reachable_tiles`, `new_game`, `move_player`, and `enemy_turn`.

## Commit Note

Do not commit unless the user explicitly requests it. If asked to commit after verification, stage only the goblin-mode spec, plan, script, tests, and justfile changes.
