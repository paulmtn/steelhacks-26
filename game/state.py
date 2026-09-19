"""Explicit game state machine and player progression."""
from enum import Enum, auto
from dataclasses import dataclass

class GameMode(Enum):
    PLAYING = auto(); SHOP = auto(); LEVEL_UP = auto(); UPGRADES = auto(); GAME_OVER = auto()

@dataclass
class PlayerProgress:
    score: int = 0; gems: int = 0; coins: int = 0; wave: int = 1; health: float = 100; max_health: float = 100
    xp: float = 0; level: int = 1; xp_to_next: float = 10
    fire_rate: float = 0.35; damage: int = 1; speed_bonus: float = 0
    magnet: float = 48; shots: int = 1; xp_multiplier: float = 1.0; survival_time: float = 0
    orb_active: bool = False
    orb_count: int = 0
    upgrades: dict = None; ability_choices: list = None; shop_items: list = None
    def __post_init__(self):
        self.upgrades = {} if self.upgrades is None else self.upgrades
        self.ability_choices = [] if self.ability_choices is None else self.ability_choices
        self.shop_items = [] if self.shop_items is None else self.shop_items

class StateMachine:
    def __init__(self):     self.mode = GameMode.PLAYING
    def transition(self, mode): self.mode = mode
