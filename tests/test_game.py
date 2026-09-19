from game.pools import Pool
from game.entities import Zombie
from game.data import Vec2
from game.spatial_hash import SpatialHash
from game.state import StateMachine, GameMode, PlayerProgress
from game.entities import Player, Pickup
from game.systems.progression import buy, collect_pickups, cleanup_dead
from game.pools import EntityPools
from game.systems.combat import nearest_target
from game.systems.combat import fire_beam
from game.systems.progression import apply_ability

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
