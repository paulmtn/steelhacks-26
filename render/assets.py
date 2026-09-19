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

SPRITES={"player":(0,0,0,8,8,0),"walker":(0,8,0,8,8,0),
         "runner":(0,16,0,8,8,0),"xp":(0,24,0,3,3,0),
         "gold":(0,29,0,3,3,0),"merchant":(0,34,0,8,8,0)}
# Pyxel palette: 10 is yellow and 13 is blue.
FALLBACK_COLORS={"player":11,"walker":3,"runner":9,"xp":13,"gold":10,"merchant":12}
ASSETS_LOADED=False
BG=1; TEXT=7; PLAYER=11; ZOMBIE=3; BULLET=10; COIN=9; HEALTH=11; PANEL=0; MERCHANT=12
def load_assets(pyxel, path=None):
    global ASSETS_LOADED
    if path:
        try:
            pyxel.load(path)
            ASSETS_LOADED=True
        except (OSError, ValueError):
            ASSETS_LOADED=False
    return SPRITES


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

# The player's 8-direction "walk while shooting" spritesheet: 8 columns of
# animation frames per row, one row per facing direction, in row order
# S, SW, NW, N, NE, SE, E, W (see game.systems.movement._FACING_ROW_BY_BUCKET,
# which maps aim/movement direction to the matching row index).
PLAYER_SHEET_PATH = os.path.join(os.path.dirname(__file__), "graphics", "Walk_while_Shooting.png")
PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT = 48, 64
PLAYER_FRAMES_PER_DIR = 8

def get_player_sheet():
    """Load and cache the player spritesheet, parsing it only once. Returns (image, colorkey)."""
    return _load_image(PLAYER_SHEET_PATH)