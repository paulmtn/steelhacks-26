"""Fixed-layout entity records; inactive records are reused by pools."""
from dataclasses import dataclass
from game.data import Vec2
from game.config import PICKUP_LIFETIME

@dataclass
class Entity:
    active: bool = False
    pos: Vec2 = None
    radius: float = 4
    hp: float = 1
    ttl: float = 0
    kind: str = ""
    vx: float = 0; vy: float = 0
    damage: int = 1
    def __post_init__(self):
        if self.pos is None: self.pos = Vec2()

@dataclass
class Player(Entity):
    radius: float = 6
    hp: float = 100
    kind: str = "player"
    xp: float = 0
    level: int = 1
    gems: int = 0
    magnet: float = 48
    shots: int = 1
    invulnerable: float = 0

@dataclass
class Zombie(Entity):
    radius: float = 5
    hp: float = 2
    kind: str = "zombie"
    enemy_type: str = "walker"

@dataclass
class Bullet(Entity):
    radius: float = 2
    ttl: float = 1.5
    kind: str = "bullet"

@dataclass
class Particle(Entity):
    radius: float = 1
    ttl: float = .5
    kind: str = "particle"

@dataclass
class Pickup(Entity):
    radius: float = 3
    ttl: float = PICKUP_LIFETIME
    amount: int = 1
    kind: str = "xp"
