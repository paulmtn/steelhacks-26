"""Sprite registry and the asset-free fallback palette.

Replace the coordinates below when the team receives a .pyxres file.  Keeping
the names stable means gameplay and rendering code do not need to change.
"""
import os, tempfile
try:
    import pyxel
except ImportError:
    pyxel = None
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None
from game.tilemap import get_world_map, GID_FLIP_MASK
from game.config import (
    ZOMBIE_ANIM_FPS, WALKER_ANIM_FPS_BOOST, ZOMBIE_HURT_DURATION, ZOMBIE_DEATH_DURATION,
    PLAYER_DEATH_DURATION,
)
from game.data import ZOMBIE_BASE_TYPE

SPRITES={"player":(0,0,0,8,8,0),"walker":(0,8,0,8,8,0),
         "runner":(0,16,0,8,8,0),"xp":(0,24,0,3,3,0),
         "gold":(0,29,0,3,3,0),"merchant":(0,34,0,8,8,0)}
BG=1; TEXT=7; PLAYER=11; ZOMBIE=3; BULLET=10; COIN=9; HEALTH=11; PANEL=0; MERCHANT=12
# Fallback color if a zombie's sheet ever fails to load; matches its sprite's tint.
FALLBACK_COLORS={"player":11,"walker":14,"runner":8,"walker_super":14,"runner_super":8,"xp":HEALTH,"gold":10,"merchant":12}
ASSETS_LOADED=False
def load_assets(pyxel, path=None):
    global ASSETS_LOADED
    if path:
        try:
            pyxel.load(path)
            ASSETS_LOADED=True
        except (OSError, ValueError):
            ASSETS_LOADED=False
    return SPRITES

# One fixed pyxel.sounds[] slot and channel per sound effect. Only 4 mixer
# channels exist, and channel 3 is reserved entirely for the looping bgm (see
# MUSIC_CHANNEL below) -- playing an effect on the same channel as the bgm
# would cut the music off (silently, forever, since nothing re-triggers a
# loop after it's been interrupted), so every sound effect lives on channel
# 0-2 instead, grouped by what they mean rather than by literal sound:
# channel 1 is every player attack (gunshot plus the three ability impacts),
# channel 2 is enemy feedback and progression (hurt/dead naturally cut each
# other off -- a kill just replaces the hurt flash with the death sound, same
# as most games -- and a pickup/purchase chime is rare enough to tolerate
# occasionally losing to one of those). Channel 0 is hit_hurt shared with
# step and power_up -- footsteps retrigger every walking frame and will cut
# those off almost immediately, but that's a one-frame cosmetic loss against
# rare events.
_SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
SOUND_SLOTS = {
    "hit_hurt": (0, 0, "hitHurt.wav"),
    "mace": (1, 1, "mace.wav"),
    "orb": (1, 2, "orb.wav"),
    "thunder": (1, 3, "thunder.wav"),
    "shoot": (1, 6, "shoot.wav"),
    "enemy_hurt": (2, 7, "HurtEnemy.wav"),
    "enemy_dead": (2, 8, "enemyDead.wav"),
    "pickup_coin": (2, 4, "pickupCoin.wav"),
    "power_up": (0, 5, "power_up.wav"),
    "step": (0, 9, "step.wav"),
}
SOUNDS_LOADED=False

# The game's soundtrack: channel 3, kept free of every one-shot sound effect
# above (see the grouping comment) so nothing ever interrupts it, looping for
# as long as the game runs.
MUSIC_CHANNEL = 3
MUSIC_SLOT = 10
MUSIC_PATH = os.path.join(_SOUNDS_DIR, "Battle Encounter.ogg")
MUSIC_LOADED = False

def load_sounds(pyxel):
    """Load each sound effect's WAV, and the bgm's OGG, into their own
    pyxel.sounds[] slot in PCM mode, once, ready for play_sound/play_music to
    trigger by channel."""
    global SOUNDS_LOADED
    if SOUNDS_LOADED:
        return
    for _channel, slot, filename in SOUND_SLOTS.values():
        try:
            pyxel.sounds[slot].pcm(os.path.join(_SOUNDS_DIR, filename))
        except (OSError, ValueError):
            pass
    try:
        pyxel.sounds[MUSIC_SLOT].pcm(MUSIC_PATH)
    except (OSError, ValueError):
        pass
    SOUNDS_LOADED=True

