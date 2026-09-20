from game.pools import Pool
from game.entities import Zombie, Bullet
from game.data import ABILITIES, SHOP_ITEMS, Vec2, ENEMY_TYPES, ZOMBIE_MERGE_TARGET
from game.systems.spawn import spawn_zombie, spawn_super_zombie, merge_touching_zombies
from game.spatial_hash import SpatialHash
from game.state import StateMachine, GameMode, PlayerProgress, combined_score
from game.save import load_save, save_high_score
from game.entities import Player, Pickup
from game.systems.progression import buy, buy_permanent, collect_pickups, cleanup_dead, tick_zombie_hit_effects
from game.pools import EntityPools
from game.systems.combat import nearest_target, update_bullets, damage_at_point, fire_zombie_bullets, update_enemy_bullets
from game.systems.movement import move_player, move_zombies
from game.tilemap import get_world_map, TiledMap, compute_distance_field
from game.systems.combat import fire_beam
from game.systems.progression import apply_ability
import game.systems.movement as movement_module
import game.systems.combat as combat_module
import game.systems.shop as shop_module
import game.tilemap as tilemap_module
from game.entities import Shop
from game.systems.shop import (
    update_shop, _frame_for_direction, _half_extents, _steer_minimizing_turns,
    shop_obstacle, shop_touching, SHOP_VAN_SPEED,
)
from game.config import (
    SHOP_PARK_DURATION, SHOP_HITBOX_LONG, SHOP_HITBOX_SHORT, SHOP_PIVOT_DURATION,
    SHOP_STUCK_THRESHOLD, SHOP_GIVE_UP_THRESHOLD,
    ZOMBIE_HURT_DURATION, ZOMBIE_DEATH_DURATION,
    ZOMBIE_BULLET_RANGE, ZOMBIE_FIRE_RATE, ZOMBIE_BULLET_SPEED,
    MAX_ZOMBIES, WORLD_WIDTH, WORLD_HEIGHT,
)

def test_pool_is_fixed_and_reuses():
    p=Pool(Zombie,1); z=p.acquire(); assert z and p.acquire() is None; p.release(z); assert p.acquire() is z

def test_spatial_hash_candidates():
    h=SpatialHash(10); z=Zombie(active=True,pos=Vec2(11,11)); h.insert(z); assert z in h.query(10,10,2)

def test_state_and_merchant():
    s=StateMachine(); s.transition(GameMode.PLAYING); assert s.mode is GameMode.PLAYING
    p=PlayerProgress(coins=12, shop_inventory=["Arsenal"])
    assert buy(p,'damage'); assert p.damage==2 and p.coins==0

def test_pickups_are_magnetized_toward_player():
    player = Player(active=True, pos=Vec2(0, 0))
    pickup = Pickup(active=True, pos=Vec2(10, 0), kind="gold", amount=1)
    progress = PlayerProgress(magnet=50)

    collect_pickups(player, (pickup,), progress, dt=0.1)

    assert pickup.pos.x < 10
    assert pickup.pos.x > 0

def test_magnet_upgrade_actually_widens_pickup_range():
    player = Player(active=True, pos=Vec2(0, 0))
    pickup = Pickup(active=True, pos=Vec2(60, 0), kind="gold", amount=1)
    progress = PlayerProgress(coins=20)

    # Out of range before the upgrade -- buy_permanent's "Magnet" branch
    # raises progress.magnet, which collect_pickups must actually read for
    # this purchase to do anything.
    collect_pickups(player, (pickup,), progress, dt=0.1)
    assert pickup.pos.x == 60

    assert buy_permanent(progress, "Magnet")
    collect_pickups(player, (pickup,), progress, dt=0.1)
    assert pickup.pos.x < 60

def test_shop_stock_prices_and_gem_items():
    progress = PlayerProgress(
        coins=100,
        gems=40,
        shop_inventory=["Arsenal", "Extra Life", "Double XP", "Boots"],
    )
    assert buy(progress, "Arsenal")
    assert progress.damage == 2
    assert progress.shop_items["Arsenal"] == 9
    first_coins = progress.coins
    assert buy(progress, "Arsenal")
    assert first_coins - progress.coins == 14
    assert buy(progress, "Extra Life")
    assert progress.extra_lives == 1
    assert progress.shop_items["Extra Life"] == 0
    assert not buy(progress, "Extra Life")
    assert buy(progress, "Double XP")
    assert progress.xp_multiplier == 2.0
    assert progress.shop_items["Double XP"] == 0
    assert not buy(progress, "Double XP")

def test_shop_has_four_randomly_selected_items():
    progress = PlayerProgress()
    assert len(progress.shop_inventory) == 4
    assert len(set(progress.shop_inventory)) == 4
    assert set(progress.shop_inventory).issubset({item.name for item in SHOP_ITEMS})

def test_magnetism_is_not_a_level_up_ability():
    assert all(ability.name != "Magnetism" for ability in ABILITIES)

def _find_interior_solid_tile():
    """A Collisions-layer tile with enough clearance on both sides for a
    horizontal approach test: 5 tiles of column margin gives the moving
    entity room to start left of the wall without world-bound clamping
    (move_player floors position at 3 tiles from the edge) jumping it past
    the wall in a single step; 3 tiles of row margin keeps the Y position
    off that same floor/ceiling. The map's current Collisions layer only
    marks a border band, so this deliberately doesn't require a deep,
    fully-interior tile -- just one with that much breathing room.
    """
    tm = get_world_map()
    gids = tm.layers["Collisions"]
    for i, gid in enumerate(gids):
        col, row = i % tm.width, i // tm.width
        if gid and 5 <= col <= tm.width - 5 and 3 <= row <= tm.height - 3:
            return tm, col, row
    raise AssertionError("no Collisions tile with enough clearance found to test against")

def test_player_cannot_walk_through_collision_tile():
    tm, col, row = _find_interior_solid_tile()
    wall_x = col * tm.tile_width
    player = Player(active=True, pos=Vec2(wall_x - 32, row * tm.tile_height + 8))
    for _ in range(400):
        move_player(player, 1, 0, 1 / 60, 70)
    assert player.pos.x + player.radius <= wall_x + 0.01

def test_zombies_cannot_walk_through_collision_tile():
    tm, col, row = _find_interior_solid_tile()
    wall_x = col * tm.tile_width
    wy = row * tm.tile_height + 8
    zombie = Zombie(active=True, pos=Vec2(wall_x - 32, wy))
    player = Player(active=True, pos=Vec2(wall_x + 64, wy))
    for _ in range(600):
        move_zombies([zombie], player, 1 / 60, 18)
    assert zombie.pos.x + zombie.radius <= wall_x + 0.01

def _wall_with_gap_map(width=10, height=10, tile_size=16, wall_row=5, gap_col=8):
    """A tile grid with one solid row except a single-tile gap, forcing any
    path across it to detour to that column."""
    data = [0] * (width * height)
    for col in range(width):
        if col != gap_col:
            data[wall_row * width + col] = 1
    return TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                     layers={"Collisions": data}, tilesets=[])

def test_distance_field_routes_around_a_wall_gap():
    tm = _wall_with_gap_map()
    tilemap_module._solid_tiles_cache.clear()
    field = compute_distance_field(tm, target_col=1, target_row=8)
    w = tm.width
    assert field[5 * w + 3] == -1          # solid wall tile: unreachable/blocked
    assert field[5 * w + 8] == 10          # the gap tile itself, on the direct route down
    # The top-left corner is only reachable by detouring sideways to the gap
    # column and back -- its BFS distance must exceed the straight-line (no
    # wall) Manhattan distance to the target, proving a real detour happened.
    direct_manhattan = abs(0 - 1) + abs(0 - 8)
    assert field[0] > direct_manhattan
    assert field[0] == 23

