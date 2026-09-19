def fire(pool, x,y, dx,dy, speed, damage):
    b=pool.acquire()
    if not b:return None
    b.pos.x,b.pos.y,b.vx,b.vy,b.hp,b.damage,b.ttl=x,y,dx*speed,dy*speed,1,damage,1.5
    return b

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
    return min((z for z in candidates if z.active),
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