def play_music(pyxel):
    """Start the soundtrack looping on its dedicated channel. Idempotent --
    safe to call once at startup; pyxel keeps replaying it on its own after
    that (loop=True), so nothing needs to poll or re-trigger it per frame."""
    global MUSIC_LOADED
    if MUSIC_LOADED:
        return
    pyxel.play(MUSIC_CHANNEL, MUSIC_SLOT, loop=True)
    MUSIC_LOADED = True

def play_sound(pyxel, name):
    """Play the named effect (a key of SOUND_SLOTS) on its assigned channel,
    cutting off whatever that channel was already playing -- fine for these
    short one-shot effects, which never share a channel with the looping bgm
    (see MUSIC_CHANNEL)."""
    channel, slot, _filename = SOUND_SLOTS[name]
    pyxel.play(channel, slot)


def slice_image(image, tile_width, tile_height, start_index, end_index):
    tiles = []
    tiles_across = image.width // tile_width

    for index in range(start_index, end_index + 1):
        x = (index % tiles_across) * tile_width
        y = (index // tiles_across) * tile_height

        tile = pyxel.Image(tile_width, tile_height)

        for tile_y in range(tile_height):
            for tile_x in range(tile_width):
                tile.pset(
                    tile_x,
                    tile_y,
                    image.pget(x + tile_x, y + tile_y)
                )

        tiles.append(tile)

    return tiles

TILE_SET=("graphics/All_Tileset.png",16,16,0,27347)

_loaded_images = {}  # path -> (pyxel.Image, colorkey)

# Pyxel images have no per-pixel alpha channel -- transparency only exists as
# a single "colorkey" palette index that blt() is told to skip. Naively
# dropping a PNG's alpha (Image.convert("RGB")) turns every transparent pixel
# into RGB (0, 0, 0), which is indistinguishable from real black artwork
# (hair, outlines, gun barrels, ...) once both get quantized into the same
# palette slot -- so keying transparency off color 0 (pyxel's default black)
# also hides every genuinely black pixel. To keep that black, transparent
# pixels are recolored to this reserved sentinel *before* the image is ever
# quantized or handed to pyxel, and the sentinel's resulting palette index --
# never assumed to be 0 -- is used as the colorkey instead.
TRANSPARENT_KEY_RGB = (255, 0, 255)
_ALPHA_OPAQUE_THRESHOLD = 128

def _flatten_transparency(path):
    """Return a same-size RGB copy of the PNG at path with transparent pixels
    recolored to TRANSPARENT_KEY_RGB and every opaque pixel's real color,
    including black, left untouched."""
    src = PILImage.open(path).convert("RGBA")
    opaque_mask = src.split()[-1].point(lambda a: 255 if a >= _ALPHA_OPAQUE_THRESHOLD else 0)
    flat = PILImage.new("RGB", src.size, TRANSPARENT_KEY_RGB)
    flat.paste(src.convert("RGB"), mask=opaque_mask)
    return flat

def _load_image(path):
    """Load a full-color PNG (tileset or spritesheet) as a pyxel.Image, growing
    pyxel's palette first. Returns (image, colorkey): colorkey is the palette
    index standing in for this image's real transparency, to pass to blt().
    """
    cached = _loaded_images.get(path)
    if cached is not None:
        return cached
    if PILImage is None:
        image = pyxel.Image.from_image(path)
        _loaded_images[path] = (image, 0)
        return _loaded_images[path]

    flat = _flatten_transparency(path)
    room = 256 - len(pyxel.colors)
    if room > 0:
        n = min(room, 240)
        palette = flat.quantize(colors=n).getpalette()
        # PIL returns a palette sized to the colors it actually used, which can be
        # fewer than requested for images with a small color count -- iterate its
        # real length, and skip colors this palette already has.
        for i in range(len(palette) // 3):
            r, g, b = palette[i*3:i*3+3]
            packed = (r << 16) | (g << 8) | b
            if packed not in pyxel.colors:
                pyxel.colors.append(packed)

    r, g, b = TRANSPARENT_KEY_RGB
    packed_key = (r << 16) | (g << 8) | b
    colorkey = next((i for i, c in enumerate(pyxel.colors) if c == packed_key), 0)

    fd, flat_path = tempfile.mkstemp(suffix=".png", prefix="pyxel_flat_")
    os.close(fd)
    try:
        flat.save(flat_path)
        image = pyxel.Image.from_image(flat_path)
    finally:
        os.remove(flat_path)
    _loaded_images[path] = (image, colorkey)
    return _loaded_images[path]

def tile_source(tiled_map, gid):
    """Resolve a tile gid to (image, u, v, colorkey) in its tileset image, loading that image on first use."""
    for ts in tiled_map.tilesets:
        if gid >= ts["firstgid"]:
            local_id = gid - ts["firstgid"]
            image, colorkey = _load_image(ts["image"])
            col, row = local_id % ts["columns"], local_id // ts["columns"]
            return image, col * tiled_map.tile_width, row * tiled_map.tile_height, colorkey
    return None

# The player's four 48x64-frame, 8-column spritesheets, picked in
# render.draw.draw_player by two independent states: moving vs standing
# still, and firing (has a live auto-fire target) vs not.
#
#           firing                    not firing
#   moving  Walk_while_Shooting (8 rows)  Walk_Gun (6 rows)
#   still   Shooting (8 rows)             Idle_Gun (6 rows)
#
# The 8-row sheets have one row per facing direction, in order
# S, SW, NW, N, NE, SE, E, W (see game.systems.movement._FACING_ROW_BY_BUCKET,
# which maps aim/movement direction to that same facing index). The two
# 6-row sheets only go S, SW, NW, N, NE, SE -- no dedicated east/west pose --
# so PLAYER_6ROW_FACING_MAP maps the facing index onto them, reusing the SE
# row for E and the SW row for W.
PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT = 48, 64
PLAYER_FRAMES_PER_DIR = 8
PLAYER_6ROW_FACING_MAP = (0, 1, 2, 3, 4, 5, 5, 1)

PLAYER_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "Walk_while_Shooting.png")
WALK_GUN_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "Walk_Gun.png")
SHOOTING_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "Shooting.png")
IDLE_GUN_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "Idle_Gun.png")
DEATH_GUN_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "death_Gun.png")

