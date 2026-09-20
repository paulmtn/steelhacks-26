"""Cross-run persistence for the high score (see game.state.combined_score).

SaveData (game.data) also has coins/upgrades fields for a future meta-
progression save -- only high_score is read or written here.
"""
import json
import os
from dataclasses import asdict

from game.data import SaveData

SAVE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "save.json")

def load_save(path=SAVE_PATH):
    try:
        with open(path) as f:
            raw = json.load(f)
        return SaveData(high_score=int(raw.get("high_score", 0)))
    except (OSError, ValueError, json.JSONDecodeError):
        return SaveData()

def save_high_score(high_score, path=SAVE_PATH):
    with open(path, "w") as f:
        json.dump(asdict(SaveData(high_score=high_score)), f)
