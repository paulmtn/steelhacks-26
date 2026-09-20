from game.tilemap import get_world_map, has_line_of_sight
from game.data import MAX_ZOMBIE_RADIUS, ENEMY_TYPES, RANGED_ZOMBIE_TYPES, ZOMBIE_BASE_TYPE
from game.config import ZOMBIE_BULLET_SPEED, ZOMBIE_BULLET_RADIUS, ZOMBIE_FIRE_RATE, ZOMBIE_BULLET_RANGE
import math, random

def fire(pool, x,y, dx,dy, speed, damage, radius):
    b=pool.acquire()
    if not b:return None
    b.pos.x,b.pos.y,b.vx,b.vy,b.hp,b.damage,b.ttl,b.radius=x,y,dx*speed,dy*speed,1,damage,1.5,radius
    return b

def fire_beam(effect_pool, zombies, spatial_hash, x, y, dx, dy,
              max_range, damage, source=None, target=None):
    """Damage zombies intersecting an instant beam and pool its visual effect.

    source/target (e.g. the player and the zombie it's aimed at) let the
    drawn beam track both entities' *live* positions for its short life
    instead of freezing at the orb's world position when it fired -- see
    Particle.source/target. Purely cosmetic: hit detection above still uses
    the fixed x,y/dx,dy this call was given.
    """
    length = (dx * dx + dy * dy) ** 0.5 or 1
    dx, dy = dx / length, dy / length
    for zombie in spatial_hash.query(x, y, max_range):
        if not zombie.active:
            continue
        offset_x = zombie.pos.x - x
        offset_y = zombie.pos.y - y
        along = offset_x * dx + offset_y * dy
        across = abs(offset_x * dy - offset_y * dx)
        if 0 <= along <= max_range and across <= zombie.radius + 2:
            zombie.hp -= damage

    effect = effect_pool.acquire()
    if effect:
        effect.pos.x, effect.pos.y = x, y
        effect.vx, effect.vy = dx, dy
        effect.source, effect.target = source, target
        effect.ttl = 0.12
        effect.kind = "beam"

def strike_lightning_chain(
    effect_pool,
    zombies,
    damage,
    origin_x,
    origin_y,
    viewport=None,
    chain_range=64.0,
    chain_count=2,
    source=None,
):
    """source is the entity (e.g. the player) the first bolt visually strikes
    from -- see Particle.source/target. Later hops in the chain use the
    previously struck zombie itself as their live source, since that's what
    the bolt actually now runs from."""
    targets = [z for z in zombies if z.active]
    if viewport is not None:
        left, top, width, height = viewport
        right, bottom = left + width, top + height
        targets = [
            z for z in targets
            if left <= z.pos.x <= right and top <= z.pos.y <= bottom
        ]
    if not targets:
        return False
    target = random.choice(targets)
    previous_x, previous_y = origin_x, origin_y
    previous_entity = source
    struck = []
    for _ in range(chain_count + 1):
        target.hp -= damage
        effect = effect_pool.acquire()
        if effect:
            effect.pos.x, effect.pos.y = previous_x, previous_y
            effect.vx, effect.vy = target.pos.x - previous_x, target.pos.y - previous_y
            effect.source, effect.target = previous_entity, target
            effect.radius = 12
            effect.ttl, effect.kind = 0.45, "lightning"
        struck.append(target)
        candidates = [
            zombie for zombie in targets
            if zombie not in struck
            and (zombie.pos.x - target.pos.x) ** 2
            + (zombie.pos.y - target.pos.y) ** 2 <= chain_range ** 2
        ]
        if not candidates:
            break
        target = min(
            candidates,
            key=lambda zombie: (zombie.pos.x - target.pos.x) ** 2
            + (zombie.pos.y - target.pos.y) ** 2,
        )
        previous_x, previous_y = struck[-1].pos.x, struck[-1].pos.y
        previous_entity = struck[-1]
    return True

def strike_random_zombie(effect_pool, zombies, damage, viewport=None):
    """Compatibility wrapper for callers that need one on-screen strike."""
    return strike_lightning_chain(
        effect_pool, zombies, damage, 0, 0, viewport, chain_count=0
    )

def damage_at_point(zombies, spatial_hash, x, y, radius, damage):
    hit = False
    # +MAX_ZOMBIE_RADIUS: a zombie's own edge can reach into this blast from
    # outside the query's bounding box otherwise (see the precise per-zombie
    # check below, which is what actually decides the hit).
    for zombie in spatial_hash.query(x, y, radius + MAX_ZOMBIE_RADIUS):
        if not zombie.active:
            continue
        if (zombie.pos.x - x) ** 2 + (zombie.pos.y - y) ** 2 <= (radius + zombie.radius) ** 2:
            zombie.hp -= damage
            hit = True
    return hit

def hail_burst(effect_pool, zombies, spatial_hash, x, y, radius, damage, source=None):
    """x,y is the player's own position -- source (the player) lets the
    drawn cloud keep tracking them live for the effect's lifetime instead of
    freezing at the spawn-time position (see Particle.source)."""
    damage_at_point(zombies, spatial_hash, x, y, radius, damage)
    effect = effect_pool.acquire()
    if effect:
        effect.pos.x, effect.pos.y = x, y
        effect.source = source
        effect.radius, effect.ttl, effect.kind = radius, 0.35, "hail"