def get_player_sheet():
    """Load and cache the walking-while-firing spritesheet. Returns (image, colorkey)."""
    return _load_image(PLAYER_SHEET_PATH)

def get_walk_gun_sheet():
    """Load and cache the walking-not-firing spritesheet. Returns (image, colorkey)."""
    return _load_image(WALK_GUN_SHEET_PATH)

def get_shooting_sheet():
    """Load and cache the standing-still-and-firing spritesheet. Returns (image, colorkey)."""
    return _load_image(SHOOTING_SHEET_PATH)

def get_idle_gun_sheet():
    """Load and cache the standing-still-not-firing spritesheet. Returns (image, colorkey)."""
    return _load_image(IDLE_GUN_SHEET_PATH)

# Same 48x64 frame layout and 6-row (no dedicated E/W pose) facing scheme as
# Idle_Gun/Walk_Gun -- see PLAYER_6ROW_FACING_MAP -- but 8 columns: one play-
# once death animation per facing direction instead of a walk cycle.
PLAYER_DEATH_FRAMES = 8
PLAYER_DEATH_FPS = PLAYER_DEATH_FRAMES / PLAYER_DEATH_DURATION

def get_player_death_sheet():
    """Load and cache the player's death spritesheet. Returns (image, colorkey)."""
    return _load_image(DEATH_GUN_SHEET_PATH)

