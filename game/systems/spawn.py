import random
from game.config import WORLD_WIDTH, WORLD_HEIGHT
from game.data import ENEMY_TYPES, ZOMBIE_MERGE_TARGET, MAX_ZOMBIE_RADIUS
from game.tilemap import get_world_map, rect_collides

# Spots to retry a spawn point that landed inside a solid (Collisions-layer)
# tile before giving up on this spawn -- edge tiles can themselves be part of
# a building, so a single random sample sometimes lands inside one.
_SPAWN_ATTEMPTS = 20

def spawn_zombie(pool, wave):
    # Only two classes now: walker (slow/tanky) is the common case, runner
    # (fast/fragile) the rarer threat. Available from wave 1 so they're not
    # gated behind minutes of score-grinding to ever be seen. Neither "_super"
    # variant is ever spawned directly -- they only come from merging (see
    # merge_touching_zombies below).
    enemy_type="runner" if random.random()<.25 else "walker"
    profile=ENEMY_TYPES[enemy_type]
    tiled_map=get_world_map()
    for _ in range(_SPAWN_ATTEMPTS):
        edge=random.randrange(4)
        x=random.uniform(5*16,WORLD_WIDTH-5*16) if edge<2 else (5*16 if edge==2 else WORLD_WIDTH-5*16)
        y=(5*16 if edge==0 else WORLD_HEIGHT-5*16) if edge<2 else random.uniform(5*16,WORLD_HEIGHT-5*16)
        if not rect_collides(tiled_map, x, y, profile.radius, profile.radius):
            break
    else:
        return None
    z=pool.acquire()
    if not z:
        return None
    z.pos.x,z.pos.y=x,y
    z.enemy_type=enemy_type
    z.hp=profile.hp+wave*.35; z.radius=profile.radius; z.active=True
    z.dying=False; z.death_timer=0; z.hurt_timer=0; z.fire_timer=0
    return z

def spawn_super_zombie(pool, enemy_type, x, y, fallback=()):
    """Acquire a fresh zombie from the pool as the doubled-stat "_super"
    variant of enemy_type, at (x, y) -- used by merge_touching_zombies, not
    the normal wave-based spawn_zombie above.

    (x, y) is the merged trio's centroid, which -- unlike each zombie's own
    already-validated position -- was never itself checked against the tile
    grid, and the super's bigger radius can push it into a wall the three
    smaller zombies were clear of. fallback (their three original positions)
    is tried in order if so; despawn_stuck_zombies below is the last-resort
    net if even those don't clear it (e.g. now-solid ground from a moved
    obstacle).
    """
    profile=ENEMY_TYPES[enemy_type]
    tiled_map=get_world_map()
    for cx,cy in ((x,y),)+tuple(fallback):
        if not rect_collides(tiled_map, cx, cy, profile.radius, profile.radius):
            x,y=cx,cy
            break
    z=pool.acquire()
    if not z:
        return None
    z.pos.x,z.pos.y=x,y
    z.enemy_type=enemy_type
    z.hp=profile.hp; z.radius=profile.radius; z.active=True
    z.dying=False; z.death_timer=0; z.hurt_timer=0; z.fire_timer=0
    return z

def despawn_stuck_zombies(pool, zombies):
    """Release any zombie whose current position overlaps a solid
    (Collisions-layer) tile. move_zombies only ever stops a zombie moving
    *further* into a wall -- it can't free one that started out embedded in
    one, whether from a spawn or merge edge case this module missed, or a
    map/obstacle change after the fact -- so this is the catch-all net."""
    tiled_map=get_world_map()
    for z in zombies:
        if z.active and not z.dying and rect_collides(tiled_map, z.pos.x, z.pos.y, z.radius, z.radius):
            pool.release(z)

def _touching(a, b):
    dx,dy=a.pos.x-b.pos.x,a.pos.y-b.pos.y
    return dx*dx+dy*dy <= (a.radius+b.radius)**2

def merge_touching_zombies(zombies, pool, spatial_hash):
    """Whenever three zombies of the same base type are all mutually
    touching each other at once -- a fully-connected trio, not just a
    three-long chain -- delete all three and spawn one bigger "_super"
    zombie of that type in their place (see ZOMBIE_MERGE_TARGET /
    ENEMY_TYPES), centered on where they were. They're fused, not killed:
    no score/xp/pickups, just like spawn_zombie's own zombies never granted
    anything on creation.

    spatial_hash: this frame's zombie SpatialHash (see game.spatial_hash) --
    used to only check a zombie against others actually near it, instead of
    brute-force scanning every same-type pair in the whole population. That
    brute-force version cost several ms/frame with a zombie horde clustered
    near the player (a common late-game scenario, and exactly when a
    triple like this is likely to actually occur) -- a real per-frame stall
    a spatial query avoids, since two zombies on opposite sides of the map
    are never candidates to begin with.
    """
    merged=set()
    for z in zombies:
        if id(z) in merged or not z.active or z.dying or z.enemy_type not in ZOMBIE_MERGE_TARGET:
            continue
        # Generous query radius: z.radius alone isn't enough, since the
        # *other two* zombies in a trio only need to touch z and each
        # other, not necessarily sit within z's own radius of z's center.
        reach = z.radius + MAX_ZOMBIE_RADIUS
        neighbors = [
            n for n in spatial_hash.query(z.pos.x, z.pos.y, reach)
            if n is not z and n.active and not n.dying and n.enemy_type == z.enemy_type
            and id(n) not in merged and _touching(z, n)
        ]
        for i, b in enumerate(neighbors):
            for c in neighbors[i + 1:]:
                if not _touching(b, c):
                    continue
                super_type = ZOMBIE_MERGE_TARGET[z.enemy_type]
                cx=(z.pos.x+b.pos.x+c.pos.x)/3; cy=(z.pos.y+b.pos.y+c.pos.y)/3
                fallback=((z.pos.x,z.pos.y),(b.pos.x,b.pos.y),(c.pos.x,c.pos.y))
                merged.add(id(z)); merged.add(id(b)); merged.add(id(c))
                pool.release(z); pool.release(b); pool.release(c)
                spawn_super_zombie(pool, super_type, cx, cy, fallback=fallback)
                break
            if id(z) in merged: break
