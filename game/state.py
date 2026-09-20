"""Explicit game state machine and player progression."""
from enum import Enum, auto
from dataclasses import dataclass
import random
from game.data import SHOP_ITEMS

class GameMode(Enum):
    START_MENU = auto(); PLAYING = auto(); SHOP = auto(); LEVEL_UP_INTRO = auto(); LEVEL_UP = auto(); UPGRADES = auto(); DYING = auto(); GAME_OVER = auto()

@dataclass
class PlayerProgress:
    score: int = 0; gems: int = 0; coins: int = 0; wave: int = 1; health: float = 100; max_health: float = 100
    high_score: int = 0  # best combined_score() ever reached, loaded from game.save at startup
    xp: float = 0; level: int = 1; xp_to_next: float = 10
    fire_rate: float = 0.35; damage: int = 1; speed_bonus: float = 0
    sharpshooter_count: int = 0
    magnet: float = 48; shots: int = 1; xp_multiplier: float = 1.0; survival_time: float = 0
    move_multiplier: float = 1.0
    extra_lives: int = 0
    death_cause: str = ""  # what killed the player, shown on the GAME_OVER end screen
    orb_active: bool = False
    orb_count: int = 0
    shield_unlocked: bool = False
    shield_ready: bool = False
    shield_hits: int = 0
    shield_max_hits: int = 0
    shield_regen_timer: float = 0.0
    fire_from_heaven_active: bool = False
    fire_from_heaven_count: int = 0
    fire_from_heaven_timer: float = 0.0
    morning_star_active: bool = False
    morning_star_count: int = 0
    morning_star_angle: float = 0.0
    morning_star_hit_timer: float = 0.0
    hail_active: bool = False
    hail_level: int = 0
    hail_timer: float = 0.0
    upgrades: dict = None; ability_choices: list = None; shop_items: dict = None
    shop_purchases: dict = None
    shop_inventory: list = None
    score_ring_radius: float = 0.0  # HUD scoring-rate ring's radius (see render.draw) -- grows score/10 per point scored, decays 1/frame
    def __post_init__(self):
        self.upgrades = {} if self.upgrades is None else self.upgrades
        self.ability_choices = [] if self.ability_choices is None else self.ability_choices
        self.shop_items = (
            {item.name: item.stock for item in SHOP_ITEMS}
            if self.shop_items is None else self.shop_items
        )
        self.shop_purchases = {} if self.shop_purchases is None else self.shop_purchases
        self.shop_inventory = (
            [item.name for item in random.sample(SHOP_ITEMS, 4)]
            if self.shop_inventory is None else self.shop_inventory
        )

class StateMachine:
    def __init__(self):     self.mode = GameMode.PLAYING
    def transition(self, mode): self.mode = mode

def combined_score(progress):
    """The run's actual high-score metric: raw kill score scaled by wave,
    the game's existing difficulty dial (see main.Game.update, which derives
    it from score and uses it to scale zombie speed/spawns). Surviving to a
    later wave makes every point already earned worth more, instead of a
    flat kill-count race rewarding turtling through easy early waves."""
    return int(progress.score * progress.wave)

def high_score_progress(progress):
    """0..1 fraction of the way from 0 to the persisted high score, for the
    HUD's high-score progress ring (see render.draw) -- reaching or beating
    it (or, since a fresh save's high_score starts at 0, simply scoring
    anything at all on a first-ever run) fills the ring to 1.0."""
    current = combined_score(progress)
    if progress.high_score <= 0:
        return 1.0 if current > 0 else 0.0
    return min(1.0, current / progress.high_score)
