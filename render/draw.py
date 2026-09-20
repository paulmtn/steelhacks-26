import math
from render.assets import *
from game.config import (
    WIDTH, HEIGHT, CELL_SIZE, WORLD_WIDTH, WORLD_HEIGHT,
    MORNING_STAR_DISTANCE, ORB_ORBIT_DISTANCE,
    ORB_BULLET_SPEED, PLAYER_ANIM_FPS, SHIELD_RADIUS,
    ZOMBIE_HURT_DURATION, ZOMBIE_DEATH_DURATION,
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
    """Draw the player's 48x64 sprite, lower-center pinned to its world position.

    Picks one of four sheets from two independent states -- moving vs
    standing still, firing (has a live auto-fire target) vs not -- see the
    table in render.assets above PLAYER_SHEET_PATH. The two not-firing
    sheets only have 6 rows (no dedicated E/W pose), so those go through
    PLAYER_6ROW_FACING_MAP; the firing sheets have the full 8 and use the
    facing index directly.
    """
    x,y=player.pos.x-ox,player.pos.y-oy
    if player.is_moving:
        sheet,colorkey=get_player_sheet() if player.is_firing else get_walk_gun_sheet()
    else:
        sheet,colorkey=get_shooting_sheet() if player.is_firing else get_idle_gun_sheet()
    row=player.facing if player.is_firing else PLAYER_6ROW_FACING_MAP[player.facing]
    if sheet is None:
        draw_sprite(p,"player",x,y); return
    frame=int(player.anim_time*PLAYER_ANIM_FPS)%PLAYER_FRAMES_PER_DIR
    u,v=frame*PLAYER_FRAME_WIDTH,row*PLAYER_FRAME_HEIGHT
    p.blt(x-PLAYER_FRAME_WIDTH//2,y-PLAYER_FRAME_HEIGHT+32,sheet,u,v,PLAYER_FRAME_WIDTH,PLAYER_FRAME_HEIGHT,colorkey)

def draw_zombie(p,zombie,ox,oy):
    """Draw a zombie's current-state sprite -- walking (looping), briefly
    flashing its "hurt" sheet after taking damage and surviving, or playing
    its "death" sheet once while it's dying -- centered on its world position
    and horizontally flipped to face its direction of travel, since the
    sheets only have right-facing frames. Falls back to a colored circle if
    a sheet ever fails to load."""
    x,y=zombie.pos.x-ox,zombie.pos.y-oy
    if zombie.dying:
        variant,elapsed=("death",ZOMBIE_DEATH_DURATION-zombie.death_timer)
    elif zombie.hurt_timer>0:
        variant,elapsed=("hurt",ZOMBIE_HURT_DURATION-zombie.hurt_timer)
    else:
        variant,elapsed=("walk",None)
    sheet_info=get_zombie_sheet(zombie.enemy_type,variant)
    if sheet_info is None:
        draw_sprite(p,zombie.enemy_type,x,y); return
    sheet,colorkey,meta=sheet_info
    fw,fh,frames=meta["frame_width"],meta["frame_height"],meta["frames"]
    if variant=="walk":
        frame=int(zombie.anim_time*meta["anim_fps"])%frames
    else:
        # Hurt/death play once and hold on the last frame, rather than
        # looping -- they end when their timer runs out (hurt, back to
        # walking) or the zombie is removed (death), not by wrapping around.
        frame=min(frames-1,int(max(0.0,elapsed)*meta["anim_fps"]))
    u=frame*fw
    w=fw if zombie.facing_right else -fw
    p.blt(x-fw//2,y-fh//2,sheet,u,0,w,fh,colorkey)

def draw_shop(p,shop,ox,oy):
    """Draw the shop van at its current rotation frame, centered on its world
    position. Falls back to a plain circle if the sheet ever fails to load."""
    x,y=shop.pos.x-ox,shop.pos.y-oy
    sheet,colorkey=get_shop_van_sheet()
    if sheet is None:
        p.circ(x,y,10,MERCHANT); return
    size=SHOP_VAN_FRAME_SIZE
    col,row=shop.frame%SHOP_VAN_COLUMNS,shop.frame//SHOP_VAN_COLUMNS
    p.blt(x-size//2,y-size//2,sheet,col*size,row*size,size,size,colorkey)

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

def draw_world(p,player,pools,progress,mode,camera,shop,dev=False,
               demo_mode=False):
    p.cls(BG); ox,oy=camera.x,camera.y
    draw_tilemap(p,get_world_map(),ox,oy)
    draw_shop(p,shop,ox,oy)
    if shop.state=="parked":
        label="SHOP: PRESS E."
        label_y=shop.pos.y-oy-58+(32 if shop.orientation=="horizontal" else 16)
        p.text(shop.pos.x-ox-len(label)*2,label_y,label,TEXT)
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
    for b in pools.bullets.active(): p.circ(b.pos.x-ox,b.pos.y-oy,round(b.radius),7)
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
    if progress.extra_lives > 0:
        p.circ(7,31,3,8)
        p.circ(12,31,3,8)
        p.tri(4,32,15,32,9,39,8)
        p.text(18,29,f"x{progress.extra_lives}",TEXT)
    p.rect(4,19,70,7,0)
    p.rect(4,19,int(70*max(0,progress.health/progress.max_health)),7,HEALTH)
    p.text(7,19,f"{int(max(0, progress.health))}/{int(progress.max_health)}",TEXT)
    if mode==GameMode.SHOP:
        shop_items = [
            item for item in SHOP_ITEMS
            if item.name in progress.shop_inventory
        ]
        cards_overlay(p, "MERCHANT", shop_items, show_cost=True, footer="E close", progress=progress)
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

def cards_overlay(p, title, items, show_cost=False, footer="", progress=None):
    """Draw bounded level-up cards or a four-item shop grid."""
    if show_cost:
        shop_grid(p, title, items, progress, footer)
        return

    p.rect(8,38,240,84,PANEL)
    p.rectb(8,38,240,84,TEXT)
    p.text(92,43,title,10)
    visible_items = items[:5] if show_cost else items[:3]
    card_width = 76
    card_height = 55
    for index, item in enumerate(visible_items):
        x = 10 + index * card_width
        y = 57
        p.rectb(x,y,card_width - 4,card_height,TEXT)
        heading = f"{index + 1} {item.name}"
        for line_index, line in enumerate(wrap_text(heading, 16)[:3]):
            p.text(x + 3, y + 3 + line_index * 6, line, TEXT)
        description_y = y + 22
        for line_index, line in enumerate(wrap_text(item.description, 16)[:3]):
            p.text(x + 3, description_y + line_index * 6, line, TEXT)
    p.text(72,116,footer,TEXT)

def shop_grid(p, title, items, progress, footer):
    """Draw the four selected shop items as a compact 2x2 grid."""
    p.rect(4,26,248,112,PANEL)
    p.rectb(4,26,248,112,TEXT)
    p.text(94,31,title,10)
    card_width, card_height = 120, 42
    for index, item in enumerate(items[:4], 1):
        row, column = divmod(index - 1, 2)
        x, y = 7 + column * card_width, 43 + row * card_height
        p.rectb(x, y, card_width - 6, card_height - 3, TEXT)
        purchases = progress.shop_purchases.get(item.name, 0)
        cost = math.ceil(item.cost * (1.1 ** purchases))
        currency = "gems" if item.currency == "gems" else "$"
        stock = (
            f"{progress.shop_items.get(item.name, 0)} left"
            if item.stock is not None else "unlimited"
        )
        heading = f"{index} {item.name} {cost}{currency}"
        for line_index, line in enumerate(wrap_text(heading, 21)[:2]):
            p.text(x + 4, y + 3 + line_index * 6, line, TEXT)
        for line_index, line in enumerate(wrap_text(item.description, 21)[:2]):
            p.text(x + 4, y + 16 + line_index * 6, line, TEXT)
        p.text(x + 4, y + 31, stock, TEXT)
    p.text(42,130,"1-4 buy item    E close",TEXT)

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
