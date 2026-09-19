from game.tilemap import get_world_map, has_line_of_sight

def fire(pool, x,y, dx,dy, speed, damage):
    b=pool.acquire()
    if not b:return None
    b.pos.x,b.pos.y,b.vx,b.vy,b.hp,b.damage,b.ttl=x,y,dx*speed,dy*speed,1,damage,1.5
    return b

def fire_beam(effect_pool, zombies, spatial_hash, x, y, dx, dy,
              max_range, damage):
    """Damage zombies intersecting an instant beam and pool its visual effect."""
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
        effect.ttl = 0.12
        effect.kind = "beam"

def nearest_target(player, zombies, spatial_hash=None, max_range=260,
                   viewport=None):
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
        if z.active and has_line_of_sight(tiled_map, player.pos.x, player.pos.y, z.pos.x, z.pos.y)
    )
    return min(candidates,
               key=lambda z:(z.pos.x-player.pos.x)**2+(z.pos.y-player.pos.y)**2,
               default=None)

def update_bullets(pool, zombies, dt, width, height, spatial_hash=None):
    hits=[]
    for b in pool.active():
        b.pos.x+=b.vx*dt; b.pos.y+=b.vy*dt; b.ttl-=dt
        if b.ttl<=0 or not(0<=b.pos.x<=width and 0<=b.pos.y<=height): pool.release(b); continue
        candidates = spatial_hash.query(b.pos.x, b.pos.y, b.radius + 6) if spatial_hash else zombies
        for z in candidates:
            if not z.active:
                continue
            if (b.pos.x-z.pos.x)**2+(b.pos.y-z.pos.y)**2 < (b.radius+z.radius)**2:
                z.hp-=b.damage; pool.release(b); hits.append(z); break
    return hits
