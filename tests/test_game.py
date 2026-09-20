from game.pools import Pool
from game.entities import Zombie
from game.data import ABILITIES, SHOP_ITEMS, Vec2
from game.spatial_hash import SpatialHash
from game.state import StateMachine, GameMode, PlayerProgress
from game.entities import Player, Pickup
from game.systems.progression import buy, collect_pickups, cleanup_dead
from game.pools import EntityPools
from game.systems.combat import nearest_target
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
    player = Player(active=True, pos=Vec2(0, 0), magnet=50)
    pickup = Pickup(active=True, pos=Vec2(10, 0), kind="gold", amount=1)
    progress = PlayerProgress()

    collect_pickups(player, (pickup,), progress, dt=0.1)

    assert pickup.pos.x < 10
    assert pickup.pos.x > 0

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

def test_uncollected_pickups_expire_and_free_pool_slots():
    player = Player(active=True, pos=Vec2(0, 0), magnet=0)
    pickup = Pickup(active=True, pos=Vec2(100, 0), kind="gold", amount=1, ttl=0.1)
    progress = PlayerProgress()

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
    shop = Shop(pos=Vec2(400, 600), dest=Vec2(700, 300), state="driving")
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
