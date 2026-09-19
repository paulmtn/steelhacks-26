import math
from render.assets import *
from game.config import (
    WIDTH, HEIGHT, CELL_SIZE, WORLD_WIDTH, WORLD_HEIGHT,
    MORNING_STAR_DISTANCE, ORB_ORBIT_DISTANCE,
    ORB_BULLET_SPEED, PLAYER_ANIM_FPS, SHIELD_RADIUS,
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

def draw_player(p,player,ox,oy):
    """Draw the player's 48x64 walk-while-shooting sprite, lower-center pinned to its world position."""
    x,y=player.pos.x-ox,player.pos.y-oy
    sheet,colorkey=get_player_sheet()
    if sheet is None:
        draw_sprite(p,"player",x,y); return
    frame=int(player.anim_time*PLAYER_ANIM_FPS)%PLAYER_FRAMES_PER_DIR
    u,v=frame*PLAYER_FRAME_WIDTH,player.facing*PLAYER_FRAME_HEIGHT
    p.blt(x-PLAYER_FRAME_WIDTH//2,y-PLAYER_FRAME_HEIGHT+32,sheet,u,v,PLAYER_FRAME_WIDTH,PLAYER_FRAME_HEIGHT,colorkey)

def draw_zombie(p,zombie,ox,oy):
    """Draw a zombie's walk-cycle sprite (walker/runner), centered on its
    world position and horizontally flipped to face its direction of travel --
    the sheets only have right-facing frames. Falls back to a colored circle
    if the sheet ever fails to load."""
    x,y=zombie.pos.x-ox,zombie.pos.y-oy
    sheet_info=get_zombie_sheet(zombie.enemy_type)
    if sheet_info is None:
        draw_sprite(p,zombie.enemy_type,x,y); return
    sheet,colorkey,meta=sheet_info
    fw,fh,frames=meta["frame_width"],meta["frame_height"],meta["frames"]
    frame=int(zombie.anim_time*meta["anim_fps"])%frames
    u=frame*fw
    w=fw if zombie.facing_right else -fw
    p.blt(x-fw//2,y-fh//2,sheet,u,0,w,fh,colorkey)

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
                image,u,v,colorkey=source
                p.blt(col*tw-ox,row*th-oy,image,u,v,tw,th,colorkey)

def draw_world(p,player,pools,progress,mode,camera,merchant,dev=False,
               demo_mode=False):
    p.cls(BG); ox,oy=camera.x,camera.y
    draw_tilemap(p,get_world_map(),ox,oy)
    draw_sprite(p,"merchant",merchant.x-ox,merchant.y-oy)
    p.text(merchant.x-ox-14,merchant.y-oy-12,"SHOP",TEXT)
    draw_player(p,player,ox,oy)
    for orb_index in range(progress.orb_count):
        angle = player.orb_angle + (2 * math.pi * orb_index / progress.orb_count)
        orb_x = player.pos.x + math.cos(angle) * ORB_ORBIT_DISTANCE
        orb_y = player.pos.y + math.sin(angle) * ORB_ORBIT_DISTANCE
        p.circ(orb_x-ox, orb_y-oy, 3, 10)
    if progress.shield_hits > 0 or progress.shield_regen_timer > 0:
        p.circb(
            player.pos.x-ox,
            player.pos.y-oy,
            SHIELD_RADIUS,
            12 if progress.shield_hits > 0 else 5,
        )
    if progress.morning_star_active:
        for spike_index in range(progress.morning_star_count):
            angle = progress.morning_star_angle + (
                2 * math.pi * spike_index / progress.morning_star_count
            )
            star_x = player.pos.x + math.cos(angle) * MORNING_STAR_DISTANCE - ox
            star_y = player.pos.y + math.sin(angle) * MORNING_STAR_DISTANCE - oy
            p.circ(star_x, star_y, 4, 8)
            p.line(star_x-5, star_y, star_x+5, star_y, 10)
            p.line(star_x, star_y-5, star_x, star_y+5, 10)
    for z in pools.zombies.active(): draw_zombie(p,z,ox,oy)
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
        elif effect.kind == "lightning":
            start_x, start_y = effect.pos.x - ox, effect.pos.y - oy
            end_x, end_y = start_x + effect.vx, start_y + effect.vy
            mid_x, mid_y = (start_x + end_x) / 2, (start_y + end_y) / 2
            perp_x, perp_y = -effect.vy, effect.vx
            length = max(1.0, math.hypot(perp_x, perp_y))
            offset_x, offset_y = perp_x / length * 5, perp_y / length * 5
            p.line(start_x, start_y, mid_x + offset_x, mid_y + offset_y, 10)
            p.line(mid_x + offset_x, mid_y + offset_y, end_x - offset_x, end_y - offset_y, 10)
            p.line(end_x - offset_x, end_y - offset_y, end_x, end_y, 10)
            p.circ(end_x, end_y, effect.radius, 10)
        elif effect.kind == "hail":
            x, y = effect.pos.x - ox, effect.pos.y - oy
            cloud_y = y - effect.radius * 0.45
            p.circ(x - 16, cloud_y, 8, 7)
            p.circ(x - 5, cloud_y - 4, 10, 7)
            p.circ(x + 8, cloud_y - 3, 10, 7)
            p.circ(x + 18, cloud_y, 7, 7)
            p.rect(x - 20, cloud_y, 40, 7, 7)
            for hail_x, hail_length in ((-15, 10), (-7, 15), (2, 11), (11, 16), (18, 9)):
                start_y = cloud_y + 7
                p.line(x + hail_x, start_y, x + hail_x - 2, start_y + hail_length, 13)
            p.circb(x, y, effect.radius, 13)
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
    p.rect(12,38,232,78,PANEL)
    p.rectb(12,38,232,78,TEXT)
    p.text(92,44,title,10)
    for index, line in enumerate(wrap_text(hint, 38)[:4]):
        p.text(20,62 + index * 8,line,TEXT)

def cards_overlay(p, title, items, show_cost=False, footer=""):
    """Draw separated cards with word-aware text wrapping."""
    p.rect(8,30,240,90,PANEL)
    p.rectb(8,30,240,90,TEXT)
    p.text(92 if title != "MERCHANT" else 88,34,title,10)
    card_width = 76
    for index, item in enumerate(items[:3]):
        x = 12 + index * card_width
        p.rectb(x,47,72,57,TEXT)
        heading = f"{index + 1} {item.name}"
        if show_cost:
            heading += f" ${item.cost}"
        for line_index, line in enumerate(wrap_text(heading, 16)[:3]):
            p.text(x + 3, 50 + line_index * 7, line, TEXT)
        description_y = 72 if len(wrap_text(heading, 16)) < 3 else 79
        for line_index, line in enumerate(wrap_text(item.description, 16)[:3]):
            p.text(x + 3, description_y + line_index * 7, line, TEXT)
    p.text(76,108,footer,TEXT)

def wrap_text(text, max_chars):
    """Wrap at spaces, while safely splitting an unusually long word."""
    lines = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
            lines.extend(
                word[index:index + max_chars]
                for index in range(0, len(word), max_chars)
            )
        elif not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
