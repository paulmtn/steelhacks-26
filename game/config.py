"""Tunable constants for the zombie survival game."""
WIDTH, HEIGHT, FPS = 256, 144, 60
# Matches untitled.json: a 64x64 tile map at 16px tiles.
WORLD_WIDTH, WORLD_HEIGHT = 1024, 1024
CELL_SIZE = 32
MAX_ZOMBIES, MAX_BULLETS, MAX_PARTICLES, MAX_PICKUPS = 160, 96, 192, 80
PLAYER_SPEED, BULLET_SPEED = 70.0, 210.0
ORB_ORBIT_DISTANCE, ORB_FIRE_RATE = 18.0, 1.4
ORB_BULLET_SPEED, ORB_DAMAGE = 150.0, 1
SHIELD_REGEN_TIME = 10.0
SHIELD_RADIUS = 12.0
FIRE_FROM_HEAVEN_RATE, FIRE_FROM_HEAVEN_DAMAGE = 3.5, 3
FIRE_FROM_HEAVEN_CHAIN_RANGE, FIRE_FROM_HEAVEN_CHAIN_COUNT = 64.0, 2
MORNING_STAR_DISTANCE, MORNING_STAR_DAMAGE, MORNING_STAR_HIT_RATE = 23.0, 2, 0.35
MAX_MORNING_STARS = 8
HAIL_RATE, HAIL_RADIUS, HAIL_DAMAGE = 4.0, 56.0, 2
ZOMBIE_SPEED, ZOMBIE_DAMAGE = 18.0, 10.0
BULLET_COIN_RADIUS, BULLET_FULL_RADIUS = 1, 3  # visual size: coin-sized at base damage, full size once ramped up
BULLET_DAMAGE_RAMP = 4  # points of damage above the base needed to reach BULLET_FULL_RADIUS
SPAWN_INTERVAL, PICKUP_RADIUS = .8, 18.0
PICKUP_MAGNET_SPEED = 200.0
PICKUP_CLOSE_MAGNET_RADIUS = 16.0
PICKUP_CLOSE_MAGNET_SPEED = 360.0
# How close a magnetized pickup has to get to the player to actually be
# collected. Was 2px -- close enough that the per-frame magnet step could
# converge to just above it and never quite close the gap, leaving pickups
# visibly stuck to the player without being picked up.
PICKUP_COLLECT_RADIUS = 6.0
PICKUP_LIFETIME = 20.0
GEM_DROP_CHANCE = 0.10
XP_TEXT_DURATION = 0.8  # seconds an XP-gained popup floats before disappearing
XP_TEXT_RISE_SPEED = 18.0  # px/sec the popup floats upward
DT_MAX = .05
CONTACT_INVULN = .8
SURVIVAL_TARGET = 999999
PLAYER_ANIM_FPS = 10.0
ZOMBIE_ANIM_FPS = 8.0  # shared baseline walk-cycle rate; also scaled per-zombie by actual speed (see move_zombies)
WALKER_ANIM_FPS_BOOST = 1.5  # walker's frame rate is 50% faster than the shared baseline
ZOMBIE_HURT_DURATION = 0.25  # seconds a zombie plays its "hurt" flash sheet after taking damage and surviving
ZOMBIE_DEATH_DURATION = 0.5  # seconds a zombie plays its "death" sheet before being removed from the pool
PLAYER_DEATH_DURATION = 1.0  # seconds the player plays its death sheet before the screen pauses
GAME_OVER_PAUSE = 1.5  # seconds the screen holds on the player's final death frame before the end screen appears
SHOP_PARK_DURATION = 30.0  # seconds parked (open for business) before driving to a new destination
SHOP_HITBOX_LONG = 5 * 16   # 80px: the van's hitbox long side (5 tiles)
SHOP_HITBOX_SHORT = 3 * 16  # 48px: the van's hitbox short side (3 tiles)
SHOP_PIVOT_DURATION = 0.2  # seconds for a 90-degree turn's frame-sweep animation (paced ~1 sheet-frame per engine tick at 60fps, so it doesn't skip frames)
SHOP_STUCK_THRESHOLD = 0.4  # seconds of zero progress while driving before the van tries backing up
SHOP_BACKUP_DURATION = 0.5  # seconds spent reversing once stuck, before trying forward pathing again
SHOP_GIVE_UP_THRESHOLD = 2.0  # cumulative seconds spent backing up on one trip before abandoning that destination for a new one
MAX_ENEMY_BULLETS = 64
ZOMBIE_BULLET_SPEED = BULLET_SPEED  # "_super" zombies shoot at the same speed the player's own bullets travel at
ZOMBIE_BULLET_RADIUS = 2
ZOMBIE_FIRE_RATE = 1.5       # seconds between shots, per "_super" zombie (see game.systems.combat.fire_zombie_bullets)
ZOMBIE_BULLET_RANGE = 260.0  # mirrors nearest_target's own default max_range -- the same "must be in range" rule, from the zombie's side
RANGED_ZOMBIE_STOP_TILES = 6  # "_super" zombies stop closing the distance once this close, and shoot instead (see game.systems.movement.move_zombies)
