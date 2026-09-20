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
    facing: int = 0       # sprite row: 0=S,1=SW,2=NW,3=N,4=NE,5=SE,6=E,7=W
    anim_time: float = 0  # seconds elapsed, used to pick the walk-cycle column
    orb_active: bool = False
    orb_count: int = 0
    orb_angle: float = 0.0
    orb_fire_timer: float = 0.0

@dataclass
class Zombie(Entity):
    radius: float = 5
    hp: float = 2
    kind: str = "zombie"
    enemy_type: str = "walker"
    facing_right: bool = True  # mirrors the (right-facing) walk sprite when moving left
    anim_time: float = 0       # seconds elapsed, scaled by speed, picks the walk-cycle frame

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

@dataclass
class Shop:
    """The mobile shop van: drives to a random empty spot, running over
    anything in its path, parks there to do business for a while, then picks
    a new destination. A singleton, not pool-managed, so it doesn't share
    Entity's active/ttl/vx/vy pooling fields. See game.systems.shop."""
    pos: Vec2 = None
    dest: Vec2 = None
    state: str = "parked"            # "parked" or "driving"
    park_timer: float = 0.0          # counts down while parked; drives again at 0
    orientation: str = "horizontal"  # "horizontal" or "vertical" -- current hitbox shape
    frame: int = 0                   # rotation frame index into the van spritesheet (0-47)
    heading: tuple = (1, 0)          # last tile-step direction driven; steering keeps this
                                      # over an equally-short alternative, to minimize turns
    pivot_timer: float = 0.0         # counts down during a turn's frame-sweep animation
    pivot_from_frame: int = 0        # frame the current turn's sweep started at
    pivot_span: int = 0              # signed frame delta the current sweep covers
    pivot_duration: float = 0.0      # total duration of the current sweep (scales with its size)
    stuck_timer: float = 0.0         # seconds of zero progress while driving; triggers backing up
    backup_timer: float = 0.0        # counts down while reversing away from an obstruction
    trouble_time: float = 0.0        # cumulative seconds spent backing up on the current trip;
                                      # past SHOP_GIVE_UP_THRESHOLD the van picks a new destination
    def __post_init__(self):
        if self.pos is None: self.pos = Vec2()
        if self.dest is None: self.dest = Vec2()