def test_zombies_path_around_walls_to_reach_player(monkeypatch):
    """A zombie separated from the player by a wall with a single gap must
    still reach the player -- proving it actually pathfinds through the gap
    rather than getting stuck pressed against the wall (which is what
    straight-line-plus-wall-slide movement would do here)."""
    tm = _wall_with_gap_map()
    tilemap_module._solid_tiles_cache.clear()
    movement_module._flow_field_cache.update(tiled_map_id=None, target=None, field=None)
    monkeypatch.setattr(movement_module, "get_world_map", lambda: tm)

    player = Player(active=True, pos=Vec2(1 * 16 + 8, 8 * 16 + 8))
    zombie = Zombie(active=True, pos=Vec2(1 * 16 + 8, 1 * 16 + 8))

    for _ in range(1200):
        move_zombies([zombie], player, 1 / 60, 40)
        if (zombie.pos.x - player.pos.x) ** 2 + (zombie.pos.y - player.pos.y) ** 2 < 4 ** 2:
            break
    else:
        raise AssertionError("zombie never reached the player around the wall")

def test_zombies_route_around_a_parked_van_instead_of_jamming_against_it(monkeypatch):
    """The van isn't part of the static Collisions layer the flow field is
    built from, so without telling the field about it separately (see
    game.systems.movement._obstacle_tiles) a zombie approaching it head-on
    would just jam against its edge forever instead of detouring -- the same
    failure test_zombies_path_around_walls_to_reach_player guards against for
    real walls."""
    tm = TiledMap(width=30, height=30, tile_width=16, tile_height=16,
                  layers={"Collisions": [0] * (30 * 30)}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    movement_module._flow_field_cache.update(tiled_map_id=None, target=None, obstacle=None, field=None)
    monkeypatch.setattr(movement_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(15 * 16 + 8, 15 * 16 + 8), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    zombie = Zombie(active=True, pos=Vec2(3 * 16 + 8, 15 * 16 + 8))
    player = Player(active=True, pos=Vec2(27 * 16 + 8, 15 * 16 + 8))

    for _ in range(3000):
        move_zombies([zombie], player, 1 / 60, 40, obstacle=obstacle)
        if (zombie.pos.x - player.pos.x) ** 2 + (zombie.pos.y - player.pos.y) ** 2 < 4 ** 2:
            break
    else:
        raise AssertionError("zombie never reached the player around the van")

def test_move_zombies_reuses_cached_field_within_the_same_tile(monkeypatch):
    """The flow field is recomputed only when the player crosses into a new
    tile -- the shared per-frame cost this whole approach relies on to stay
    fast regardless of zombie count. Moving the player without crossing a
    tile boundary must not trigger a recompute."""
    tm = _wall_with_gap_map()
    tilemap_module._solid_tiles_cache.clear()
    movement_module._flow_field_cache.update(tiled_map_id=None, target=None, field=None)
    monkeypatch.setattr(movement_module, "get_world_map", lambda: tm)

    calls = []
    real_compute = movement_module.compute_distance_field
    def counting_compute(*args, **kwargs):
        calls.append(1)
        return real_compute(*args, **kwargs)
    monkeypatch.setattr(movement_module, "compute_distance_field", counting_compute)

    player = Player(active=True, pos=Vec2(1 * 16 + 8, 8 * 16 + 8))
    zombie = Zombie(active=True, pos=Vec2(1 * 16 + 8, 1 * 16 + 8))
    move_zombies([zombie], player, 1 / 60, 40)
    assert len(calls) == 1
    for _ in range(5):
        player.pos.x += 0.1  # stays within the same tile
        move_zombies([zombie], player, 1 / 60, 40)
    assert len(calls) == 1

def test_auto_target_ignores_enemies_outside_viewport():
    player = Player(active=True, pos=Vec2(50, 50))
    visible = Zombie(active=True, pos=Vec2(60, 50))
    hidden = Zombie(active=True, pos=Vec2(400, 50))

    assert nearest_target(
        player,
        [visible, hidden],
        viewport=(0, 0, 256, 144),
    ) is visible

def test_nearest_target_ignores_enemies_behind_walls(monkeypatch):
    """A zombie directly behind a wall from the player must be skipped in
    favor of a farther-but-visible one -- proves auto-fire targeting no
    longer picks enemies it has no line of sight to."""
    width, height, tile_size = 10, 10, 16
    wall_col = 3
    data = [0] * (width * height)
    for row in range(height):
        data[row * width + wall_col] = 1
    tm = TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                  layers={"Collisions": data}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    player = Player(active=True, pos=Vec2(1 * tile_size + 8, 5 * tile_size + 8))
    near_but_hidden = Zombie(active=True, pos=Vec2(5 * tile_size + 8, 5 * tile_size + 8))   # closer, behind the wall
    far_but_visible = Zombie(active=True, pos=Vec2(0 * tile_size + 8, 0 * tile_size + 8))   # farther, clear line of sight
    grid = SpatialHash(32)
    grid.insert(near_but_hidden)
    grid.insert(far_but_visible)

    assert nearest_target(player, [near_but_hidden, far_but_visible], grid, max_range=200) is far_but_visible

def test_nearest_target_ignores_enemies_behind_the_van(monkeypatch):
    """The parked van isn't a Collisions-layer wall, so has_line_of_sight
    needs its obstacle rect passed in separately (see nearest_target's
    obstacle parameter) to block auto-aim the same way a wall tile does --
    otherwise the player could auto-fire straight through its own shop."""
    tm = TiledMap(width=10, height=10, tile_width=16, tile_height=16,
                  layers={"Collisions": [0] * (10 * 10)}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(5 * 16 + 8, 5 * 16 + 8), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    player = Player(active=True, pos=Vec2(1 * 16 + 8, 5 * 16 + 8))
    near_but_hidden = Zombie(active=True, pos=Vec2(5 * 16 + 8, 5 * 16 + 8))   # closer, inside/behind the van
    far_but_visible = Zombie(active=True, pos=Vec2(0 * 16 + 8, 0 * 16 + 8))   # farther, clear line of sight
    grid = SpatialHash(32)
    grid.insert(near_but_hidden)
    grid.insert(far_but_visible)

    assert nearest_target(
        player, [near_but_hidden, far_but_visible], grid, max_range=200, obstacle=obstacle,
    ) is far_but_visible

def test_bullets_are_destroyed_by_the_parked_van():
    """Bullets otherwise fly clean through everything but zombies -- there's
    no wall collision for them at all -- but the van is a physical obstacle
    like the player and zombies are (see shop_obstacle), so a bullet flying
    into it should be destroyed there instead of passing through to
    whatever's behind it."""
    pool = Pool(Bullet, 1)
    bullet = pool.acquire()
    bullet.pos.x, bullet.pos.y = 400, 500
    bullet.vx, bullet.vy = 200, 0
    bullet.ttl, bullet.radius = 1.5, 2

    shop = Shop(pos=Vec2(500, 500), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)

    for _ in range(120):
        update_bullets(pool, [], 1 / 60, 2000, 2000, obstacle=obstacle)
        if not bullet.active:
            break
    else:
        raise AssertionError("bullet was never stopped by the van")
    # Destroyed at/before the van's near edge -- proves it didn't fly through
    # to the far side (which would put it well past x=500).
    assert bullet.pos.x < 500

def test_bullets_pass_through_a_driving_van():
    """A moving van doesn't block anything -- it deals contact damage
    instead (see game.systems.shop.update_shop) -- so shop_obstacle returns
    None while driving and bullets must fly straight through it."""
    pool = Pool(Bullet, 1)
    bullet = pool.acquire()
    bullet.pos.x, bullet.pos.y = 400, 500
    bullet.vx, bullet.vy = 200, 0
    bullet.ttl, bullet.radius = 1.5, 2

    shop = Shop(pos=Vec2(500, 500), state="driving", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    assert obstacle is None

    for _ in range(60):
        update_bullets(pool, [], 1 / 60, 2000, 2000, obstacle=obstacle)
    assert bullet.active and bullet.pos.x > 500

def test_demo_mode_triples_pickup_rewards():
    pools = EntityPools(1, 1, 1, 2)
    zombie = pools.zombies.acquire()
    zombie.active = True
    zombie.hp = 0
    zombie.pos = Vec2(10, 10)
    progress = PlayerProgress()

    cleanup_dead([zombie], pools, progress, reward_multiplier=3, gem_drop_chance=1)

    pickups = list(pools.pickups.active())
    assert sorted((pickup.kind, pickup.amount) for pickup in pickups) == [
        ("gold", 3),
        ("xp", 3),
    ]
    assert progress.xp == 3

def test_every_kill_grants_xp_without_a_gem():
    pools = EntityPools(1, 1, 1, 1)
    zombie = pools.zombies.acquire()
    zombie.active = True
    zombie.hp = 0
    progress = PlayerProgress()

    cleanup_dead([zombie], pools, progress, gem_drop_chance=0)

    assert progress.xp == 1
    assert list(pools.pickups.active())[0].kind == "gold"

def test_cleanup_dead_marks_dying_instead_of_releasing_immediately():
    pools = EntityPools(1, 1, 1, 1)
    zombie = pools.zombies.acquire()
    zombie.active = True
    zombie.hp = 0
    progress = PlayerProgress()

    cleanup_dead([zombie], pools, progress, gem_drop_chance=0)

    assert zombie.dying
    assert zombie.death_timer == ZOMBIE_DEATH_DURATION
    assert zombie.active  # still occupies its pool slot, still drawable
    assert list(pools.zombies.active()) == [zombie]

def test_cleanup_dead_does_not_double_reward_an_already_dying_zombie():
    pools = EntityPools(1, 1, 1, 1)
    zombie = pools.zombies.acquire()
    zombie.active = True
    zombie.hp = 0
    progress = PlayerProgress()

    cleanup_dead([zombie], pools, progress, gem_drop_chance=0)
    cleanup_dead([zombie], pools, progress, gem_drop_chance=0)

    assert progress.xp == 1

def test_tick_zombie_hit_effects_releases_zombie_after_death_animation():
    pools = EntityPools(1, 1, 1, 1)
    zombie = pools.zombies.acquire()
    zombie.active = True
    zombie.hp = 0
    progress = PlayerProgress()
    cleanup_dead([zombie], pools, progress, gem_drop_chance=0)

    tick_zombie_hit_effects([zombie], pools.zombies, dt=ZOMBIE_DEATH_DURATION / 2)
    assert zombie.active  # animation not finished yet

    tick_zombie_hit_effects([zombie], pools.zombies, dt=ZOMBIE_DEATH_DURATION / 2 + 0.01)
    assert not zombie.active  # released once the death animation finishes

def test_tick_zombie_hit_effects_decays_hurt_timer_without_releasing():
    zombie = Zombie(active=True, hurt_timer=ZOMBIE_HURT_DURATION)
    pool = Pool(Zombie, 1)

    tick_zombie_hit_effects([zombie], pool, dt=ZOMBIE_HURT_DURATION / 2)
    assert 0 < zombie.hurt_timer < ZOMBIE_HURT_DURATION
    assert zombie.active

    tick_zombie_hit_effects([zombie], pool, dt=ZOMBIE_HURT_DURATION)
    assert zombie.hurt_timer == 0
    assert zombie.active  # surviving a hit never releases the zombie

def test_uncollected_pickups_expire_and_free_pool_slots():
    player = Player(active=True, pos=Vec2(0, 0))
    pickup = Pickup(active=True, pos=Vec2(100, 0), kind="gold", amount=1, ttl=0.1)
    progress = PlayerProgress(magnet=0)

    collect_pickups(player, (pickup,), progress, dt=0.1)

    assert not pickup.active

def test_new_abilities_modify_health_and_xp_gain():
    progress = PlayerProgress()
    apply_ability(progress, "Thick Skin")
    assert progress.max_health == 120
    assert progress.health == 120

    apply_ability(progress, "Sharpshooter")
    assert progress.damage == 2
    assert progress.fire_rate == 0.35 * 0.88

    assert not progress.orb_active
    apply_ability(progress, "Job's Orb")
    assert progress.orb_active
    assert progress.orb_count == 1
    apply_ability(progress, "Job's Orb")
    apply_ability(progress, "Job's Orb")
    apply_ability(progress, "Job's Orb")
    apply_ability(progress, "Job's Orb")
    apply_ability(progress, "Job's Orb")
    assert progress.orb_count == 5

def test_new_combat_abilities_are_unlockable():
    progress = PlayerProgress()

    assert apply_ability(progress, "Hedge of Protection")
    assert progress.shield_unlocked
    assert progress.shield_ready
    assert progress.shield_hits == 1
    apply_ability(progress, "Hedge of Protection")
    assert progress.shield_max_hits == 2
    assert progress.shield_hits == 2
    assert apply_ability(progress, "Fire from Heaven")
    assert progress.fire_from_heaven_active
    assert progress.fire_from_heaven_count == 1
    apply_ability(progress, "Fire from Heaven")
    assert progress.fire_from_heaven_count == 2
    assert apply_ability(progress, "Morning Star")
    assert progress.morning_star_active
    assert progress.morning_star_count == 1
    apply_ability(progress, "Morning Star")
    assert progress.morning_star_count == 2
    for _ in range(5):
        apply_ability(progress, "Morning Star")
    assert progress.morning_star_count == 7
    apply_ability(progress, "Morning Star")
    apply_ability(progress, "Morning Star")
    assert progress.morning_star_count == 8
    apply_ability(progress, "Morning Star")
    assert progress.morning_star_count == 8
    assert apply_ability(progress, "Storehouse of Hail")
    assert progress.hail_active
    assert progress.hail_level == 1
    apply_ability(progress, "Storehouse of Hail")
    assert progress.hail_level == 2

def test_ui_text_wraps_at_word_boundaries():
    from render.draw import wrap_text

    lines = wrap_text("Storehouse of Hail deals more damage", 16)
    assert lines == ["Storehouse of", "Hail deals more", "damage"]

def test_combat_ability_helpers_damage_zombies():
    pools = EntityPools(3, 1, 3, 1)
    first = pools.zombies.acquire()
    first.active, first.hp, first.pos = True, 5, Vec2(30, 0)
    second = pools.zombies.acquire()
    second.active, second.hp, second.pos = True, 5, Vec2(0, 20)
    grid = SpatialHash(32)
    grid.insert(first)
    grid.insert(second)

    from game.systems.combat import damage_at_point, hail_burst, strike_random_zombie
    assert damage_at_point((first, second), grid, 30, 0, 5, 2)
    assert first.hp == 3
    hail_burst(pools.particles, (first, second), grid, 0, 0, 25, 1)
    assert second.hp == 4
    assert strike_random_zombie(pools.particles, (first, second), 1)
    assert first.hp < 3 or second.hp < 4
    lightning = next(effect for effect in pools.particles.active() if effect.kind == "lightning")
    assert lightning.ttl > 0

def test_orb_beam_hits_zombies_on_horizontal_ray():
    pools = EntityPools(2, 1, 2, 1)
    first = pools.zombies.acquire()
    first.active, first.hp, first.pos = True, 2, Vec2(30, 0)
    second = pools.zombies.acquire()
    second.active, second.hp, second.pos = True, 2, Vec2(30, 20)
    grid = SpatialHash(32)
    grid.insert(first)
    grid.insert(second)

    fire_beam(pools.particles, [first, second], grid, 0, 0, 1, 0, 50, 1)

    assert first.hp == 1
    assert second.hp == 2
    assert next(pools.particles.active()).kind == "beam"

def test_shop_van_speed_is_twice_the_fast_monster():
    from game.data import ENEMY_TYPES
    assert SHOP_VAN_SPEED == ENEMY_TYPES["runner"].speed * 2

def test_shop_frame_calibration_matches_the_eight_compass_directions():
    """The van sheet's 48 rotation frames start at frame 0 = due east and
    advance 7.5 degrees per frame; this locks in that calibration (verified
    against the sheet's own pixel bounding boxes) so a future edit can't
    silently point the van the wrong way."""
    assert _frame_for_direction(1, 0) == 0    # east
    assert _frame_for_direction(1, 1) == 6    # southeast
    assert _frame_for_direction(0, 1) == 12   # south (screen y grows downward)
    assert _frame_for_direction(-1, 1) == 18  # southwest
    assert _frame_for_direction(-1, 0) == 24  # west
    assert _frame_for_direction(-1, -1) == 30 # northwest
    assert _frame_for_direction(0, -1) == 36  # north
    assert _frame_for_direction(1, -1) == 42  # northeast
    assert _frame_for_direction(0, 0) is None  # not moving: caller holds its current frame

def test_shop_hitbox_orientation_matches_travel_axis():
    horizontal = Shop(orientation="horizontal")
    vertical = Shop(orientation="vertical")
    assert _half_extents(horizontal) == (SHOP_HITBOX_LONG / 2, SHOP_HITBOX_SHORT / 2)
    assert _half_extents(vertical) == (SHOP_HITBOX_SHORT / 2, SHOP_HITBOX_LONG / 2)

def _open_map(width=20, height=20, tile_size=16):
    """A tile grid with no walls at all -- wide enough that the van's 80px
    (5-tile) hitbox has clearance from the edges wherever it's placed near
    the middle, unlike the 10x10 _wall_with_gap_map used for zombie/player
    tests (whose small radius never hits that edge case)."""
    return TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                     layers={"Collisions": [0] * (width * height)}, tilesets=[])

def test_shop_parks_then_drives_after_its_duration(monkeypatch):
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(shop_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(10 * 16 + 8, 10 * 16 + 8), park_timer=SHOP_PARK_DURATION)
    player = Player(active=True, pos=Vec2(-9999, -9999))
    frames_parked = 0
    for _ in range(int(SHOP_PARK_DURATION * 60) + 5):
        update_shop(shop, 1 / 60, [], player)
        if shop.state == "parked":
            frames_parked += 1
        else:
            break
    else:
        raise AssertionError("shop van never started driving")
    # It should have stayed parked for essentially the full duration (allow
    # a couple of frames' slack for dt/60 floating-point accumulation).
    assert abs(frames_parked - int(SHOP_PARK_DURATION * 60)) <= 2
    assert shop.state == "driving"
    # Its new destination must be a real, walkable tile.
    col, row = int(shop.dest.x // tm.tile_width), int(shop.dest.y // tm.tile_height)
    assert not tilemap_module.is_solid_tile(tm, col, row)

def test_shop_destination_always_has_room_for_the_vans_full_hitbox():
    """A single clear tile's 3x3 neighborhood is nowhere near enough room for
    the van's actual (up to 5-tile) footprint -- picking a destination on
    that check alone could land it in a pocket it could never actually fit
    into. Build a map with exactly one such trap (a 3x3 clearing boxed in by
    walls) plus one genuinely spacious area -- both at or past
    SHOP_MIN_DEST_COL, since the van is confined to that column and further
    right -- and confirm _pick_destination always lands in the spacious one,
    never the trap, and never left of that confinement column."""
    width, height = 70, 20
    tile_size = 16
    data = [1] * (width * height)  # solid everywhere by default
    def clear(c0, c1, r0, r1):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                data[r * width + c] = 0
    clear(44, 46, 4, 6)    # a 3x3 trap room -- enough for the old check, not the van
    clear(50, 58, 10, 18)  # a genuinely spacious area
    tm = TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                  layers={"Collisions": data}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()

    current = Vec2(45 * tile_size + 8, 5 * tile_size + 8)  # inside the trap room
    for _ in range(100):
        dest = shop_module._pick_destination(tm, current)
        assert shop_module._has_room_for_hitbox(tm, dest.x, dest.y)
        col, row = int(dest.x // tile_size), int(dest.y // tile_size)
        assert not (44 <= col <= 46 and 4 <= row <= 6)  # never the trap room
        assert col >= shop_module.SHOP_MIN_DEST_COL  # never left of the confinement column

def test_shop_kills_any_zombie_it_drives_over():
    shop = Shop(pos=Vec2(500, 500), dest=Vec2(500, 500), state="driving", orientation="horizontal")
    zombie = Zombie(active=True, pos=Vec2(505, 505), hp=999)  # well inside the 80x48 hitbox
    far_zombie = Zombie(active=True, pos=Vec2(700, 500), hp=5)  # outside it
    player = Player(active=True, pos=Vec2(-9999, -9999))

    update_shop(shop, 1 / 60, [zombie, far_zombie], player)

    assert zombie.hp <= 0
    assert far_zombie.hp == 5

def test_shop_hits_player_only_when_not_invulnerable():
    vulnerable = Player(active=True, pos=Vec2(500, 505), invulnerable=0)
    invulnerable = Player(active=True, pos=Vec2(500, 505), invulnerable=0.5)

    hit_vulnerable = update_shop(
        Shop(pos=Vec2(500, 500), dest=Vec2(500, 500), state="driving", orientation="vertical"),
        1 / 60, [], vulnerable,
    )
    hit_invulnerable = update_shop(
        Shop(pos=Vec2(500, 500), dest=Vec2(500, 500), state="driving", orientation="vertical"),
        1 / 60, [], invulnerable,
    )

    assert hit_vulnerable is True
    assert hit_invulnerable is False

def test_shop_arrives_and_reparks_with_a_fresh_timer(monkeypatch):
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    shop_module._flow_field_cache.update(tiled_map_id=None, dest=None, field=None)
    monkeypatch.setattr(shop_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(5 * 16 + 8, 10 * 16 + 8), dest=Vec2(14 * 16 + 8, 10 * 16 + 8), state="driving")
    player = Player(active=True, pos=Vec2(-9999, -9999))
    for _ in range(2000):
        update_shop(shop, 1 / 60, [], player)
        if shop.state == "parked":
            break
    else:
        raise AssertionError("shop van never arrived at its destination")
    assert shop.park_timer == SHOP_PARK_DURATION

def test_shop_obstacle_is_none_while_driving_and_a_rect_while_parked():
    driving = Shop(pos=Vec2(500, 500), state="driving", orientation="horizontal")
    parked = Shop(pos=Vec2(500, 500), state="parked", orientation="vertical")
    assert shop_obstacle(driving) is None
    assert shop_obstacle(parked) == (500, 500, SHOP_HITBOX_SHORT / 2, SHOP_HITBOX_LONG / 2)

def test_player_can_open_the_shop_only_after_walking_into_its_collision_edge():
    """The parked van blocks the player like a wall (test_parked_van_blocks_
    the_player_like_a_wall), so they can never reach its center -- "E to
    shop" has to trigger once they're pressed against its edge, not within
    some fixed radius of its middle (the old check, which the van's own
    collision made unreachable and was this bug)."""
    shop = Shop(pos=Vec2(500, 500), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    player = Player(active=True, pos=Vec2(400, 500))
    assert not shop_touching(shop, player.pos.x, player.pos.y, player.radius)
    for _ in range(300):
        move_player(player, 1, 0, 1 / 60, 70, obstacle=obstacle)
    assert shop_touching(shop, player.pos.x, player.pos.y, player.radius)

def test_shop_touching_ignores_a_driving_van():
    driving = Shop(pos=Vec2(500, 500), state="driving", orientation="horizontal")
    # Right where the van's center is -- as close as physically possible.
    assert not shop_touching(driving, 500, 500, 6)

def test_parked_van_blocks_the_player_like_a_wall():
    """A stationary van is a solid obstacle (this task); a driving one isn't
    -- it deals damage instead (see test_shop_hits_player_only_when_not_invulnerable)."""
    shop = Shop(pos=Vec2(500, 500), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    player = Player(active=True, pos=Vec2(450, 500))
    for _ in range(300):
        move_player(player, 1, 0, 1 / 60, 70, obstacle=obstacle)
    # Stops at the van's left edge (500 - 40 half-width), short of its own radius.
    assert player.pos.x + player.radius <= 500 - SHOP_HITBOX_LONG / 2 + 0.01

def test_parked_van_blocks_zombies_too():
    shop = Shop(pos=Vec2(500, 500), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    zombie = Zombie(active=True, pos=Vec2(450, 500))
    lure = Player(active=True, pos=Vec2(700, 500))  # pulls the zombie east, into the van
    for _ in range(600):
        move_zombies([zombie], lure, 1 / 60, 18, obstacle=obstacle)
    assert zombie.pos.x + zombie.radius <= 500 - SHOP_HITBOX_LONG / 2 + 0.01

def test_driving_van_does_not_block_movement():
    shop = Shop(pos=Vec2(500, 500), state="driving", orientation="horizontal")
    obstacle = shop_obstacle(shop)
    player = Player(active=True, pos=Vec2(450, 500))
    for _ in range(300):
        move_player(player, 1, 0, 1 / 60, 70, obstacle=obstacle)
    assert player.pos.x > 500  # drove straight through, undeflected

def test_van_steering_keeps_its_heading_through_a_symmetric_tie():
    """Faced with two equally-short ways around an obstacle (go north or go
    south around a pillar dead ahead), the van keeps whichever direction it
    was already heading instead of picking one arbitrarily -- this is what
    "prioritizes the minimum number of turns" means: never a longer route to
    avoid a turn, but never an unforced turn between equally-good options
    either."""
    width, height, tile_size = 20, 20, 16
    data = [0] * (width * height)
    data[10 * width + 10] = 1  # a lone pillar directly between start and destination
    tm = TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                  layers={"Collisions": data}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    dest_col, dest_row = 15, 10
    field = compute_distance_field(tm, dest_col, dest_row)
    dest_x, dest_y = (dest_col + .5) * tile_size, (dest_row + .5) * tile_size
    x, y = (9 + .5) * tile_size, (10 + .5) * tile_size  # right up against the pillar's west face

    _, dy_north, heading_north = _steer_minimizing_turns(tm, field, x, y, dest_x, dest_y, (0, -1))
    _, dy_south, heading_south = _steer_minimizing_turns(tm, field, x, y, dest_x, dest_y, (0, 1))

    assert heading_north == (0, -1) and dy_north < 0  # kept heading north
    assert heading_south == (0, 1) and dy_south > 0   # kept heading south

def test_van_never_drives_diagonally(monkeypatch):
    """A full diagonal trip (destination offset in both x and y) must still
    only ever move the van along one axis at a time -- it turns at
    intersections instead of cutting the corner."""
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    shop_module._flow_field_cache.update(tiled_map_id=None, dest=None, field=None)
    monkeypatch.setattr(shop_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(3 * 16 + 8, 3 * 16 + 8), dest=Vec2(16 * 16 + 8, 16 * 16 + 8), state="driving")
    player = Player(active=True, pos=Vec2(-9999, -9999))
    moved_x = moved_y = False
    for _ in range(3000):
        before_x, before_y = shop.pos.x, shop.pos.y
        update_shop(shop, 1 / 60, [], player)
        step_x, step_y = shop.pos.x - before_x, shop.pos.y - before_y
        assert step_x == 0 or step_y == 0, f"diagonal step: ({step_x}, {step_y})"
        moved_x = moved_x or step_x != 0
        moved_y = moved_y or step_y != 0
        if shop.state == "parked":
            break
    else:
        raise AssertionError("shop van never arrived at its diagonal destination")
    # A route that's purely axis-aligned start to finish should still have
    # used both axes at some point, given the destination is diagonal from
    # the start -- otherwise this test wouldn't be exercising anything.
    assert moved_x and moved_y

def test_van_sweeps_through_several_frames_when_it_turns(monkeypatch):
    """Turning a corner should smoothly sweep the frame from the old cardinal
    heading to the new one across several distinct intermediate frames --
    not jump straight there, and not freeze on a single diagonal pose (which
    looked like the van spinning in place) -- then settle into a real
    cardinal frame once the sweep finishes."""
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    shop_module._flow_field_cache.update(tiled_map_id=None, dest=None, field=None)
    monkeypatch.setattr(shop_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(3 * 16 + 8, 3 * 16 + 8), dest=Vec2(16 * 16 + 8, 16 * 16 + 8), state="driving")
    player = Player(active=True, pos=Vec2(-9999, -9999))
    turn_seen = False
    frames_during_sweep = []
    for _ in range(3000):
        old_heading = shop.heading
        update_shop(shop, 1 / 60, [], player)
        if shop.heading != old_heading and not turn_seen:
            turn_seen = True
            # A 90-degree turn between two cardinal directions spans exactly
            # 12 sheet-frames (see SHOP_VAN_DEGREES_PER_FRAME).
            assert abs(shop.pivot_span) == 12
            assert shop.pivot_duration == SHOP_PIVOT_DURATION
            # The timer already ticked down by one dt within this same call.
            assert 0 < shop.pivot_timer <= SHOP_PIVOT_DURATION
        if turn_seen:
            frames_during_sweep.append(shop.frame)
            if shop.pivot_timer <= 0:
                break
    assert turn_seen, "route never turned a corner to sweep through"
    # More than just a single held pose: several distinct frames were shown
    # as the sweep progressed, not one diagonal frame frozen for its duration.
    assert len(set(frames_during_sweep)) >= 5
    assert shop.pivot_timer == 0
    assert shop.frame in (0, 12, 24, 36)

def test_van_backs_up_instead_of_freezing_at_a_too_narrow_gap(monkeypatch):
    """The van's pathfinding treats it as a single point, so a gap it thinks
    is open can still be too narrow for its actual (multi-tile) hitbox --
    without recovery, it would just sit jammed against it forever. This
    checks it doesn't: after enough time stuck, it backs away."""
    width, height, tile_size = 20, 20, 16
    wall_row, gap_col = 10, 10
    data = [0] * (width * height)
    for col in range(width):
        if col != gap_col:
            data[wall_row * width + col] = 1
    tm = TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                  layers={"Collisions": data}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    shop_module._flow_field_cache.update(tiled_map_id=None, dest=None, field=None)
    monkeypatch.setattr(shop_module, "get_world_map", lambda: tm)

    shop = Shop(
        pos=Vec2((gap_col + .5) * tile_size, 5 * tile_size + 8),
        dest=Vec2((gap_col + .5) * tile_size, 15 * tile_size + 8),
        state="driving", heading=(0, 1),
    )
    player = Player(active=True, pos=Vec2(-9999, -9999))
    positions = []
    for _ in range(int((SHOP_STUCK_THRESHOLD + 0.5) * 60) + 30):
        update_shop(shop, 1 / 60, [], player)
        positions.append((shop.pos.x, shop.pos.y))
    # It must have pressed up against the gap (made progress early on)...
    assert positions[10] != positions[0]
    # ...but not sat completely frozen at the same spot for the whole window:
    # once stuck long enough it should have backed away, changing position
    # again after appearing to settle.
    settled_pos = positions[int(SHOP_STUCK_THRESHOLD * 60)]
    assert positions[-1] != settled_pos
    assert shop.backup_timer > 0 or shop.stuck_timer == 0  # currently backing up, or already recovered

def test_van_backup_never_triggers_during_unobstructed_driving():
    """Zero false positives: a normal trip with nothing in the way must never
    make the van think it's stuck and start backing up."""
    # (768,88) -> (900,88) is a straight run through open ground -- unlike
    # (400,600), which turned out to already be inside solid map geometry
    # (a wall block spanning roughly tile columns 20-30, rows 34-41), so the
    # van could never move in any direction and failed this test for reasons
    # having nothing to do with "unobstructed".
    shop = Shop(pos=Vec2(768, 88), dest=Vec2(900, 88), state="driving")
    player = Player(active=True, pos=Vec2(-9999, -9999))
    for _ in range(600):
        update_shop(shop, 1 / 60, [], player)
        assert shop.backup_timer == 0
        assert shop.stuck_timer < SHOP_STUCK_THRESHOLD
        if shop.state == "parked":
            break
    else:
        raise AssertionError("shop van never arrived on an unobstructed route")

def test_van_gives_up_and_repicks_after_too_much_cumulative_backing_up(monkeypatch):
    """Backing up can't discover a genuinely wider route by itself -- the
    field has no idea the van is wide, so if the *shortest* path to a
    destination is a gap too narrow for it everywhere nearby, the van would
    back up and re-approach that same gap forever. Once cumulative backing-up
    time on one trip passes SHOP_GIVE_UP_THRESHOLD, it must abandon that
    destination for a new one instead of looping indefinitely."""
    width, height, tile_size = 20, 20, 16
    wall_row, gap_col = 10, 10
    data = [0] * (width * height)
    for col in range(width):
        if col != gap_col:
            data[wall_row * width + col] = 1
    tm = TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                  layers={"Collisions": data}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    shop_module._flow_field_cache.update(tiled_map_id=None, dest=None, field=None)
    monkeypatch.setattr(shop_module, "get_world_map", lambda: tm)

    original_dest = Vec2((gap_col + .5) * tile_size, 15 * tile_size + 8)
    shop = Shop(
        pos=Vec2((gap_col + .5) * tile_size, 5 * tile_size + 8),
        dest=Vec2(original_dest.x, original_dest.y),
        state="driving", heading=(0, 1),
    )
    player = Player(active=True, pos=Vec2(-9999, -9999))
    # Cumulative *backing-up* time needs to reach SHOP_GIVE_UP_THRESHOLD, but
    # wall-clock time between backups also includes SHOP_STUCK_THRESHOLD's
    # wait and the travel back to the gap each cycle, so the real time needed
    # is well over the threshold itself -- generous upper bound here.
    max_frames = int(SHOP_GIVE_UP_THRESHOLD * 10 * 60)
    for _ in range(max_frames):
        update_shop(shop, 1 / 60, [], player)
        if shop.dest.x != original_dest.x or shop.dest.y != original_dest.y:
            break
    else:
        raise AssertionError("van never gave up on the unreachable-for-its-size destination")
    # Giving up resets the cumulative counter so the fresh destination gets
    # its own full budget of backing-up attempts.
    assert shop.trouble_time == 0.0

def test_zombie_sheets_have_matching_hurt_and_death_variants_for_both_types():
    import os
    from render.assets import ZOMBIE_SHEETS
    for enemy_type in ("walker", "runner"):
        variants = ZOMBIE_SHEETS[enemy_type]
        assert set(variants) == {"walk", "hurt", "death"}
        assert variants["walk"]["frames"] == 8
        for variant in ("hurt", "death"):
            meta = variants[variant]
            assert meta["frames"] == 4
            assert meta["frame_width"] == meta["frame_height"] == 100
            assert os.path.isfile(meta["path"])

def test_super_zombie_stats_and_scale_are_the_right_multiples_of_the_base_types():
    for base_type, super_type in ZOMBIE_MERGE_TARGET.items():
        base, super_ = ENEMY_TYPES[base_type], ENEMY_TYPES[super_type]
        assert super_.hp == base.hp * 3
        assert super_.speed == base.speed * 2
        assert super_.contact_damage == base.contact_damage * 2  # melee only -- see ZOMBIE_BASE_TYPE for bullet damage
        assert super_.radius == base.radius * 2

def test_spawn_zombie_never_creates_a_super_variant_directly():
    pool = Pool(Zombie, 50)
    for _ in range(50):
        z = spawn_zombie(pool, wave=1)
        assert z.enemy_type in ("walker", "runner")
        assert z.radius == ENEMY_TYPES[z.enemy_type].radius

def _zombie_grid(zombies):
    """A SpatialHash populated with zombies, matching what main.py builds
    each frame -- merge_touching_zombies uses it to only check nearby
    zombies as merge candidates instead of the whole population (see its
    own docstring for why that matters)."""
    grid = SpatialHash(32)
    for z in zombies:
        grid.insert(z)
    return grid

def test_three_mutually_touching_walkers_merge_into_a_super_walker():
    """A fully-connected trio (each pair touching, not just a chain) of the
    same base type fuses into one bigger "_super" zombie centered on them,
    and the three originals are gone -- not just marked dying."""
    pool = Pool(Zombie, 10)
    a = pool.acquire(); a.pos.x, a.pos.y, a.enemy_type, a.radius = 500, 500, "walker", 5
    b = pool.acquire(); b.pos.x, b.pos.y, b.enemy_type, b.radius = 506, 500, "walker", 5
    c = pool.acquire(); c.pos.x, c.pos.y, c.enemy_type, c.radius = 503, 505, "walker", 5
    zombies = [a, b, c]

    merge_touching_zombies(zombies, pool, _zombie_grid(zombies))

    # The pool reuses freed slots, so the merged zombie may well *be* one of
    # a/b/c's underlying objects now repurposed -- what matters is that only
    # one zombie survives in the pool at all, as the merged super type.
    survivors = list(pool.active())
    assert len(survivors) == 1
    merged = survivors[0]
    assert merged.enemy_type == "walker_super"
    assert merged.hp == ENEMY_TYPES["walker_super"].hp
    assert merged.radius == ENEMY_TYPES["walker_super"].radius
    assert merged.pos.x == (500 + 506 + 503) / 3
    assert merged.pos.y == (500 + 500 + 505) / 3

def test_a_touching_chain_that_isnt_a_mutual_trio_does_not_merge():
    """Three zombies in a line -- A touches B, B touches C, but A and C are
    too far apart to touch each other -- is a chain, not a fully-connected
    trio, and must not merge."""
    pool = Pool(Zombie, 10)
    a = pool.acquire(); a.pos.x, a.pos.y, a.enemy_type, a.radius = 500, 500, "walker", 5
    b = pool.acquire(); b.pos.x, b.pos.y, b.enemy_type, b.radius = 510, 500, "walker", 5
    c = pool.acquire(); c.pos.x, c.pos.y, c.enemy_type, c.radius = 520, 500, "walker", 5
    zombies = [a, b, c]

    merge_touching_zombies(zombies, pool, _zombie_grid(zombies))

    assert a.active and b.active and c.active
    assert {z.enemy_type for z in pool.active()} == {"walker"}

def test_two_touching_zombies_do_not_merge():
    """Merging needs three, not two -- a pair just touching stays as-is."""
    pool = Pool(Zombie, 10)
    a = pool.acquire(); a.pos.x, a.pos.y, a.enemy_type, a.radius = 500, 500, "walker", 5
    b = pool.acquire(); b.pos.x, b.pos.y, b.enemy_type, b.radius = 506, 500, "walker", 5
    zombies = [a, b]

    merge_touching_zombies(zombies, pool, _zombie_grid(zombies))

    assert a.active and b.active

def test_merging_requires_the_same_base_type():
    """Two walkers and a runner all mutually touching isn't a same-type
    trio, so nothing merges even though every pair is in contact."""
    pool = Pool(Zombie, 10)
    a = pool.acquire(); a.pos.x, a.pos.y, a.enemy_type, a.radius = 500, 500, "walker", 5
    b = pool.acquire(); b.pos.x, b.pos.y, b.enemy_type, b.radius = 506, 500, "walker", 5
    c = pool.acquire(); c.pos.x, c.pos.y, c.enemy_type, c.radius = 503, 505, "runner", 5
    zombies = [a, b, c]

    merge_touching_zombies(zombies, pool, _zombie_grid(zombies))

    assert a.active and b.active and c.active

def test_super_zombies_do_not_merge_further():
    """The two new types don't chain-evolve into something bigger still --
    three mutually touching "_super" zombies just stay as they are."""
    pool = Pool(Zombie, 10)
    zombies = [spawn_super_zombie(pool, "walker_super", 500 + i * 6, 500) for i in range(3)]

    merge_touching_zombies(zombies, pool, _zombie_grid(zombies))

    assert all(z.active for z in zombies)
    assert {z.enemy_type for z in pool.active()} == {"walker_super"}

def test_merge_touching_zombies_stays_cheap_with_a_full_scattered_population():
    """Regression guard: an earlier version of this checked every same-type
    pair (and often triple) brute-force, which cost several ms/frame with a
    full zombie population -- enough to visibly stutter the game (dropped
    frames make effects with a fixed cast-time position, like the lightning
    chain or orb strikes, look like they're lagging behind the player). This
    uses the spatial hash to only check zombies actually near each other, so
    a full, mostly-scattered population (matching how zombies really spawn,
    at map edges, and converge over time) should take a fraction of a
    millisecond, not multiple milliseconds."""
    import random, time
    rng = random.Random(0)
    pool = Pool(Zombie, MAX_ZOMBIES)
    zombies = []
    for i in range(MAX_ZOMBIES):
        z = pool.acquire()
        z.enemy_type = "walker" if rng.random() < .75 else "runner"
        z.radius = 5
        if i < 30:  # a real cluster right on the player
            z.pos.x = 500 + rng.uniform(-40, 40)
            z.pos.y = 500 + rng.uniform(-40, 40)
        else:  # the rest, scattered across the whole world, still converging
            z.pos.x = rng.uniform(0, WORLD_WIDTH)
            z.pos.y = rng.uniform(0, WORLD_HEIGHT)
        zombies.append(z)
    grid = _zombie_grid(zombies)

    start = time.perf_counter()
    for _ in range(10):
        merge_touching_zombies(zombies, pool, grid)
    elapsed_per_call = (time.perf_counter() - start) / 10

    assert elapsed_per_call < 0.005  # generously under a 60fps frame budget (16.7ms)

def test_max_zombie_radius_matches_the_biggest_enemy_type():
    from game.data import MAX_ZOMBIE_RADIUS
    assert MAX_ZOMBIE_RADIUS == 10
    assert MAX_ZOMBIE_RADIUS == max(t.radius for t in ENEMY_TYPES.values())

def test_hail_burst_reaches_a_super_zombie_sitting_at_its_outer_edge():
    """damage_at_point's broad-phase spatial-hash query has to reach past
    the blast radius by the target's own radius, or a zombie sitting well
    within the true hit range (blast radius + its radius) but outside the
    query's raw radius can be excluded before the precise per-zombie check
    even runs. A fine-grained hash (cell_size=5, versus the game's actual
    32) makes that cell-boundary gap deterministic to test: with the old,
    un-padded query (radius=5) the "_super" zombie's cell falls outside the
    scanned range even though it's well within the true 5+10=15 hit range;
    padding the query by MAX_ZOMBIE_RADIUS fixes that."""
    pool = Pool(Zombie, 1)
    super_zombie = spawn_super_zombie(pool, "walker_super", 12, 0)
    grid = SpatialHash(5)
    grid.insert(super_zombie)

    hit = damage_at_point([super_zombie], grid, 0, 0, 5, damage=1)

    assert hit
    assert super_zombie.hp == ENEMY_TYPES["walker_super"].hp - 1

def test_bullets_reach_a_super_zombies_outer_rim():
    """update_bullets' broad-phase query has the same class of gap as
    damage_at_point's (see test_hail_burst_reaches_a_super_zombie_sitting_at_its_outer_edge)
    -- it has to reach past the bullet's own radius by the target's radius
    too, or a bullet well within true hit range of a "_super" zombie's rim
    can still miss it because the query itself never returns it as a
    candidate."""
    pool = Pool(Bullet, 1)
    bullet = pool.acquire()
    bullet.pos.x, bullet.pos.y = 0, 0
    bullet.vx, bullet.vy = 0, 0  # stationary: isolates the query/hit check from travel
    bullet.ttl, bullet.radius, bullet.damage = 1.5, 2, 5

    zpool = Pool(Zombie, 1)
    super_zombie = spawn_super_zombie(zpool, "walker_super", 10.5, 0)
    grid = SpatialHash(5)
    grid.insert(super_zombie)

    hits = update_bullets(pool, [super_zombie], 1 / 60, 2000, 2000, grid)

    assert hits == [super_zombie]
    assert not bullet.active
    assert super_zombie.hp == ENEMY_TYPES["walker_super"].hp - 5

def test_super_zombie_stops_pursuing_within_6_tiles(monkeypatch):
    """"_super" zombies hold position once close enough to shoot instead of
    closing the last few tiles into melee (see RANGED_ZOMBIE_STOP_TILES /
    fire_zombie_bullets)."""
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    movement_module._flow_field_cache.update(tiled_map_id=None, target=None, obstacle=None, field=None)
    monkeypatch.setattr(movement_module, "get_world_map", lambda: tm)

    pool = Pool(Zombie, 1)
    zombie = spawn_super_zombie(pool, "walker_super", 3 * 16 + 8, 3 * 16 + 8)
    player = Player(active=True, pos=Vec2(8 * 16 + 8, 3 * 16 + 8))  # 5 tiles away, inside the 6-tile stop range

    before_x, before_y = zombie.pos.x, zombie.pos.y
    move_zombies([zombie], player, 1 / 60, 40)

    assert (zombie.pos.x, zombie.pos.y) == (before_x, before_y)

def test_super_zombie_still_pursues_beyond_6_tiles(monkeypatch):
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    movement_module._flow_field_cache.update(tiled_map_id=None, target=None, obstacle=None, field=None)
    monkeypatch.setattr(movement_module, "get_world_map", lambda: tm)

    pool = Pool(Zombie, 1)
    zombie = spawn_super_zombie(pool, "walker_super", 3 * 16 + 8, 3 * 16 + 8)
    player = Player(active=True, pos=Vec2(16 * 16 + 8, 3 * 16 + 8))  # well past the 6-tile stop range

    before_x = zombie.pos.x
    move_zombies([zombie], player, 1 / 60, 40)

    assert zombie.pos.x > before_x

def test_base_zombies_ignore_the_stop_range_and_keep_chasing(monkeypatch):
    """Only "_super" zombies hold at range -- base zombies are melee-only
    and always keep closing the distance, even well inside 6 tiles."""
    tm = _open_map()
    tilemap_module._solid_tiles_cache.clear()
    movement_module._flow_field_cache.update(tiled_map_id=None, target=None, obstacle=None, field=None)
    monkeypatch.setattr(movement_module, "get_world_map", lambda: tm)

    zombie = Zombie(active=True, enemy_type="walker", pos=Vec2(3 * 16 + 8, 3 * 16 + 8))
    player = Player(active=True, pos=Vec2(8 * 16 + 8, 3 * 16 + 8))  # 5 tiles away

    before_x = zombie.pos.x
    move_zombies([zombie], player, 1 / 60, 40)

    assert zombie.pos.x > before_x

def test_super_zombie_fires_at_the_player_in_range_with_los(monkeypatch):
    """"_super" zombies shoot at the player by the same rules the player's
    own auto-fire uses (see nearest_target): in range, clear line of sight,
    on a cooldown -- see fire_zombie_bullets."""
    tm = TiledMap(width=10, height=10, tile_width=16, tile_height=16,
                  layers={"Collisions": [0] * 100}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    pool = Pool(Zombie, 1)
    shooter = spawn_super_zombie(pool, "walker_super", 0, 0)
    player = Player(active=True, pos=Vec2(50, 0))
    bullets = Pool(Bullet, 4)

    fire_zombie_bullets(bullets, [shooter], player, 1 / 60)

    fired = list(bullets.active())
    assert len(fired) == 1
    b = fired[0]
    # Bullet damage is the base type's own (unmultiplied) contact_damage,
    # not the super's 2x melee contact_damage -- the melee buff doesn't
    # carry over to the ranged attack.
    assert b.damage == ENEMY_TYPES["walker"].contact_damage
    assert b.vx > 0 and b.vy == 0  # aimed straight at the player, due east
    assert round((b.vx ** 2 + b.vy ** 2) ** 0.5) == round(ZOMBIE_BULLET_SPEED)
    assert shooter.fire_timer == ZOMBIE_FIRE_RATE

def test_base_zombies_never_fire():
    """Only "_super" zombies shoot -- base zombies stay melee-only even
    with a clear, in-range shot at the player."""
    pool = Pool(Zombie, 1)
    walker = pool.acquire()
    walker.enemy_type = "walker"
    walker.pos.x, walker.pos.y = 0, 0
    player = Player(active=True, pos=Vec2(50, 0))
    bullets = Pool(Bullet, 4)

    fire_zombie_bullets(bullets, [walker], player, 1 / 60)

    assert not list(bullets.active())

def test_super_zombie_respects_its_own_cooldown(monkeypatch):
    tm = TiledMap(width=10, height=10, tile_width=16, tile_height=16,
                  layers={"Collisions": [0] * 100}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    pool = Pool(Zombie, 1)
    shooter = spawn_super_zombie(pool, "walker_super", 0, 0)
    shooter.fire_timer = 1.0
    player = Player(active=True, pos=Vec2(50, 0))
    bullets = Pool(Bullet, 4)

    fire_zombie_bullets(bullets, [shooter], player, 1 / 60)

    assert not list(bullets.active())
    assert shooter.fire_timer < 1.0  # still ticks down even while on cooldown

def test_super_zombie_does_not_fire_beyond_range(monkeypatch):
    tm = TiledMap(width=400, height=400, tile_width=16, tile_height=16,
                  layers={"Collisions": [0] * (400 * 400)}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    pool = Pool(Zombie, 1)
    shooter = spawn_super_zombie(pool, "walker_super", 0, 0)
    player = Player(active=True, pos=Vec2(ZOMBIE_BULLET_RANGE + 50, 0))
    bullets = Pool(Bullet, 4)

    fire_zombie_bullets(bullets, [shooter], player, 1 / 60)

    assert not list(bullets.active())

def test_super_zombie_does_not_fire_through_a_wall(monkeypatch):
    """Mirrors test_nearest_target_ignores_enemies_behind_walls, from the
    zombie's side of the same has_line_of_sight check."""
    width, height, tile_size = 10, 10, 16
    wall_col = 3
    data = [0] * (width * height)
    for row in range(height):
        data[row * width + wall_col] = 1
    tm = TiledMap(width=width, height=height, tile_width=tile_size, tile_height=tile_size,
                  layers={"Collisions": data}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    pool = Pool(Zombie, 1)
    shooter = spawn_super_zombie(pool, "walker_super", 1 * tile_size + 8, 5 * tile_size + 8)
    player = Player(active=True, pos=Vec2(5 * tile_size + 8, 5 * tile_size + 8))
    bullets = Pool(Bullet, 4)

    fire_zombie_bullets(bullets, [shooter], player, 1 / 60)

    assert not list(bullets.active())

def test_super_zombie_does_not_fire_through_the_van(monkeypatch):
    """Mirrors test_nearest_target_ignores_enemies_behind_the_van -- the van
    blocks a zombie's shot at the player exactly like it blocks the
    player's own auto-aim."""
    tm = TiledMap(width=10, height=10, tile_width=16, tile_height=16,
                  layers={"Collisions": [0] * 100}, tilesets=[])
    tilemap_module._solid_tiles_cache.clear()
    monkeypatch.setattr(combat_module, "get_world_map", lambda: tm)

    shop = Shop(pos=Vec2(5 * 16 + 8, 5 * 16 + 8), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)

    pool = Pool(Zombie, 1)
    shooter = spawn_super_zombie(pool, "walker_super", 1 * 16 + 8, 5 * 16 + 8)
    player = Player(active=True, pos=Vec2(9 * 16 + 8, 5 * 16 + 8))
    bullets = Pool(Bullet, 4)

    fire_zombie_bullets(bullets, [shooter], player, 1 / 60, obstacle=obstacle)

    assert not list(bullets.active())

def test_update_enemy_bullets_damages_the_player():
    pool = Pool(Bullet, 1)
    bullet = pool.acquire()
    bullet.pos.x, bullet.pos.y = 0, 0
    bullet.vx, bullet.vy = 0, 0
    bullet.ttl, bullet.radius, bullet.damage = 1.5, 2, 7

    player = Player(active=True, pos=Vec2(0, 0), invulnerable=0)

    damage = update_enemy_bullets(pool, player, 1 / 60, 2000, 2000)

    assert damage == 7
    assert not bullet.active

def test_update_enemy_bullets_pass_through_an_invulnerable_player():
    """Mirrors the existing shop/zombie contact rule: while invulnerable,
    the player simply can't be hit -- an incoming bullet flies on through
    rather than being consumed harmlessly."""
    pool = Pool(Bullet, 1)
    bullet = pool.acquire()
    bullet.pos.x, bullet.pos.y = 0, 0
    bullet.vx, bullet.vy = 0, 0
    bullet.ttl, bullet.radius, bullet.damage = 1.5, 2, 7

    player = Player(active=True, pos=Vec2(0, 0), invulnerable=0.5)

    damage = update_enemy_bullets(pool, player, 1 / 60, 2000, 2000)

    assert damage == 0
    assert bullet.active

def test_update_enemy_bullets_are_destroyed_by_the_van():
    pool = Pool(Bullet, 1)
    bullet = pool.acquire()
    bullet.pos.x, bullet.pos.y = 400, 500
    bullet.vx, bullet.vy = 200, 0
    bullet.ttl, bullet.radius, bullet.damage = 1.5, 2, 7

    player = Player(active=True, pos=Vec2(-9999, -9999))
    shop = Shop(pos=Vec2(500, 500), state="parked", orientation="horizontal")
    obstacle = shop_obstacle(shop)

    for _ in range(120):
        update_enemy_bullets(pool, player, 1 / 60, 2000, 2000, obstacle=obstacle)
        if not bullet.active:
            break
    else:
        raise AssertionError("enemy bullet was never stopped by the van")
    assert bullet.pos.x < 500

def test_combined_score_scales_with_wave():
    progress = PlayerProgress(score=200, wave=3)
    assert combined_score(progress) == 600

def test_high_score_round_trips_through_save_file(tmp_path):
    path = tmp_path / "save.json"
    assert load_save(path).high_score == 0
    save_high_score(4200, path)
    assert load_save(path).high_score == 4200

def test_load_save_ignores_corrupt_file(tmp_path):
    path = tmp_path / "save.json"
    path.write_text("not json")
    assert load_save(path).high_score == 0
