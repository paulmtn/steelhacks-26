"""The shop van: drives to a random empty spot -- running over anything in
its path along the way -- parks there to do business for a while, then picks
a new spot and drives again. While parked it's a solid obstacle instead (see
shop_obstacle, used by game.systems.movement.move_player/move_zombies).

Movement reuses the same flow-field BFS zombies use (see
game.tilemap.compute_distance_field): one BFS from the destination tile,
cached until the destination changes, so a whole multi-second trip costs one
BFS, not one per frame. Steering itself (_steer_minimizing_turns) is its own
variant of game.systems.movement._steer_along_field's steepest-descent walk,
restricted to orthogonal (N/S/E/W) steps only -- the van drives strictly
horizontally or vertically, never diagonally -- and tie-breaking in favor of
the van's current heading so it drives in long straight lines, turning only
at intersections rather than zig-zagging between equally-short options.

When it does turn a corner, it sweeps smoothly through every sheet frame
between the old and new heading (see _shortest_frame_span) instead of
snapping straight from one cardinal frame to the other or freezing on a
single held pose -- a real, if brief, rotation rather than a jump-cut.
Movement itself is unaffected; this only changes which frame gets drawn.

The pathfinding above treats the van as a single point, so it can recommend
a route that's technically open but too narrow for the van's actual (up to
5-tile-wide) hitbox. If it makes zero progress for SHOP_STUCK_THRESHOLD
seconds, update_shop has it back up for SHOP_BACKUP_DURATION instead of
sitting jammed against the obstruction forever, giving pathing a different
spot to re-evaluate from. Backing up alone isn't a guarantee, though: the
field still has no idea the van is wide, so if the *shortest* route to a
destination is a too-narrow gap it'll keep recommending that same gap from
everywhere nearby, and the van would back up and re-approach it forever.
SHOP_GIVE_UP_THRESHOLD bounds that: once a trip has spent that much
cumulative time backing up, the van abandons its destination for a new one
rather than being stuck in that loop indefinitely.
"""
import math, random
from game.data import ENEMY_TYPES, Vec2
from game.config import (
    SHOP_PARK_DURATION, SHOP_HITBOX_LONG, SHOP_HITBOX_SHORT, SHOP_PIVOT_DURATION,
    SHOP_STUCK_THRESHOLD, SHOP_BACKUP_DURATION, SHOP_GIVE_UP_THRESHOLD,
)
from game.tilemap import get_world_map, rect_collides, is_solid_tile, compute_distance_field
from game.systems.movement import _ORTHOGONAL_STEPS

# "Twice the speed of the fast monsters" -- runner is the fast type (see game.data.ENEMY_TYPES).
SHOP_VAN_SPEED = ENEMY_TYPES["runner"].speed * 2

# White_MINIVAN_CLEAN_All_000-sheet.png is a 7x7 grid of 100x100 frames; the
# last cell is blank, leaving 48 frames that sweep a full rotation in clean
# 7.5-degree steps (verified against the sheet's own pixel bounding boxes --
# frame 0 is the widest/flattest silhouette, i.e. due east, and every 12th
# frame after it is the narrowest, i.e. a 90-degree turn).
SHOP_VAN_FRAME_COUNT = 48
SHOP_VAN_DEGREES_PER_FRAME = 360 / SHOP_VAN_FRAME_COUNT

_ARRIVE_DIST = 8.0  # close enough to the destination tile's center to call it "parked"

_flow_field_cache = {"tiled_map_id": None, "dest": None, "field": None}

def _flow_field_to(tiled_map, dest_col, dest_row):
    """The cached BFS distance field rooted at the van's current destination
    tile, recomputed only when that destination (or the map) changes."""
    cache = _flow_field_cache
    key = (dest_col, dest_row)
    if cache["tiled_map_id"] is not tiled_map or cache["dest"] != key:
        cache["field"] = compute_distance_field(tiled_map, dest_col, dest_row)
        cache["tiled_map_id"] = tiled_map
        cache["dest"] = key
    return cache["field"]

