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
* **1-4 in merchant** - buy one of the four randomly selected shop items
* **1-3 on level up** - choose from the available abilities
* **R** - restart after death
* **F2** - toggle 3x demo rewards; **F3** - developer overlay
* **F4** - grant 50 XP and 100 gold

The game starts immediately in the city. The HUD shows survival time as
`mm:ss`, XP, level, gems, gold, health, and score. F4 is a development grant:
it adds 50 XP and 100 gold. **U** opens the permanent upgrades menu anywhere
outside the merchant. Merchant access is strictly proximity-only: stand near
the SHOP marker and press E. Gold and XP gems are separate magnetized pickups.
Press F2 to enable demo mode; zombie drops then provide 3x XP, gems, and gold.

The merchant randomly offers four items per run. Ten-stock coin items (Medkit,
Arsenal, and Boots) each
purchase increases that item's coin price by 10%. Boots increase movement speed
by 3%. Extra Life and Double XP cost gems and are each available once per run.
Extra Life adds a revive heart shown in the upper-left HUD, while
Double XP doubles XP gained for the run.

Zombies drop gems that are automatically collected within the pickup radius.
Each zombie has a 10% chance to drop an XP gem; gems grant XP and each level
pauses gameplay briefly for an ability choice. The ability pool includes
Sharpshooter (+1 damage and faster fire rate), Twin Shot, Thick Skin (+20 max
HP), Hedge of Protection, Fire from Heaven, Morning Star,
Storehouse of Hail, and Job's Orb. Hedge of Protection blocks one hit and
regenerates after 10 seconds. Fire from Heaven periodically strikes a random
zombie with lightning that chains through nearby zombies; each Fire from Heaven
upgrade adds another simultaneous strike. Morning Star circles the player with up to eight spikes
that become stronger with upgrades, and Storehouse of Hail periodically damages
nearby zombies with an upgradeable area attack. Job's Orb circles the
player and periodically fires a beam of light at the nearest visible zombie
after it is chosen. Each additional Job's Orb choice adds another orb, up to
five total. The beams aim horizontally, vertically, or diagonally based on the
target's position.
Rendering is procedural, and `render.assets.load_assets()` provides a sprite
registry ready for replacing placeholders with image assets.
