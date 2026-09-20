import math
from game.config import WORLD_WIDTH, WORLD_HEIGHT
from game.data import ENEMY_TYPES
from game.tilemap import get_world_map, rect_collides, compute_distance_field, is_solid_tile

# Sprite row for each 45-degree compass bucket, starting at East (0) and going
# clockwise in screen space: E, SE, S, SW, W, NW, N, NE. Matches the row order
# of render/graphics/Walk_while_Shooting.png (S, SW, NW, N, NE, SE, E, W).
_FACING_ROW_BY_BUCKET = (6, 5, 0, 1, 7, 2, 3, 4)

def _facing_row(dx, dy):
    """Map a direction vector to the closest of the 8 sprite-sheet rows."""
    degrees = math.degrees(math.atan2(dy, dx)) % 360
    bucket = int((degrees + 22.5) // 45) % 8
    return _FACING_ROW_BY_BUCKET[bucket]

def update_player_facing(player, move_dx, move_dy, aim_dx, aim_dy):
    """Point the player sprite at its current aim target so the gun tracks what
    it's auto-firing at, falling back to the movement direction when there is
    no target, and holding the last facing while standing still with no target.
    """
    if aim_dx or aim_dy: player.facing = _facing_row(aim_dx, aim_dy)
    elif move_dx or move_dy: player.facing = _facing_row(move_dx, move_dy)

def _blocked_by_obstacle(obstacle, x, y, half_w, half_h):
    """obstacle: an optional (x, y, half_width, half_height) solid rectangle
    besides tile walls -- e.g. the parked shop van (see
    game.systems.shop.shop_obstacle). A moving van doesn't use this; it deals
    damage instead (see game.systems.shop.update_shop)."""
    if obstacle is None:
        return False
    ox, oy, ohw, ohh = obstacle
    return abs(x - ox) <= half_w + ohw and abs(y - oy) <= half_h + ohh

def _obstacle_tiles(tiled_map, obstacle):
    """The tile coords an (x, y, half_width, half_height) obstacle rect (e.g.
    the parked shop van) currently covers, fed to compute_distance_field as
    extra blocked cells -- so the zombie flow field routes around it, rather
    than running the BFS as though it weren't there and then just bumping
    zombies into its edge one _blocked_by_obstacle step at a time."""
    if obstacle is None:
        return frozenset()
    ox, oy, ohw, ohh = obstacle
    tw, th = tiled_map.tile_width, tiled_map.tile_height
    col_start, col_end = int((ox - ohw) // tw), int((ox + ohw) // tw)
    row_start, row_end = int((oy - ohh) // th), int((oy + ohh) // th)
    return frozenset(
        (c, r) for r in range(row_start, row_end + 1) for c in range(col_start, col_end + 1)
    )

def move_player(player, dx, dy, dt, speed, width=WORLD_WIDTH, height=WORLD_HEIGHT, obstacle=None):
    length=(dx*dx+dy*dy)**.5
    if length: dx,dy=dx/length,dy/length
    tiled_map=get_world_map(); half=player.radius
    new_x=max(3*16,min(width-3*16,player.pos.x+dx*speed*dt))
    if not rect_collides(tiled_map,new_x,player.pos.y,half,half) and not _blocked_by_obstacle(obstacle,new_x,player.pos.y,half,half):
        player.pos.x=new_x
    new_y=max(3*16,min(height-3*16,player.pos.y+dy*speed*dt))
    if not rect_collides(tiled_map,player.pos.x,new_y,half,half) and not _blocked_by_obstacle(obstacle,player.pos.x,new_y,half,half):
        player.pos.y=new_y

# Pathing for zombies is a shared flow field, not per-zombie search: one BFS
# (game.tilemap.compute_distance_field) from the player's tile gives every
# tile's step-distance to the player, and each zombie just reads its own
# tile's value plus its 8 neighbors' -- O(1) per zombie per frame. This is
# what keeps "shortest path for every zombie" cheap regardless of zombie
# count, versus running A*/BFS separately per zombie.
_flow_field_cache = {"tiled_map_id": None, "target": None, "obstacle": None, "field": None}

def _flow_field_to(tiled_map, target_col, target_row, obstacle=None):
    """The cached BFS distance field rooted at (target_col, target_row),
    recomputed only when the player has moved into a different tile, the
    world map instance changed, or the van's blocked-tile footprint changed
    (it starts/stops parking, or parks somewhere new) since the last call."""
    cache = _flow_field_cache
    key = (target_col, target_row)
    if cache["tiled_map_id"] is not tiled_map or cache["target"] != key or cache["obstacle"] != obstacle:
        cache["field"] = compute_distance_field(
            tiled_map, target_col, target_row, _obstacle_tiles(tiled_map, obstacle),
        )
        cache["tiled_map_id"] = tiled_map
        cache["target"] = key
        cache["obstacle"] = obstacle
    return cache["field"]

_ORTHOGONAL_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL_STEPS = ((1, 1), (1, -1), (-1, 1), (-1, -1))

def _steer_along_field(tiled_map, field, zx, zy, px, py, blocked_tiles=frozenset()):
    """Direction (unnormalized) from (zx, zy) toward the player: one tile-step
    of steepest descent on the BFS field (checked across all 8 neighbors, with
    diagonals only taken when neither flanking wall corner -- or blocked_tiles
    cell, e.g. the parked shop van -- blocks them), or a direct line when the
    field can't help -- already in the player's tile, or cut off from it
    entirely by walls (an unreachable pocket)."""
    tw, th = tiled_map.tile_width, tiled_map.tile_height
    width, height = tiled_map.width, tiled_map.height
    col, row = int(zx // tw), int(zy // th)
    own_dist = field[row * width + col] if 0 <= col < width and 0 <= row < height else -1
    if own_dist <= 0:
        return px - zx, py - zy
    best_dist, best_dx, best_dy = own_dist, px - zx, py - zy
    for dcol, drow in _ORTHOGONAL_STEPS:
        ncol, nrow = col + dcol, row + drow
        if 0 <= ncol < width and 0 <= nrow < height:
            nd = field[nrow * width + ncol]
            if 0 <= nd < best_dist:
                best_dist = nd
                best_dx, best_dy = (ncol + .5) * tw - zx, (nrow + .5) * th - zy
    for dcol, drow in _DIAGONAL_STEPS:
        ncol, nrow = col + dcol, row + drow
        if 0 <= ncol < width and 0 <= nrow < height:
            nd = field[nrow * width + ncol]
            flank_a, flank_b = (col + dcol, row), (col, row + drow)
            if (0 <= nd < best_dist
                    and not is_solid_tile(tiled_map, *flank_a) and flank_a not in blocked_tiles
                    and not is_solid_tile(tiled_map, *flank_b) and flank_b not in blocked_tiles):
                best_dist = nd
                best_dx, best_dy = (ncol + .5) * tw - zx, (nrow + .5) * th - zy
    return best_dx, best_dy

def move_zombies(zombies, player, dt, speed, obstacle=None):
    tiled_map=get_world_map()
    tw,th=tiled_map.tile_width,tiled_map.tile_height
    target_col=max(0,min(tiled_map.width-1,int(player.pos.x//tw)))
    target_row=max(0,min(tiled_map.height-1,int(player.pos.y//th)))
    field=_flow_field_to(tiled_map,target_col,target_row,obstacle)
    blocked_tiles=_obstacle_tiles(tiled_map,obstacle)
    for z in zombies:
        dx,dy=_steer_along_field(tiled_map,field,z.pos.x,z.pos.y,player.pos.x,player.pos.y,blocked_tiles)
        d=(dx*dx+dy*dy)**.5 or 1
        actual=ENEMY_TYPES.get(z.enemy_type, ENEMY_TYPES["walker"]).speed + speed - 18
        half=z.radius
        new_x=z.pos.x+dx/d*actual*dt
        if not rect_collides(tiled_map,new_x,z.pos.y,half,half) and not _blocked_by_obstacle(obstacle,new_x,z.pos.y,half,half):
            z.pos.x=new_x
        new_y=z.pos.y+dy/d*actual*dt
        if not rect_collides(tiled_map,z.pos.x,new_y,half,half) and not _blocked_by_obstacle(obstacle,z.pos.x,new_y,half,half):
            z.pos.y=new_y
        if dx: z.facing_right=dx>0
        z.anim_time+=dt*actual/18  # walk-cycle plays faster/slower with the zombie's own speed