# The game's only two zombie classes, each with three single-row spritesheets
# -- walking (8 frames, looping), taking a hit and surviving (4 frames,
# played once), and dying (4 frames, played once) -- all right-facing, so
# movement left is done by horizontally flipping at draw time (see
# render.draw.draw_zombie) rather than by picking a different row. The hurt
# and death sheets play at the same rate for both types regardless of
# walker's walk-cycle speed boost, since they're not about walking pace.
_ZOMBIE_HURT_FRAMES = 4
_ZOMBIE_DEATH_FRAMES = 4
_ZOMBIE_HURT_FPS = _ZOMBIE_HURT_FRAMES / ZOMBIE_HURT_DURATION
_ZOMBIE_DEATH_FPS = _ZOMBIE_DEATH_FRAMES / ZOMBIE_DEATH_DURATION

def _zombie_graphics(name):
    return os.path.join(os.path.dirname(__file__), "graphics", name)

ZOMBIE_SHEETS = {
    "runner": {  # fast, fragile
        "walk": {
            "path": _zombie_graphics("Demon_A_Walk.png"),
            "frame_width": 100, "frame_height": 100, "frames": 8,
            "anim_fps": ZOMBIE_ANIM_FPS,
        },
        "hurt": {
            "path": _zombie_graphics("Demon_A_Hurt.png"),
            "frame_width": 100, "frame_height": 100, "frames": _ZOMBIE_HURT_FRAMES,
            "anim_fps": _ZOMBIE_HURT_FPS,
        },
        "death": {
            "path": _zombie_graphics("Demon_A_Death.png"),
            "frame_width": 100, "frame_height": 100, "frames": _ZOMBIE_DEATH_FRAMES,
            "anim_fps": _ZOMBIE_DEATH_FPS,
        },
    },
    "walker": {  # slow, tanky -- walk frame rate boosted 50% over the shared baseline
        "walk": {
            "path": _zombie_graphics("Blood Monster_A_Walk.png"),
            "frame_width": 100, "frame_height": 100, "frames": 8,
            "anim_fps": ZOMBIE_ANIM_FPS * WALKER_ANIM_FPS_BOOST,
        },
        "hurt": {
            "path": _zombie_graphics("Blood Monster_A_Hurt.png"),
            "frame_width": 100, "frame_height": 100, "frames": _ZOMBIE_HURT_FRAMES,
            "anim_fps": _ZOMBIE_HURT_FPS,
        },
        "death": {
            "path": _zombie_graphics("Blood Monster_A_Death.png"),
            "frame_width": 100, "frame_height": 100, "frames": _ZOMBIE_DEATH_FRAMES,
            "anim_fps": _ZOMBIE_DEATH_FPS,
        },
    },
}

# "_super" zombies (see game.data.ENEMY_TYPES/ZOMBIE_MERGE_TARGET) don't get
# their own art -- there isn't any -- they reuse their base type's sheets (see
# game.data.ZOMBIE_BASE_TYPE) at ZOMBIE_SUPER_SCALE, drawn bigger by
# render.draw.draw_zombie to match their doubled hitbox radius.
ZOMBIE_SUPER_SCALE = 2.0

def get_zombie_sheet(enemy_type, variant="walk"):
    """Load and cache enemy_type's spritesheet for variant ("walk", "hurt",
    or "death"), parsing it only once. Returns (image, colorkey, meta) or
    None if enemy_type/variant has no sheet. A "_super" enemy_type resolves
    to its base type's sheet (see ZOMBIE_BASE_TYPE) -- there's no separate
    art for it, just a bigger draw scale."""
    type_sheets = ZOMBIE_SHEETS.get(ZOMBIE_BASE_TYPE.get(enemy_type, enemy_type))
    if type_sheets is None:
        return None
    meta = type_sheets.get(variant)
    if meta is None:
        return None
    image, colorkey = _load_image(meta["path"])
    return image, colorkey, meta

# The shop van: a 7x7 grid of 100x100 frames, 48 of them used (the last cell
# is blank) sweeping one full rotation. See game.systems.shop for how the
# frame index is picked from the van's travel direction.
SHOP_VAN_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "White_MINIVAN_CLEAN_All_000-sheet.png")
SHOP_VAN_FRAME_SIZE = 100
SHOP_VAN_COLUMNS = 7

def get_shop_van_sheet():
    """Load and cache the shop van spritesheet, parsing it only once. Returns (image, colorkey)."""
    return _load_image(SHOP_VAN_SHEET_PATH)