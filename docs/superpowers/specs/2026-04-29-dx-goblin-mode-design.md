# DX Goblin Mode Design

## Goal

Add a DX-only easter egg that rewards discovery without affecting normal system behavior. The easter egg should feel like a tiny, complete roguelike rather than a static joke, while remaining small enough to audit and maintain.

## User Entry Point

`ujust goblin` launches `/usr/bin/adwaita-lite-goblin` on the DX stream. The command is intentionally DX-only; `latest` and `beta` do not include it, while `testing` inherits it from `dx`.

## Game Scope

The game is **Goblin Mode**, a compact terminal roguelike implemented with Python 3 standard-library `curses`.

- 5 procedural floors.
- HP, bump combat, scraps/loot, exit stairs, win and loss states.
- Theme: recover the golden image from a tiny dungeon before goblins and build imps get you.
- Controls: WASD/arrows to move, `.` to wait, `?` for help, `r` to restart after win/loss, and `q` to quit.
- No save files, config files, networking, or extra package dependencies.

## Procedural Generation

Each floor uses compact classic room generation.

- Generate 6-10 non-overlapping rectangular rooms.
- Sort rooms by center point and connect adjacent rooms with L-shaped corridors.
- Place the player in the first room and stairs in the farthest reachable room.
- Validate every generated floor with flood fill so the stairs, enemies, and loot are reachable.
- Place enemies and loot only on floor tiles outside the start room.
- Prefer placing rewards and stairs farther from the start using distance scoring.
- Scale danger by floor: later floors have more enemies and fewer safe placements.
- Retry generation on validation failure; if retries are exhausted, fall back to a simple guaranteed connected layout.
- If the terminal is too small, show a friendly message instead of crashing.

## Testing

Static tests should verify that the DX payload includes `/usr/bin/adwaita-lite-goblin`, exposes `ujust goblin`, and keeps the feature branch-local to DX payload expectations. The game should also expose enough pure functions for lightweight tests of map reachability and floor generation without requiring an interactive terminal.
