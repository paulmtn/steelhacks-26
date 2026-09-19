from game.pools import Pool
from game.entities import Zombie
from game.data import Vec2
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
import game.tilemap as tilemap_module

def test_pool_is_fixed_and_reuses():
    p=Pool(Zombie,1); z=p.acquire(); assert z and p.acquire() is None; p.release(z); assert p.acquire() is z

def test_spatial_hash_candidates():
    h=SpatialHash(10); z=Zombie(active=True,pos=Vec2(11,11)); h.insert(z); assert z in h.query(10,10,2)

def test_state_and_merchant():
    s=StateMachine(); s.transition(GameMode.PLAYING); assert s.mode is GameMode.PLAYING
    p=PlayerProgress(coins=12); assert buy(p,'damage'); assert p.damage==2 and p.coins==0

def test_pickups_are_magnetized_toward_player():
    player = Player(active=True, pos=Vec2(0, 0), magnet=50)
    pickup = Pickup(active=True, pos=Vec2(10, 0), kind="gold", amount=1)
    progress = PlayerProgress()

    collect_pickups(player, (pickup,), progress, dt=0.1)

    assert pickup.pos.x < 10
    assert pickup.pos.x > 0

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

    apply_ability(progress, "Scavenger")
    assert progress.xp_multiplier == 1.2

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
