"""Fixed-layout entity records; inactive records are reused by pools."""
from dataclasses import dataclass
import math
from game.data import Vec2
from game.config import PICKUP_LIFETIME, ORB_ORBIT_DISTANCE

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
    shots: int = 1
    invulnerable: float = 0
    facing: int = 0       # sprite row: 0=S,1=SW,2=NW,3=N,4=NE,5=SE,6=E,7=W
    anim_time: float = 0  # seconds elapsed, used to pick the walk-cycle column
    is_firing: bool = False  # has a live auto-fire target; picks which sheet draw_player uses
    is_moving: bool = False  # holding a movement key; walk-cycle sheets vs stationary ones
    orb_active: bool = False
    orb_count: int = 0
    orb_angle: float = 0.0
    orb_fire_timer: float = 0.0
    dying: bool = False        # true once health hits 0; plays the death sheet once (see draw_player)
    death_timer: float = 0.0   # counts down the death sheet's duration; holds on the last frame at 0

class OrbAnchor:
    """Live stand-in for one orbiting orb, used as a beam Particle's source
    (see Particle.source) so the drawn beam tracks that orb's *current*
    orbit position -- not the player's -- for its short life, instead of
    freezing at (or being anchored to the player's) fire-time position."""
    def __init__(self, player, orb_index, orb_count):
        self.player, self.orb_index, self.orb_count = player, orb_index, orb_count

    @property
    def active(self):
        return self.player.active

    @property
    def pos(self):
        angle = self.player.orb_angle + (2 * math.pi * self.orb_index / self.orb_count)
        return Vec2(
            self.player.pos.x + math.cos(angle) * ORB_ORBIT_DISTANCE,
            self.player.pos.y + math.sin(angle) * ORB_ORBIT_DISTANCE,
        )

@dataclass
class Zombie(Entity):
    radius: float = 5
    hp: float = 2
    kind: str = "zombie"
    enemy_type: str = "walker"
    facing_right: bool = True  # mirrors the (right-facing) walk sprite when moving left
    anim_time: float = 0       # seconds elapsed, scaled by speed, picks the walk-cycle frame
    hurt_timer: float = 0.0    # counts down while showing the brief "hurt" flash sheet
    dying: bool = False        # true from the killing blow until its death animation finishes
    death_timer: float = 0.0   # counts down the "death" sheet; released from the pool at 0
    fire_timer: float = 0.0    # counts down between shots -- only "_super" zombies ever fire
                                # (see game.systems.combat.fire_zombie_bullets)

@dataclass
class Bullet(Entity):
    radius: float = 2
    ttl: float = 1.5
    kind: str = "bullet"
    # Shooter's enemy_type, set only by fire_zombie_bullets -- lets the end
    # screen say which zombie type's gunfire killed the player (see
    # update_enemy_bullets' on_hit callback). Unused by the player's own bullets.
    enemy_type: str = ""

@dataclass
class Particle(Entity):
    radius: float = 1
    ttl: float = .5
    kind: str = "particle"
    # Live endpoints for beam/lightning effects: whatever entity fired it
    # (the player, or the previously struck zombie in a lightning chain) and
    # whatever it's hitting. draw_world reads their *current* .pos each frame
    # so the line stays stretched between the two while they move, instead of
    # freezing at (or rigidly translating) the positions they had when the
    # effect was fired. None falls back to the static spawn-time pos/vx/vy.
    source: object = None
    target: object = None
    # Amount shown by a "xp_text" popup (see progression.cleanup_dead); unused
    # by every other kind.
    amount: float = 0

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
