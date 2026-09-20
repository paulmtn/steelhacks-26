# The Game of Job

A top-down survival roguelite built with **[Pyxel](https://github.com/kitao/pyxel) 2.x**. Auto-targeting
combat, a wave-based zombie horde that merges into tougher elites, an
in-run ability draft, a mobile shop van you can buy permanent upgrades
from (or get run over by), and a persistent, difficulty-weighted high
score.

You play at a fixed 256x144 resolution inside a 1024x1024 tile-based
world, framed by a light Job-and-Satan narrative: level-ups are staged as
trials to endure rather than plain power spikes.

## Features

- **Auto-fire combat** — no aiming; the player always targets the nearest
  visible zombie in range.
- **Two zombie archetypes** (slow/tanky "walkers", fast/fragile
  "runners") that **merge into "\_super" elites** — tougher, faster,
  double-damage variants — whenever three of the same type end up
  touching at once.
- **Eight level-up abilities** (Sharpshooter, Twin Shot, Thick Skin,
  Job's Orb, Hedge of Protection, Fire from Heaven, Morning Star,
  Storehouse of Hail), each stackable across a run.
- **A mobile shop van** with real BFS-flow-field pathfinding that drives
  to random spots, parks to sell four randomly chosen items for coins
  and gems, and otherwise drives through (and damages) anything in its
  way.
- **Permanent, cross-shop upgrades** (Damage, Vitality, Magnet) bought
  with coins via the upgrades menu.
- **A persisted, difficulty-weighted high score** — combined score
  (kills × current wave) is saved to disk between runs and shown live in
  the HUD as a fill-to-complete progress ring.
- **Hand-authored sprite sheets and sound effects** for the player,
  both zombie types, the shop van, and the tile-based world map — not
  placeholder art, though a procedural circle/color fallback still
  exists for anything that fails to load.
- **78 automated tests** (`pytest`) covering combat, movement,
  progression, shop AI, and scoring.

## Getting Started

### Requirements

- Python 3.10+
- [Pyxel](https://github.com/kitao/pyxel) 2.x, Pillow, and pytest (see
  `requirements.txt`)

### Install

```sh
python -m pip install -r requirements.txt
```

### Run

```sh
python main.py
```

### Test

```sh
pytest -q
```

## Controls

| Key(s)                | Action                                       |
| ---------------------- | --------------------------------------------- |
| `W A S D` / arrows     | Move                                          |
| `E` near the shop van  | Open/close the merchant                       |
| `1`–`4` in the merchant | Buy one of the four offered shop items        |
| `1`–`3` on level up    | Choose one of three offered abilities         |
| `U`                    | Open the permanent upgrades menu (outside the merchant) |
| `R`                    | Restart after death                           |
| `F2`                   | Toggle demo mode (3x kill rewards)            |
| `F3`                   | Toggle the developer overlay                  |
| `F4`                   | Debug grant: +50 XP, +100 gold                |

## Gameplay

### Combat & progression

The player auto-fires at the nearest visible zombie; movement is the
only manual input during combat. Every kill grants XP, and each level
pauses the game for a choice of three abilities, drawn from a pool of
eight. Abilities stack: a second "Job's Orb" pick adds a second orbiting
orb (up to five), a second "Fire from Heaven" adds a second simultaneous
lightning strike, and so on.

### Zombies

Zombies come in two base types — slow, tanky **walkers** and fast,
fragile **runners**. Whenever three zombies of the same base type are
all touching at once, they merge into a **"\_super" elite**: 3x health,
2x speed, 2x melee damage, a doubled hitbox, and (unique to supers)
ranged gunfire once they're close enough. Spawn rate and zombie speed
both scale up with survival time and wave.

### The shop van

A van with its own pathfinding drives between random spots on the map.
While parked, walk up and press `E` to browse four randomly selected
items (a mix of coin purchases like Medkits and Arsenal, and one-time
gem purchases like Extra Life and Double XP); repeat coin purchases get
10% more expensive each time. While driving, the van is a moving hazard
— getting hit halves your current health.

### Scoring & high score

Kills grant flat score, and `wave = 1 + score // 200` acts as a running
difficulty multiplier. The number actually chased for a high score is
**combined score** (`score × wave`), so surviving to a later, harder
wave makes every prior kill worth more — a pure kill-count race would
reward camping the easiest early waves instead. The all-time combined
score is saved to disk (`save.json`) and shown top-right as a ring: a
white arc fills in clockwise as the current run approaches it, closing
into a full circle (and flipping the score label from white to black)
once it's matched or beaten. A second, light-blue ring pulses outward
with every kill and steadily shrinks back down, giving a live read on
scoring pace at a glance.

## Project Structure

```
main.py               Entry point: Pyxel init, the frame loop, input handling
game/
  config.py           Tunable constants (speeds, timers, world size, ...)
  data.py             Static data: abilities, enemy types, shop items
  entities.py         Player / Zombie / Bullet / Particle / Pickup / Shop records
  state.py            Game-mode state machine, PlayerProgress, scoring
  pools.py            Fixed-capacity object pools (no per-frame allocation)
  save.py             Persisted high-score file I/O
  spatial_hash.py     Broad-phase collision grid
  tilemap.py          Tiled map loading, collision, BFS flow fields
  systems/
    combat.py         Firing, damage, beams, lightning, hail
    movement.py       Player/zombie movement and steering
    progression.py    XP, pickups, shop purchases, ability effects
    shop.py           Mobile shop van AI and pathing
    spawn.py          Zombie spawning and elite merging
render/
  draw.py             All rendering: world, HUD, and menu overlays
  assets.py           Sprite/sound loading and the fallback palette
  graphics/, sounds/  Art and audio assets
tests/
  test_game.py        Unit tests for every system above
```

## Acknowledgments

Built at **SteelHacks 2026** by Caden Karge and Paul Nguyen.
