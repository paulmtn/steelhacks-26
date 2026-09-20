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
    radius: float = 5

# Only two base zombie classes, each with its own walk-cycle sprite (see
# render.assets.ZOMBIE_SHEETS) -- the old plain-circle "walker"/"runner"
# have been removed. Stats stay relative to that original walker baseline
# (speed 18, hp 2): runner is 2x speed / 1/2 hp, walker is 1/2 speed / 2x hp.
#
# "_super" variants aren't spawned directly (see game.systems.spawn.spawn_zombie)
# -- they're what three of the same base type become when they're ever all
# mutually touching at once (see ZOMBIE_MERGE_TARGET and
# game.systems.spawn.merge_touching_zombies): 3x health, 2x speed, 2x melee
# (contact_damage) damage, and a doubled hitbox/sprite scale, relative to
# their base type. Their ranged attack (see
# game.systems.combat.fire_zombie_bullets) deals the *base* type's own
# (unmultiplied) contact_damage instead -- the melee buff doesn't carry over
# to their bullets. They reuse their base type's art at 2x scale rather than
# needing new sheets (see ZOMBIE_BASE_TYPE / render.assets.ZOMBIE_SUPER_SCALE).
ENEMY_TYPES = {
    "walker": EnemyType("walker", 9, 4, 10, 14),   # slow, tanky -- Blood Monster_A_Walk
    "runner": EnemyType("runner", 36, 1, 10, 8),   # fast, fragile -- Demon_A_Walk
    "walker_super": EnemyType("walker_super", 9 * 2, 4 * 3, 10 * 2, 14, radius=10),
    "runner_super": EnemyType("runner_super", 36 * 2, 1 * 3, 10 * 2, 8, radius=10),
}

# Base zombie type -> the bigger type it merges into (see ENEMY_TYPES above
# and game.systems.spawn.merge_touching_zombies). Only base types are keys
# here -- a super zombie doesn't merge further.
ZOMBIE_MERGE_TARGET = {"walker": "walker_super", "runner": "runner_super"}

# The reverse of ZOMBIE_MERGE_TARGET -- a "_super" type's own base type.
# Used wherever a super needs to fall back to its base type's own stats or
# art instead of its own (e.g. bullet damage in fire_zombie_bullets, or the
# sprite sheet in render.assets.get_zombie_sheet).
ZOMBIE_BASE_TYPE = {super_type: base_type for base_type, super_type in ZOMBIE_MERGE_TARGET.items()}

# Only "_super" zombies fight at range -- they shoot at the player instead of
# closing to melee once they're close enough (see
# game.systems.combat.fire_zombie_bullets and
# game.systems.movement.move_zombies' RANGED_ZOMBIE_STOP_TILES). Base
# zombies are melee-only and always keep closing the distance.
RANGED_ZOMBIE_TYPES = frozenset(ZOMBIE_MERGE_TARGET.values())

# Human-readable names for the end screen's "killed by" message (see
# main.Game._apply_player_hit / render.draw's GAME_OVER overlay).
ZOMBIE_DISPLAY_NAMES = {
    "walker": "a Ghoul",
    "runner": "a Demon",
    "walker_super": "an Archghoul",
    "runner_super": "an Archdemon",
}

# The biggest a zombie's hitbox can ever be -- used to size broad-phase
# spatial-hash queries that need to catch a zombie by its edge, not just its
# center (contact damage, bullet hits, AoE splash), so a search box sized for
# the old fixed radius doesn't undershoot once "_super" zombies (radius 10)
# exist. Derived from ENEMY_TYPES instead of hardcoded so a future bigger
# type can't silently reintroduce the same gap.
MAX_ZOMBIE_RADIUS = max(enemy_type.radius for enemy_type in ENEMY_TYPES.values())

@dataclass(frozen=True)
class Ability:
    name: str
    description: str
    cost: int
    currency: str = "coins"
    stock: int | None = 10

ABILITIES = [
    Ability("Sharpshooter", "+1 damage and fire 12% faster", 0),
    Ability("Twin Shot", "+1 auto-fire projectile", 0),
    Ability("Thick Skin", "+20 maximum health", 0),
    Ability("Job's Orb", "orbiting orb fires at zombies", 0),
    Ability("Hedge of Protection", "blocks one hit per upgrade; regenerates in 10s", 0),
    Ability("Fire from Heaven", "adds a player-to-zombie lightning chain", 0),
    Ability("Morning Star", "add up to 8 spikes; more spikes deal more damage", 0),
    Ability("Storehouse of Hail", "larger hail storm; upgrades deal more damage", 0),
]

SHOP_ITEMS = [
    Ability("Medkit", "restore 35 health", 8),
    Ability("Arsenal", "+1 damage", 12),
    Ability("Boots", "+3% movement speed", 14),
    Ability("Extra Life", "revive once when health reaches zero", 20, "gems", 1),
    Ability("Double XP", "double XP gained for this run", 15, "gems", 1),
]
