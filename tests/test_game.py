from game.pools import Pool
from game.entities import Zombie
from game.data import Vec2
from game.spatial_hash import SpatialHash
from game.state import StateMachine, GameMode, PlayerProgress
from game.entities import Player, Pickup
from game.systems.progression import buy, collect_pickups

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
