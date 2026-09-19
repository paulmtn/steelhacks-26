"""Tiled JSON map parsing and tile-grid collision, kept free of any pyxel/render dependency.

Rendering (render/assets.py, render/draw.py) imports the data model from here so both
gameplay and drawing share one parsed map instead of loading/parsing it twice.
"""
import json, os
from dataclasses import dataclass

# High bits Tiled sets on a gid to flag horizontal/vertical/diagonal flips.
# Masking them off recovers the plain tileset-local tile id.
GID_FLIP_MASK = 0x1FFFFFFF

COLLISION_LAYER = "Collisions"

@dataclass
class TiledMap:
    """A parsed Tiled JSON map: three tile layers plus the tileset(s) they draw from."""
    width: int
    height: int
    tile_width: int
    tile_height: int
    layers: dict          # layer name -> flat row-major list[int] of gids, len width*height
    tilesets: list         # dicts with firstgid/columns/image, sorted by firstgid descending

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
    # Always keep the Collisions layer available for gameplay, even when the
    # caller only asked render code for the first few drawable layers.
    all_by_name = {l["name"]: l for l in tile_layers}
    layers = {name: layer["data"] for name, layer in chosen}
    if COLLISION_LAYER in all_by_name and COLLISION_LAYER not in layers:
        layers[COLLISION_LAYER] = all_by_name[COLLISION_LAYER]["data"]
    return TiledMap(
        width=data["width"], height=data["height"],
        tile_width=data["tilewidth"], tile_height=data["tileheight"],
        layers=layers,
        tilesets=tilesets,
    )

WORLD_MAP = None

def get_world_map():
    """Load and cache the game's world map (render/untitled.json), parsing it only once."""
    global WORLD_MAP
    if WORLD_MAP is None:
        path = os.path.join(os.path.dirname(__file__), "..", "render", "untitled.json")
        WORLD_MAP = load_tiled_map(os.path.normpath(path))
    return WORLD_MAP

_solid_tiles_cache = {}

def _solid_tiles(tiled_map):
    """Set of (col, row) tile coordinates that are non-empty in the Collisions layer."""
    key = id(tiled_map)
    solid = _solid_tiles_cache.get(key)
    if solid is not None:
        return solid
    gids = tiled_map.layers.get(COLLISION_LAYER, ())
    solid = frozenset(
        (i % tiled_map.width, i // tiled_map.width)
        for i, gid in enumerate(gids) if gid & GID_FLIP_MASK
    )
    _solid_tiles_cache[key] = solid
    return solid

def is_solid_tile(tiled_map, col, row):
    """True if (col, row) is outside the map, or a non-empty Collisions tile."""
    if not (0 <= col < tiled_map.width and 0 <= row < tiled_map.height):
        return True
    return (col, row) in _solid_tiles(tiled_map)

def rect_collides(tiled_map, x, y, half_width, half_height):
    """True if the axis-aligned box centered at (x, y) overlaps any solid tile."""
    tw, th = tiled_map.tile_width, tiled_map.tile_height
    left, right = x - half_width, x + half_width
    top, bottom = y - half_height, y + half_height
    col_start, col_end = int(left // tw), int(right // tw)
    row_start, row_end = int(top // th), int(bottom // th)
    for row in range(row_start, row_end + 1):
        for col in range(col_start, col_end + 1):
            if is_solid_tile(tiled_map, col, row):
                return True
    return False
