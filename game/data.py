"""Small value objects shared by systems."""
from dataclasses import dataclass, field
from typing import List

@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0

@dataclass
class Upgrade:
    name: str
    cost: int
    description: str

@dataclass
class SaveData:
    coins: int = 0
    high_score: int = 0
    upgrades: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class EnemyType:
    name: str
    speed: float
    hp: float
    contact_damage: float
    color: int

# Only two zombie classes, each with its own walk-cycle sprite (see
# render.assets.ZOMBIE_SHEETS) -- the old plain-circle "walker"/"runner"
# have been removed. Stats stay relative to that original walker baseline
# (speed 18, hp 2): runner is 2x speed / 1/2 hp, walker is 1/2 speed / 2x hp.
ENEMY_TYPES = {
    "walker": EnemyType("walker", 9, 4, 10, 14),   # slow, tanky -- Blood Monster_A_Walk
    "runner": EnemyType("runner", 36, 1, 10, 8),   # fast, fragile -- Demon_A_Walk
}

@dataclass(frozen=True)
class Ability:
    name: str
    description: str
    cost: int

ABILITIES = [
    Ability("Sharpshooter", "+1 projectile damage", 0),
    Ability("Haste", "fire 12% faster", 0),
    Ability("Fleet Feet", "+12 movement speed", 0),
    Ability("Magnetism", "+32 pickup radius", 0),
    Ability("Twin Shot", "+1 auto-fire projectile", 0),
    Ability("Thick Skin", "+20 maximum health", 0),
    Ability("Scavenger", "+20% XP from all sources", 0),
    Ability("Job's Orb", "orbiting orb fires at zombies", 0),
]

SHOP_ITEMS = [
    Ability("Medkit", "restore 35 health", 8),
    Ability("Arsenal", "+1 damage", 12),
    Ability("Boots", "+10 movement speed", 14),
]
