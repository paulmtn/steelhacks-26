"""Deterministic fixed pools: gameplay never allocates entities during a wave."""
from game.entities import Zombie, Bullet, Particle, Pickup

class Pool:
    def __init__(self, factory, capacity):
        self.items = [factory() for _ in range(capacity)]
    def acquire(self):
        for item in self.items:
            if not item.active:
                item.active = True
                return item
        return None
    def release(self, item): item.active = False
    def active(self): return (x for x in self.items if x.active)

class EntityPools:
    def __init__(self, zombies, bullets, particles, pickups=80, enemy_bullets=64):
        self.zombies = Pool(Zombie, zombies); self.bullets = Pool(Bullet, bullets)
        self.particles = Pool(Particle, particles); self.pickups = Pool(Pickup, pickups)
        # Zombie-fired bullets (see game.systems.combat.fire_zombie_bullets)
        # get their own pool, kept separate from the player's own so the two
        # never get mixed up over who they're allowed to hit.
        self.enemy_bullets = Pool(Bullet, enemy_bullets)