def nearest_target(player, zombies, spatial_hash=None, max_range=260,
                   viewport=None, obstacle=None):
    candidates = spatial_hash.query(player.pos.x, player.pos.y, max_range) if spatial_hash else zombies
    if viewport is not None:
        left, top, width, height = viewport
        right, bottom = left + width, top + height
        candidates = (
            z for z in candidates
            if left <= z.pos.x <= right and top <= z.pos.y <= bottom
        )
    tiled_map = get_world_map()
    candidates = (
        z for z in candidates
        if z.active and has_line_of_sight(tiled_map, player.pos.x, player.pos.y, z.pos.x, z.pos.y, obstacle)
    )
    return min(candidates,
               key=lambda z:(z.pos.x-player.pos.x)**2+(z.pos.y-player.pos.y)**2,
               default=None)

def update_bullets(pool, zombies, dt, width, height, spatial_hash=None, obstacle=None):
    """obstacle: an optional (x, y, half_width, half_height) solid rectangle
    besides the zombies bullets can hit -- e.g. the parked shop van (see
    game.systems.shop.shop_obstacle). A bullet that flies into it is
    destroyed there instead of passing through, same as it would a wall if
    walls stopped bullets."""
    hits=[]
    for b in pool.active():
        b.pos.x+=b.vx*dt; b.pos.y+=b.vy*dt; b.ttl-=dt
        if b.ttl<=0 or not(0<=b.pos.x<=width and 0<=b.pos.y<=height): pool.release(b); continue
        if obstacle is not None:
            ox, oy, ohw, ohh = obstacle
            if abs(b.pos.x-ox) <= b.radius+ohw and abs(b.pos.y-oy) <= b.radius+ohh:
                pool.release(b); continue
        # +MAX_ZOMBIE_RADIUS, not a flat margin: the query has to reach as
        # far as the biggest zombie's edge can be from its center, or a
        # bullet passing near a "_super" zombie's rim can skip right past it
        # -- the query never even returns it as a candidate, regardless of
        # how the precise per-zombie check below is written.
        candidates = spatial_hash.query(b.pos.x, b.pos.y, b.radius + MAX_ZOMBIE_RADIUS) if spatial_hash else zombies
        for z in candidates:
            if not z.active:
                continue
            if (b.pos.x-z.pos.x)**2+(b.pos.y-z.pos.y)**2 < (b.radius+z.radius)**2:
                z.hp-=b.damage; pool.release(b); hits.append(z); break
    return hits

def fire_zombie_bullets(pool, zombies, player, dt, obstacle=None):
    """Let "_super" zombies shoot at the player, by the same rules the
    player's own auto-fire (see nearest_target above) uses: a maximum range,
    a clear line of sight -- blocked by walls and the parked van, exactly
    like nearest_target's obstacle check -- and a cooldown between shots
    (each zombie's own fire_timer, mirroring the player's fire_clock). Base
    zombies never fire; only their fire_timer still ticks down, harmlessly,
    in case merging later turns one into a "_super" that does.

    Bullet damage is the shooter's *base* type's own contact_damage (see
    ZOMBIE_BASE_TYPE), not the super's own (2x) melee contact_damage -- the
    melee buff from merging doesn't carry over to their ranged attack.
    """
    tiled_map = get_world_map()
    for z in zombies:
        if not z.active or z.dying:
            continue
        if z.fire_timer > 0:
            z.fire_timer = max(0.0, z.fire_timer - dt)
        if z.enemy_type not in RANGED_ZOMBIE_TYPES or z.fire_timer > 0:
            continue
        dx, dy = player.pos.x - z.pos.x, player.pos.y - z.pos.y
        dist = math.hypot(dx, dy)
        if dist == 0 or dist > ZOMBIE_BULLET_RANGE:
            continue
        if not has_line_of_sight(tiled_map, z.pos.x, z.pos.y, player.pos.x, player.pos.y, obstacle):
            continue
        base_damage = ENEMY_TYPES[ZOMBIE_BASE_TYPE[z.enemy_type]].contact_damage
        bullet = fire(
            pool, z.pos.x, z.pos.y, dx / dist, dy / dist,
            ZOMBIE_BULLET_SPEED, base_damage, ZOMBIE_BULLET_RADIUS,
        )
        if bullet: bullet.enemy_type = z.enemy_type
        z.fire_timer = ZOMBIE_FIRE_RATE

def update_enemy_bullets(pool, player, dt, width, height, obstacle=None, on_hit=None):
    """Advance zombie-fired bullets (see fire_zombie_bullets) toward the
    player -- same movement/lifetime rules as update_bullets, and the same
    van-blocking rule (see its obstacle parameter), just aimed at the player
    instead of zombies. Returns the total damage dealt to the player this
    frame (0 if none); applying it -- shield absorption, the post-hit
    invulnerability window -- is left to the caller, same as update_shop's
    player_hit return already works.

    on_hit, if given, is called with each bullet that actually lands, before
    it's released -- lets a caller (see main.Game.update) note which
    zombie's gunfire (see Bullet.enemy_type) it was, for the end screen.
    """
    damage_dealt = 0
    for b in pool.active():
        b.pos.x+=b.vx*dt; b.pos.y+=b.vy*dt; b.ttl-=dt
        if b.ttl<=0 or not(0<=b.pos.x<=width and 0<=b.pos.y<=height): pool.release(b); continue
        if obstacle is not None:
            ox, oy, ohw, ohh = obstacle
            if abs(b.pos.x-ox) <= b.radius+ohw and abs(b.pos.y-oy) <= b.radius+ohh:
                pool.release(b); continue
        if player.invulnerable<=0 and (b.pos.x-player.pos.x)**2+(b.pos.y-player.pos.y)**2 < (b.radius+player.radius)**2:
            damage_dealt += b.damage
            if on_hit: on_hit(b)
            pool.release(b)
    return damage_dealt
