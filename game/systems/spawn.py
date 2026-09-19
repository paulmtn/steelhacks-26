import random
from game.config import WORLD_WIDTH, WORLD_HEIGHT
from game.data import ENEMY_TYPES

def spawn_zombie(pool, wave):
    z=pool.acquire()
    if not z:return None
    edge=random.randrange(4); z.pos.x=random.uniform(5*16,WORLD_WIDTH-5*16) if edge<2 else (5*16 if edge==2 else WORLD_WIDTH-5*16); z.pos.y=(5*16 if edge==0 else WORLD_HEIGHT-5*16) if edge<2 else random.uniform(5*16,WORLD_HEIGHT-5*16)
    z.enemy_type="runner" if wave >= 4 and random.random() < .15 else "walker"
    profile=ENEMY_TYPES[z.enemy_type]
    z.hp=profile.hp+wave*.35; z.radius=5; z.active=True; return z
