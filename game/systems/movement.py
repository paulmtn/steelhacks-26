from game.config import WORLD_WIDTH, WORLD_HEIGHT
from game.data import ENEMY_TYPES

def move_player(player, dx, dy, dt, speed, width=WORLD_WIDTH, height=WORLD_HEIGHT):
    length=(dx*dx+dy*dy)**.5
    if length: dx,dy=dx/length,dy/length
    player.pos.x=max(8,min(width-8,player.pos.x+dx*speed*dt)); player.pos.y=max(8,min(height-8,player.pos.y+dy*speed*dt))

def move_zombies(zombies, player, dt, speed):
    for z in zombies:
        dx,dy=player.pos.x-z.pos.x,player.pos.y-z.pos.y; d=(dx*dx+dy*dy)**.5 or 1
        actual=ENEMY_TYPES.get(z.enemy_type, ENEMY_TYPES["walker"]).speed + speed - 18
        z.pos.x+=dx/d*actual*dt; z.pos.y+=dy/d*actual*dt
