"""Sprite registry and the asset-free fallback palette.

Replace the coordinates below when the team receives a .pyxres file.  Keeping
the names stable means gameplay and rendering code do not need to change.
"""
import json, os
from dataclasses import dataclass, field
try:
    import pyxel
except ImportError:
    pyxel = None
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

SPRITES={"player":(0,0,0,8,8,0),"walker":(0,8,0,8,8,0),
         "runner":(0,16,0,8,8,0),"xp":(0,24,0,5,5,0),
         "gold":(0,29,0,5,5,0),"merchant":(0,34,0,8,8,0)}
FALLBACK_COLORS={"player":11,"walker":3,"runner":9,"xp":10,"gold":4,"merchant":12}
ASSETS_LOADED=False
BG=1; TEXT=7; PLAYER=11; ZOMBIE=3; BULLET=10; COIN=9; HEALTH=8; PANEL=0; MERCHANT=12
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

# High bits Tiled sets on a gid to flag horizontal/vertical/diagonal flips.
# Masking them off recovers the plain tileset-local tile id.
GID_FLIP_MASK=0x1FFFFFFF

@dataclass
class TiledMap:
    """A parsed Tiled JSON map: three tile layers plus the tileset(s) they draw from."""
    width: int
    height: int
    tile_width: int
    tile_height: int
    layers: dict          # layer name -> flat row-major list[int] of gids, len width*height
    tilesets: list         # dicts with firstgid/columns/image, sorted by firstgid descending
    images: dict = field(default_factory=dict)  # image path -> loaded pyxel.Image, filled lazily

def load_tiled_map(path, layer_names=None):
    """Parse a Tiled JSON export and return up to three of its tile layers.

    By default the first three "tilelayer" entries (in file order, which is
    also Tiled's bottom-to-top draw order) are used. Pass layer_names as a
    list of layer names to pick specific layers instead.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tile_layers = [l for l in data["layers"] if l.get("type") == "tilelayer"]
    if layer_names is not None:
        by_name = {l["name"]: l for l in tile_layers}
        chosen = [(name, by_name[name]) for name in layer_names]
    else:
        chosen = [(l["name"], l) for l in tile_layers[:3]]
    if not chosen:
        raise ValueError(f"Tiled map {path!r} has no tile layers")
    base_dir = os.path.dirname(path)
    tilesets = sorted(
        ({"firstgid": ts["firstgid"], "columns": ts["columns"],
          "image": os.path.normpath(os.path.join(base_dir, ts["image"]))}
         for ts in data["tilesets"]),
        key=lambda ts: ts["firstgid"], reverse=True,
    )
    return TiledMap(
        width=data["width"], height=data["height"],
        tile_width=data["tilewidth"], tile_height=data["tileheight"],
        layers={name: layer["data"] for name, layer in chosen},
        tilesets=tilesets,
    )


_palette_extended_for = set()

def _load_tileset_image(path):
    """Load a tileset PNG as a pyxel.Image, growing pyxel's palette first.

    Pyxel quantizes any loaded image down to its current (16-color by
    default) palette. A full-color tileset PNG mostly collapsed onto a
    couple of those indices this way -- including the one used as the
    world's background color, which is why tiles were rendering invisible
    against it. Feeding pyxel a few hundred more colors, sampled from the
    tileset itself via Pillow, gives quantization enough room to keep
    different tiles visually distinct.
    """
    if PILImage is not None and path not in _palette_extended_for:
        _palette_extended_for.add(path)
        room = 256 - len(pyxel.colors)
        if room > 0:
            n = min(room, 240)
            palette = PILImage.open(path).convert("RGB").quantize(colors=n).getpalette()
            for i in range(n):
                r, g, b = palette[i*3:i*3+3]
                pyxel.colors.append((r << 16) | (g << 8) | b)
    return pyxel.Image.from_image(path)

def tile_source(tiled_map, gid):
    """Resolve a tile gid to (image, u, v) in its tileset image, loading that image on first use."""
    for ts in tiled_map.tilesets:
        if gid >= ts["firstgid"]:
            local_id = gid - ts["firstgid"]
            image = tiled_map.images.get(ts["image"])
            if image is None:
                image = _load_tileset_image(ts["image"])
                tiled_map.images[ts["image"]] = image
            col, row = local_id % ts["columns"], local_id // ts["columns"]
            return image, col * tiled_map.tile_width, row * tiled_map.tile_height
    return None

WORLD_MAP=None

def get_world_map():
    """Load and cache the game's world map (render/untitled.json), parsing it only once."""
    global WORLD_MAP
    if WORLD_MAP is None:
        WORLD_MAP=load_tiled_map(os.path.join(os.path.dirname(__file__),"untitled.json"))
    return WORLD_MAP