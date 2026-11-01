import importlib.machinery
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-goblin"


def _load_goblin():
    loader = importlib.machinery.SourceFileLoader("adwaita_lite_goblin", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
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


class FakeScreen:
    def __init__(self, height, width, keys=()):
        self.height = height
        self.width = width
        self.keys = list(keys)
        self.writes = []
        self.erased = False

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.erased = True

    def addstr(self, y, x, text):
        if y < 0 or y >= self.height or x < 0 or x >= self.width:
            raise AssertionError("write outside screen")
        if y == self.height - 1 and x + len(text) >= self.width:
            raise AssertionError("text touched lower-right curses cell")
        if x + len(text) > self.width:
            raise AssertionError("text overflowed screen width")
        self.writes.append((y, x, text))

    def addch(self, y, x, char):
        if y < 0 or y >= self.height or x < 0 or x >= self.width:
            raise AssertionError("character outside screen")
        if y == self.height - 1 and x == self.width - 1:
            raise AssertionError("character touched lower-right curses cell")
        self.writes.append((y, x, char))

    def refresh(self):
        pass

    def getch(self):
        return self.keys.pop(0) if self.keys else ord("q")


def test_safe_addstr_truncates_and_skips_out_of_bounds_writes():
    goblin = _load_goblin()
    screen = FakeScreen(height=2, width=8)

    goblin.safe_addstr(screen, 0, 0, "goblin-mode")
    goblin.safe_addstr(screen, 3, 0, "ignored")
    goblin.safe_addstr(screen, 1, 8, "ignored")

    assert screen.writes == [(0, 0, "goblin-m")]


def test_safe_addstr_avoids_lower_right_curses_cell():
    goblin = _load_goblin()
    screen = FakeScreen(height=2, width=8)

    goblin.safe_addstr(screen, 1, 0, "goblin-mode")

    assert screen.writes == [(1, 0, "goblin-")]


def test_too_small_screen_message_does_not_overflow_tiny_terminal():
    goblin = _load_goblin()
    screen = FakeScreen(height=1, width=12, keys=[ord("q")])

    goblin._too_small(screen)

    assert screen.writes == [(0, 0, "Goblin Mode")]


def test_size_gate_matches_advertised_minimum():
    goblin = _load_goblin()

    assert goblin.screen_too_small(width=49, height=22)
    assert goblin.screen_too_small(width=50, height=21)
    assert not goblin.screen_too_small(width=50, height=22)


def test_help_screen_truncates_to_terminal_width():
    goblin = _load_goblin()
    screen = FakeScreen(height=22, width=50, keys=[ord("q")])

    goblin.show_help(screen)

    assert screen.writes
    assert all(x + len(text) <= screen.width for _, x, text in screen.writes)


def test_draw_is_safe_at_advertised_minimum_terminal_size():
    goblin = _load_goblin()
    state = goblin.new_game(width=49, height=19, seed=17)
    screen = FakeScreen(height=22, width=50)

    goblin.draw(screen, state)

    assert screen.writes


def test_using_stairs_on_final_floor_wins_game():
    goblin = _load_goblin()
    state = goblin.new_game(width=50, height=22, seed=11)
    state.depth = goblin.MAX_DEPTH
    state.floor.enemies.clear()
    stairs = state.floor.stairs
    state.player = goblin.Point(stairs.x - 1, stairs.y)

    result = goblin.move_player(state, 1, 0)

    assert result == "You recover the golden image. Ship it."
    assert state.won
