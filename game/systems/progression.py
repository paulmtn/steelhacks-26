import random
from game.data import ABILITIES, SHOP_ITEMS
from game.config import PICKUP_MAGNET_SPEED

def cleanup_dead(zombies, pools, progress):
    for z in list(zombies):
        if z.hp<=0:
            pools.zombies.release(z); progress.score += 10
            xp=pools.pickups.acquire()
            if xp: xp.pos.x,xp.pos.y,xp.amount,xp.kind=z.pos.x,z.pos.y,1,"xp"
            gold=pools.pickups.acquire()
            if gold: gold.pos.x,gold.pos.y,gold.amount,gold.kind=z.pos.x+3,z.pos.y+3,2,"gold"

def collect_pickups(player, pickups, progress, dt=1/60):
    for item in list(pickups):
        # Vector from the pickup to the player; moving along it pulls the
        # pickup inward instead of pushing it away.
        dx,dy=player.pos.x-item.pos.x,player.pos.y-item.pos.y
        distance=(dx*dx+dy*dy)**.5
        if distance <= player.magnet:
            if distance > 2:
                speed = min(PICKUP_MAGNET_SPEED, distance * 12)
                step = min(speed * dt, distance - 2)
                item.pos.x += dx/distance*step
                item.pos.y += dy/distance*step
            else:
                if item.kind == "gold": progress.coins += item.amount
                else: progress.gems += item.amount; progress.xp += item.amount
                item.active=False
    if progress.xp >= progress.xp_to_next:
        progress.xp -= progress.xp_to_next
        progress.level += 1
        progress.xp_to_next = int(progress.xp_to_next * 1.35 + 4)
        progress.ability_choices = random.sample(ABILITIES, 3)
        return True
    return False

def buy(progress, name):
    costs={'heal':SHOP_ITEMS[0].cost,'damage':SHOP_ITEMS[1].cost,'speed':SHOP_ITEMS[2].cost}
    cost=costs.get(name,999)
    if progress.coins<cost:return False
    progress.coins-=cost
    if name=='heal': progress.health=min(progress.max_health,progress.health+30)
    elif name=='damage': progress.damage+=1
    elif name=='speed': progress.speed_bonus+=8
    elif name=='magnet': progress.magnet+=20
    else: progress.shots+=1
    return True

def apply_ability(progress, ability_name):
    effects={"Sharpshooter":lambda: setattr(progress,"damage",progress.damage+1),
             "Haste":lambda: setattr(progress,"fire_rate",progress.fire_rate*.88),
             "Fleet Feet":lambda: setattr(progress,"speed_bonus",progress.speed_bonus+12),
             "Magnetism":lambda: setattr(progress,"magnet",progress.magnet+32),
             "Twin Shot":lambda: setattr(progress,"shots",progress.shots+1)}
    effect=effects.get(ability_name)
    if effect: effect(); return True
    return False

def buy_permanent(progress, name):
    count=progress.upgrades.get(name, 0)
    cost=(count+1)*20
    if progress.coins < cost: return False
    progress.coins -= cost; progress.upgrades[name]=count+1
    if name=="Damage": progress.damage += 1
    elif name=="Vitality": progress.max_health += 15; progress.health += 15
    else: progress.magnet += 12
    return True
