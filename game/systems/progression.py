import math
import random
from game.data import ABILITIES, SHOP_ITEMS
from game.config import (
    GEM_DROP_CHANCE,
    MAX_MORNING_STARS,
    PICKUP_CLOSE_MAGNET_RADIUS,
    PICKUP_CLOSE_MAGNET_SPEED,
    PICKUP_LIFETIME,
    PICKUP_MAGNET_SPEED,
    ZOMBIE_DEATH_DURATION,
)

def cleanup_dead(
    zombies,
    pools,
    progress,
    reward_multiplier=1,
    gem_drop_chance=GEM_DROP_CHANCE,
):
    """Grant rewards for zombies whose hp just dropped to 0 or below, and
    start their death animation -- it isn't released from the pool (and so
    keeps blocking/being drawn) until that animation finishes; see
    tick_zombie_hit_effects."""
    for z in list(zombies):
        if z.hp<=0 and not z.dying:
            z.dying=True; z.death_timer=ZOMBIE_DEATH_DURATION
            progress.score += 10
            # Every kill grants base XP; a gem is a separate 10% bonus drop.
            progress.xp += reward_multiplier * progress.xp_multiplier
            if random.random() < gem_drop_chance:
                xp=pools.pickups.acquire()
                if xp:
                    xp.pos.x,xp.pos.y,xp.amount,xp.kind=z.pos.x,z.pos.y,reward_multiplier,"xp"
                    xp.ttl=PICKUP_LIFETIME
            gold=pools.pickups.acquire()
            if gold:
                gold.pos.x,gold.pos.y,gold.amount,gold.kind=z.pos.x+3,z.pos.y+3,reward_multiplier,"gold"
                gold.ttl=PICKUP_LIFETIME

def tick_zombie_hit_effects(zombies, pool, dt):
    """Count down each zombie's "hurt" flash and "death" animation timers,
    releasing a zombie from the pool once its death animation finishes
    playing (see cleanup_dead, which starts it) rather than the instant it
    reaches 0 hp."""
    for z in zombies:
        if z.dying:
            z.death_timer -= dt
            if z.death_timer <= 0:
                pool.release(z)
        elif z.hurt_timer > 0:
            z.hurt_timer = max(0.0, z.hurt_timer - dt)

def collect_pickups(player, pickups, progress, dt=1/60):
    for item in list(pickups):
        item.ttl -= dt
        if item.ttl <= 0:
            item.active = False
            continue
        # Vector from the pickup to the player; moving along it pulls the
        # pickup inward instead of pushing it away.
        dx,dy=player.pos.x-item.pos.x,player.pos.y-item.pos.y
        distance=(dx*dx+dy*dy)**.5
        if distance <= player.magnet:
            if distance > 2:
                if distance <= PICKUP_CLOSE_MAGNET_RADIUS:
                    speed = min(PICKUP_CLOSE_MAGNET_SPEED, distance * 24)
                else:
                    speed = min(PICKUP_MAGNET_SPEED, distance * 12)
                step = min(speed * dt, distance - 2)
                item.pos.x += dx/distance*step
                item.pos.y += dy/distance*step
            else:
                if item.kind == "gold": progress.coins += item.amount
                else:
                    progress.gems += item.amount
                    progress.xp += item.amount * progress.xp_multiplier
                item.active=False
    if progress.xp >= progress.xp_to_next:
        progress.xp -= progress.xp_to_next
        progress.level += 1
        progress.xp_to_next = int(progress.xp_to_next * 1.35 + 4)
        progress.ability_choices = random.sample(ABILITIES, 3)
        return True
    return False

def buy(progress, name):
    name = {
        "heal": "Medkit",
        "damage": "Arsenal",
        "speed": "Boots",
    }.get(name, name)
    item = next((item for item in SHOP_ITEMS if item.name == name), None)
    if item is None or name not in progress.shop_inventory:
        return False
    if item.stock is not None and progress.shop_items.get(name, 0) <= 0:
        return False
    purchase_count = progress.shop_purchases.get(name, 0)
    cost = math.ceil(item.cost * (1.1 ** purchase_count))
    wallet = progress.gems if item.currency == "gems" else progress.coins
    if wallet < cost:
        return False
    if item.currency == "gems":
        progress.gems -= cost
    else:
        progress.coins -= cost
    progress.shop_purchases[name] = purchase_count + 1
    if item.stock is not None:
        progress.shop_items[name] -= 1
    if name == "Medkit":
        progress.health = min(progress.max_health, progress.health + 35)
    elif name == "Arsenal":
        progress.damage += 1
    elif name == "Boots":
        progress.move_multiplier *= 1.03
    elif name == "Extra Life":
        progress.extra_lives += 1
    elif name == "Double XP":
        progress.xp_multiplier *= 2
    return True

def apply_ability(progress, ability_name):
    effects={"Sharpshooter":lambda: (
                 setattr(progress, "damage", progress.damage + 1),
                 setattr(progress, "fire_rate", progress.fire_rate * .88),
             ),
             "Twin Shot":lambda: setattr(progress,"shots",progress.shots+1),
             "Thick Skin":lambda: (setattr(progress,"max_health",progress.max_health+20),
                                   setattr(progress,"health",progress.health+20)),
             "Hedge of Protection":lambda: (
                 setattr(progress, "shield_unlocked", True),
                 setattr(progress, "shield_max_hits", progress.shield_max_hits + 1),
                 setattr(progress, "shield_hits", progress.shield_hits + 1),
                 setattr(progress, "shield_ready", True),
                 setattr(progress, "shield_regen_timer", 0.0),
             ),
             "Fire from Heaven":lambda: (
                 setattr(progress, "fire_from_heaven_active", True),
                 setattr(progress, "fire_from_heaven_count", progress.fire_from_heaven_count + 1),
                 setattr(progress, "fire_from_heaven_timer", 0.0),
             ),
             "Morning Star":lambda: (
                 setattr(progress, "morning_star_active", True),
                 setattr(progress, "morning_star_count", min(MAX_MORNING_STARS, progress.morning_star_count + 1)),
                 setattr(progress, "morning_star_hit_timer", 0.0),
             ),
             "Storehouse of Hail":lambda: (
                 setattr(progress, "hail_active", True),
                 setattr(progress, "hail_level", progress.hail_level + 1),
                 setattr(progress, "hail_timer", 0.0),
             ),
             "Job's Orb":lambda: (
                 setattr(progress, "orb_count", min(5, progress.orb_count + 1)),
                 setattr(progress, "orb_active", True),
             )}
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
