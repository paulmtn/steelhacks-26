import math
from render.assets import *
from game.config import (
    WIDTH, HEIGHT, CELL_SIZE, WORLD_WIDTH, WORLD_HEIGHT,
    ORB_ORBIT_DISTANCE, ORB_BULLET_SPEED,
)
from game.data import SHOP_ITEMS
from game.state import GameMode

def draw_sprite(p,name,x,y):
    sprite=SPRITES.get(name)
    if sprite and ASSETS_LOADED:
        p.blt(x-sprite[3]//2,y-sprite[4]//2,sprite[0],sprite[1],sprite[2],sprite[3],sprite[4],sprite[5])
    else:
        color=FALLBACK_COLORS.get(name,TEXT)
        radius=max(1,(sprite[3] if sprite else 6)//2)
        p.circ(x,y,radius,color)

def draw_tilemap(p,tiled_map,ox,oy):
    """Blit every tile of the world map visible at camera offset (ox,oy)."""
    tw,th=tiled_map.tile_width,tiled_map.tile_height
    col_start=max(0,int(ox//tw)); col_end=min(tiled_map.width,int((ox+WIDTH)//tw)+2)
    row_start=max(0,int(oy//th)); row_end=min(tiled_map.height,int((oy+HEIGHT)//th)+2)
    for gids in tiled_map.layers.values():
        for row in range(row_start,row_end):

            base=row*tiled_map.width
            for col in range(col_start,col_end):

                gid=gids[base+col]&GID_FLIP_MASK
                if not gid: continue
                source=tile_source(tiled_map,gid)
                if source is None: continue
                image,u,v=source
                p.blt(col*tw-ox,row*th-oy,image,u,v,tw,th,0)

def draw_world(p,player,pools,progress,mode,camera,merchant,dev=False,
               demo_mode=False):
    p.cls(BG); ox,oy=camera.x,camera.y
    draw_tilemap(p,get_world_map(),ox,oy)
    draw_sprite(p,"merchant",merchant.x-ox,merchant.y-oy)
    p.text(merchant.x-ox-14,merchant.y-oy-12,"SHOP",TEXT)
    draw_sprite(p,"player",player.pos.x-ox,player.pos.y-oy)
    for orb_index in range(progress.orb_count):
        angle = player.orb_angle + (2 * math.pi * orb_index / progress.orb_count)
        orb_x = player.pos.x + math.cos(angle) * ORB_ORBIT_DISTANCE
        orb_y = player.pos.y + math.sin(angle) * ORB_ORBIT_DISTANCE
        p.circ(orb_x-ox, orb_y-oy, 3, 10)
    for z in pools.zombies.active(): draw_sprite(p,z.enemy_type,z.pos.x-ox,z.pos.y-oy)
    for b in pools.bullets.active(): draw_sprite(p,"bullet",b.pos.x-ox,b.pos.y-oy)
    for effect in pools.particles.active():
        if effect.kind == "beam":
            p.line(
                effect.pos.x-ox,
                effect.pos.y-oy,
                effect.pos.x-ox + effect.vx * ORB_BULLET_SPEED,
                effect.pos.y-oy + effect.vy * ORB_BULLET_SPEED,
                10,
            )
    for item in pools.pickups.active(): draw_sprite(p,item.kind,item.pos.x-ox,item.pos.y-oy)
    mins=int(progress.survival_time)//60; secs=int(progress.survival_time)%60
    p.text(4,3,f"{mins:02d}:{secs:02d} LV{progress.level} XP {int(progress.xp)}/{progress.xp_to_next}",TEXT)
    p.text(4,11,f"GEMS {progress.gems} GOLD {progress.coins} SCORE {progress.score}",TEXT)
    p.rect(4,19,70,7,0)
    p.rect(4,19,int(70*max(0,progress.health/progress.max_health)),7,HEALTH)
    p.text(7,19,f"{int(max(0, progress.health))}/{int(progress.max_health)}",TEXT)
    if mode==GameMode.SHOP:
        cards_overlay(p, "MERCHANT", SHOP_ITEMS, show_cost=True, footer="E close")
    elif mode==GameMode.UPGRADES: overlay(p,"UPGRADES","1 Damage  2 Vitality  3 Magnet  U close")
    elif mode==GameMode.LEVEL_UP:
        cards_overlay(p, "LEVEL UP", progress.ability_choices, footer="Choose 1, 2, or 3")
    elif mode==GameMode.GAME_OVER: overlay(p,"YOU DIED","R restart")
    if dev:
        status = "DEMO 3X" if demo_mode else "NORMAL"
        p.text(4,HEIGHT-8,f"F2 demo: {status} | z:{len(list(pools.zombies.active()))}",13)
def overlay(p,title,hint):
    p.rect(18,52,220,42,PANEL); p.rectb(18,52,220,42,TEXT); p.text(70,60,title,10); p.text(25,78,hint,TEXT)

def cards_overlay(p, title, items, show_cost=False, footer=""):
    """Draw three compact item/ability cards with descriptions underneath."""
    p.rect(12,40,232,78,PANEL); p.rectb(12,40,232,78,TEXT)
    p.text(100,45,title,10)
    card_width = 74
    for index, item in enumerate(items[:3]):
        x = 16 + index * card_width
        heading = f"{index + 1} {item.name}"
        if show_cost:
            heading += f" ${item.cost}"
        p.text(x, 59, heading[:18], TEXT)
        lines = [item.description[i:i + 17] for i in range(0, len(item.description), 17)]
        for line_index, line in enumerate(lines[:2]):
            p.text(x, 68 + line_index * 7, line, TEXT)
    p.text(78, 108, footer, TEXT)
