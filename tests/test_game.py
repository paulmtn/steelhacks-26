from game.pools import Pool
from game.entities import Zombie
from game.data import Vec2
from game.spatial_hash import SpatialHash
from game.state import StateMachine, GameMode, PlayerProgress
from game.entities import Player, Pickup
from game.systems.progression import buy, collect_pickups
from game.systems.combat import nearest_target
from game.systems.movement import move_player, move_zombies
from game.tilemap import get_world_map

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

def test_auto_target_ignores_enemies_outside_viewport():
    player = Player(active=True, pos=Vec2(50, 50))
    visible = Zombie(active=True, pos=Vec2(60, 50))
    hidden = Zombie(active=True, pos=Vec2(400, 50))

    assert nearest_target(
        player,
        [visible, hidden],
        viewport=(0, 0, 256, 144),
    ) is visible
