# Night Shift

An asset-free, modular zombie survival game for **Pyxel 2.x**. The game starts
directly in play at 256x144. The world is larger than the camera, enemies are
auto-targeted, and all moving simulation uses a clamped `time.perf_counter()`
delta time.

## Run

```sh
python -m pip install -r requirements.txt
python main.py
pytest -q
```

## Controls

* **WASD / arrows** - move
* **E near the SHOP marker** - open/close merchant
* **1-5 in merchant** - heal, damage, speed, pickup magnet, multishot
* **1-3 on level up** - choose damage, speed, or magnet ability
* **R** - restart after death
* **F2** - toggle 3x demo rewards; **F3** - developer overlay
* **F4** - grant 50 XP and 100 gold

The game starts immediately in the city. The HUD shows survival time as
`mm:ss`, XP, level, gems, gold, health, and score. F4 is a development grant:
it adds 50 XP and 100 gold. **U** opens the permanent upgrades menu anywhere
outside the merchant. Merchant access is strictly proximity-only: stand near
the SHOP marker and press E. Gold and XP gems are separate magnetized pickups.
Press F2 to enable demo mode; zombie drops then provide 3x XP, gems, and gold.

Zombies drop gems that are automatically collected within the magnet radius.
Each zombie has a 10% chance to drop an XP gem; gems grant XP and each level
pauses gameplay briefly for an ability choice.
Rendering is procedural, and `render.assets.load_assets()` provides a sprite
registry ready for replacing placeholders with image assets.
