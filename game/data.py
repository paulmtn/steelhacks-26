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

ENEMY_TYPES = {
    "walker": EnemyType("walker", 18, 2, 10, 3),
    "runner": EnemyType("runner", 30, 1, 7, 9),
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