def _pick_destination(tiled_map, current):
    """A random walkable tile with some clearance to actually park in, at
    least ~10 tiles from where the van already is so every trip means
    something. Falls back to the first walkable tile found if 50 random
    tries can't find one (e.g. a very cramped or tiny map)."""
    width, height = tiled_map.width, tiled_map.height
    tw, th = tiled_map.tile_width, tiled_map.tile_height
    cur_col, cur_row = int(current.x // tw), int(current.y // th)
    for _ in range(50):
        col = random.randrange(3, max(4, width - 3))
        row = random.randrange(3, max(4, height - 3))
        if any(is_solid_tile(tiled_map, col + dc, row + dr) for dc in (-1, 0, 1) for dr in (-1, 0, 1)):
            continue
        if (col - cur_col) ** 2 + (row - cur_row) ** 2 < 100:
            continue
        return Vec2((col + .5) * tw, (row + .5) * th)
    for row in range(height):
        for col in range(width):
            if not is_solid_tile(tiled_map, col, row):
                return Vec2((col + .5) * tw, (row + .5) * th)
    return Vec2(current.x, current.y)

def _half_extents(shop):
    """The van's current collision half-width/half-height: 5x3 tiles while
    horizontal, 3x5 while vertical."""
    if shop.orientation == "horizontal":
        return SHOP_HITBOX_LONG / 2, SHOP_HITBOX_SHORT / 2
    return SHOP_HITBOX_SHORT / 2, SHOP_HITBOX_LONG / 2

def _overlaps(shop, x, y, radius):
    half_w, half_h = _half_extents(shop)
    return abs(x - shop.pos.x) <= half_w + radius and abs(y - shop.pos.y) <= half_h + radius

_TOUCH_MARGIN = 4.0  # covers the small residual gap collision can leave (up to ~1 frame's travel)

def shop_touching(shop, x, y, radius):
    """True if a circle (x, y, radius) is at or right up against the van's
    hitbox edge while it's parked. Used for the "E to shop" interaction check
    -- since the parked van now physically blocks the player (see
    shop_obstacle), they can never reach its center, only its edge, so
    "near the shop" has to mean "touching it" rather than "within some
    radius of its middle"."""
    if shop.state != "parked":
        return False
    return _overlaps(shop, x, y, radius + _TOUCH_MARGIN)

def shop_obstacle(shop):
    """The van's collision rectangle (x, y, half_width, half_height) while
    parked, for game.systems.movement.move_player/move_zombies' obstacle
    parameter -- a stationary van blocks the player and zombies like a wall.
    Returns None while driving: a moving van doesn't block, it deals damage
    instead (see update_shop below)."""
    if shop.state != "parked":
        return None
    half_w, half_h = _half_extents(shop)
    return (shop.pos.x, shop.pos.y, half_w, half_h)

def _axis_lock(dx, dy):
    """Zero out whichever axis needs less progress, so the result points
    purely horizontally or purely vertically -- never diagonally."""
    if abs(dx) >= abs(dy):
        return dx, 0.0
    return 0.0, dy

def _steer_minimizing_turns(tiled_map, field, zx, zy, px, py, heading):
    """Like a steepest-descent search on the BFS field (one tile-step toward
    whichever orthogonal neighbor has the lowest distance-to-target), but
    when several neighbors tie for best, keeps the van's current heading if
    it's among them instead of picking whichever direction happens to be
    checked first. This is what "prioritizes the minimum number of turns":
    it never takes a longer route to avoid a turn, but it never turns just
    because an equally-short alternative happened to be examined first,
    either.

    Only N/S/E/W neighbors are ever candidates -- the van only drives
    vertically or horizontally, never diagonally -- turning at intersections
    instead of cutting corners. Every return path also runs through
    _axis_lock as a final guarantee, since a tile-step target and the van's
    exact continuous position can differ slightly off-axis (e.g. mid-lane
    between two tile centers) even when the chosen step itself is orthogonal.

    Returns (dx, dy, new_heading).
    """
    tw, th = tiled_map.tile_width, tiled_map.tile_height
    width, height = tiled_map.width, tiled_map.height
    col, row = int(zx // tw), int(zy // th)
    own_dist = field[row * width + col] if 0 <= col < width and 0 <= row < height else -1
    if own_dist <= 0:
        return (*_axis_lock(px - zx, py - zy), heading)

    candidates = []  # (dcol, drow, dist)
    for dcol, drow in _ORTHOGONAL_STEPS:
        ncol, nrow = col + dcol, row + drow
        if 0 <= ncol < width and 0 <= nrow < height:
            nd = field[nrow * width + ncol]
            if 0 <= nd < own_dist:
                candidates.append((dcol, drow, nd))

    if not candidates:
        return (*_axis_lock(px - zx, py - zy), heading)

    best_dist = min(c[2] for c in candidates)
    best = [c for c in candidates if c[2] == best_dist]
    chosen = next((c for c in best if (c[0], c[1]) == heading), best[0])
    dcol, drow, _ = chosen
    target_x, target_y = (col + dcol + .5) * tw, (row + drow + .5) * th
    dx, dy = _axis_lock(target_x - zx, target_y - zy)
    return dx, dy, (dcol, drow)

def _frame_for_direction(dx, dy):
    """The sheet's rotation frame nearest this travel direction, or None for
    no movement (holds whatever frame it was already showing)."""
    if not dx and not dy:
        return None
    degrees = math.degrees(math.atan2(dy, dx)) % 360
    return round(degrees / SHOP_VAN_DEGREES_PER_FRAME) % SHOP_VAN_FRAME_COUNT

# Frames of sheet-rotation swept per second during a turn: a 90-degree turn
# (12 sheet-frames apart, e.g. east to south) takes SHOP_PIVOT_DURATION.
SHOP_TURN_FRAME_RATE = (SHOP_VAN_FRAME_COUNT / 4) / SHOP_PIVOT_DURATION

def _shortest_frame_span(from_frame, to_frame):
    """Signed frame delta from from_frame to to_frame the short way around
    the 48-frame wheel -- e.g. +12 for a 90-degree turn, +/-24 for a
    straight reversal (arbitrarily but consistently picks the positive
    direction when the two ways round are exactly tied)."""
    diff = (to_frame - from_frame) % SHOP_VAN_FRAME_COUNT
    if diff > SHOP_VAN_FRAME_COUNT / 2:
        diff -= SHOP_VAN_FRAME_COUNT
    return diff

def update_shop(shop, dt, zombies, player):
    """Advance the shop van by dt.

    While parked, just counts down to its next trip. While driving, steers
    toward its destination one axis at a time (never diagonally -- see
    _steer_minimizing_turns), backing up instead if it's made no progress
    for a while (see the module docstring), instantly kills any zombie its
    hitbox touches, and returns True if it just hit the player -- main.py
    applies the actual health change itself, the same way it already does
    for zombie contact damage, rather than this function reaching into
    progress state that isn't its concern.
    """
    tiled_map = get_world_map()
    if shop.state == "parked":
        shop.park_timer = max(0.0, shop.park_timer - dt)
        if shop.park_timer <= 0:
            shop.dest = _pick_destination(tiled_map, shop.pos)
            shop.state = "driving"
        return False

    if shop.backup_timer > 0:
        # Reversing away from whatever's blocking the way: the van keeps
        # facing the direction it was driving (real vehicles don't spin
        # around to back up), it just moves the opposite way for a bit.
        dx, dy = -shop.heading[0], -shop.heading[1]
    else:
        dest_col = int(shop.dest.x // tiled_map.tile_width)
        dest_row = int(shop.dest.y // tiled_map.tile_height)
        field = _flow_field_to(tiled_map, dest_col, dest_row)
        old_heading = shop.heading
        dx, dy, shop.heading = _steer_minimizing_turns(
            tiled_map, field, shop.pos.x, shop.pos.y, shop.dest.x, shop.dest.y, shop.heading,
        )
        length = (dx * dx + dy * dy) ** .5 or 1
        dx, dy = dx / length, dy / length

        shop.orientation = "horizontal" if abs(dx) >= abs(dy) else "vertical"
        if shop.heading != old_heading:
            target_frame = _frame_for_direction(dx, dy)
            if target_frame is not None:
                span = _shortest_frame_span(shop.frame, target_frame)
                if span:
                    # Restarting from shop.frame's current (possibly still
                    # mid-sweep) value means a second turn arriving before the
                    # first one finishes blends smoothly into the new sweep
                    # instead of jumping.
                    shop.pivot_from_frame = shop.frame
                    shop.pivot_span = span
                    shop.pivot_duration = abs(span) / SHOP_TURN_FRAME_RATE
                    shop.pivot_timer = shop.pivot_duration
        if shop.pivot_timer > 0:
            shop.pivot_timer = max(0.0, shop.pivot_timer - dt)
            progress = 1.0 if shop.pivot_duration <= 0 else min(1.0, 1 - shop.pivot_timer / shop.pivot_duration)
            shop.frame = (shop.pivot_from_frame + round(shop.pivot_span * progress)) % SHOP_VAN_FRAME_COUNT
        else:
            frame = _frame_for_direction(dx, dy)
            if frame is not None:
                shop.frame = frame

    half_w, half_h = _half_extents(shop)
    before_x, before_y = shop.pos.x, shop.pos.y
    new_x = shop.pos.x + dx * SHOP_VAN_SPEED * dt
    if not rect_collides(tiled_map, new_x, shop.pos.y, half_w, half_h):
        shop.pos.x = new_x
    new_y = shop.pos.y + dy * SHOP_VAN_SPEED * dt
    if not rect_collides(tiled_map, shop.pos.x, new_y, half_w, half_h):
        shop.pos.y = new_y

    # Its pathfinding treats the van as a single point, so a route it thinks
    # is clear can still be too narrow for its actual (up to 5-tile-wide)
    # hitbox -- rect_collides above then blocks every step it tries there,
    # forever. Zero progress for SHOP_STUCK_THRESHOLD is the signal: back
    # away from whatever's in the way and let pathing re-evaluate from a
    # different spot, rather than sitting jammed against it indefinitely.
    if shop.backup_timer > 0:
        shop.backup_timer = max(0.0, shop.backup_timer - dt)
        shop.trouble_time += dt
    if shop.pos.x != before_x or shop.pos.y != before_y:
        shop.stuck_timer = 0.0
    else:
        shop.stuck_timer += dt
        if shop.stuck_timer >= SHOP_STUCK_THRESHOLD and shop.backup_timer <= 0:
            shop.stuck_timer = 0.0
            if shop.trouble_time >= SHOP_GIVE_UP_THRESHOLD:
                # Backing up hasn't been escaping this in a reasonable
                # amount of cumulative time -- the shortest route here is
                # probably just too narrow for the van everywhere nearby.
                # Try somewhere else instead of repeating the same loop.
                shop.dest = _pick_destination(tiled_map, shop.pos)
                shop.trouble_time = 0.0
            else:
                shop.backup_timer = SHOP_BACKUP_DURATION

    for z in zombies:
        if z.active and _overlaps(shop, z.pos.x, z.pos.y, z.radius):
            z.hp = 0

    player_hit = player.invulnerable <= 0 and _overlaps(shop, player.pos.x, player.pos.y, player.radius)

    if (shop.pos.x - shop.dest.x) ** 2 + (shop.pos.y - shop.dest.y) ** 2 <= _ARRIVE_DIST ** 2:
        shop.state = "parked"
        shop.park_timer = SHOP_PARK_DURATION
        shop.trouble_time = 0.0

    return player_hit
