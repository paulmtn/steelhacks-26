import math
from game.config import WORLD_WIDTH, WORLD_HEIGHT
from game.data import ENEMY_TYPES
from game.tilemap import get_world_map, rect_collides

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

def move_player(player, dx, dy, dt, speed, width=WORLD_WIDTH, height=WORLD_HEIGHT):
    length=(dx*dx+dy*dy)**.5
    if length: dx,dy=dx/length,dy/length
    tiled_map=get_world_map(); half=player.radius
    new_x=max(3*16,min(width-3*16,player.pos.x+dx*speed*dt))
    if not rect_collides(tiled_map,new_x,player.pos.y,half,half): player.pos.x=new_x
    new_y=max(3*16,min(height-3*16,player.pos.y+dy*speed*dt))
    if not rect_collides(tiled_map,player.pos.x,new_y,half,half): player.pos.y=new_y

def move_zombies(zombies, player, dt, speed):
    tiled_map=get_world_map()
    for z in zombies:
        dx,dy=player.pos.x-z.pos.x,player.pos.y-z.pos.y; d=(dx*dx+dy*dy)**.5 or 1
        actual=ENEMY_TYPES.get(z.enemy_type, ENEMY_TYPES["walker"]).speed + speed - 18
        half=z.radius
        new_x=z.pos.x+dx/d*actual*dt
        if not rect_collides(tiled_map,new_x,z.pos.y,half,half): z.pos.x=new_x
        new_y=z.pos.y+dy/d*actual*dt
        if not rect_collides(tiled_map,z.pos.x,new_y,half,half): z.pos.y=new_y
