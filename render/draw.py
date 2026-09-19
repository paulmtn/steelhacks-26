from render.assets import *
from game.config import WIDTH,HEIGHT,CELL_SIZE,WORLD_WIDTH,WORLD_HEIGHT
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

def draw_world(p,player,pools,progress,mode,camera,merchant,dev=False):
    p.cls(BG); ox,oy=camera.x,camera.y
    # Cull a grid of city blocks; roads remain visible between buildings.
    for cy in range(int(oy//CELL_SIZE)-1,int((oy+HEIGHT)//CELL_SIZE)+2):
        for cx in range(int(ox//CELL_SIZE)-1,int((ox+WIDTH)//CELL_SIZE)+2):
            x,y=cx*CELL_SIZE-ox,cy*CELL_SIZE-oy
            if (cx+cy)%3==0: p.rect(x+3,y+3,CELL_SIZE-6,CELL_SIZE-6,5)
            else: p.rect(x,y,CELL_SIZE,CELL_SIZE,2); p.line(x,y,x+CELL_SIZE,y,4)
    draw_sprite(p,"merchant",merchant.x-ox,merchant.y-oy)
    p.text(merchant.x-ox-14,merchant.y-oy-12,"SHOP",TEXT)
    draw_sprite(p,"player",player.pos.x-ox,player.pos.y-oy)
    for z in pools.zombies.active(): draw_sprite(p,z.enemy_type,z.pos.x-ox,z.pos.y-oy)
    for b in pools.bullets.active(): draw_sprite(p,"bullet",b.pos.x-ox,b.pos.y-oy)
    for item in pools.pickups.active(): draw_sprite(p,item.kind,item.pos.x-ox,item.pos.y-oy)
    mins=int(progress.survival_time)//60; secs=int(progress.survival_time)%60
    p.text(4,3,f"{mins:02d}:{secs:02d} LV{progress.level} XP {int(progress.xp)}/{progress.xp_to_next}",TEXT)
    p.text(4,11,f"GEMS {progress.gems} GOLD {progress.coins} SCORE {progress.score}",TEXT)
    p.rect(4,19,70,5,0); p.rect(4,19,int(70*max(0,progress.health/progress.max_health)),5,HEALTH)
    if mode==GameMode.SHOP:
        cards_overlay(p, "MERCHANT", SHOP_ITEMS, show_cost=True, footer="E close")
    elif mode==GameMode.UPGRADES: overlay(p,"UPGRADES","1 Damage  2 Vitality  3 Magnet  U close")
    elif mode==GameMode.LEVEL_UP:
        cards_overlay(p, "LEVEL UP", progress.ability_choices, footer="Choose 1, 2, or 3")
    elif mode==GameMode.GAME_OVER: overlay(p,"YOU DIED","R restart")
    if dev: p.text(4,HEIGHT-8,f"F4 +50 XP/+100 GOLD | z:{len(list(pools.zombies.active()))}",13)
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
