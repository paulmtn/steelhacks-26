"""Sprite registry and the asset-free fallback palette.

Replace the coordinates below when the team receives a .pyxres file.  Keeping
the names stable means gameplay and rendering code do not need to change.
"""
SPRITES={"player":(0,0,0,8,8,0),"walker":(0,8,0,8,8,0),
         "runner":(0,16,0,8,8,0),"xp":(0,24,0,5,5,0),
         "gold":(0,29,0,5,5,0),"merchant":(0,34,0,8,8,0)}
FALLBACK_COLORS={"player":11,"walker":3,"runner":9,"xp":10,"gold":4,"merchant":12}
ASSETS_LOADED=False
BG=1; TEXT=7; PLAYER=11; ZOMBIE=3; BULLET=10; COIN=9; HEALTH=8; PANEL=0; MERCHANT=12
def load_assets(pyxel, path=None):
    global ASSETS_LOADED
    if path:
        try:
            pyxel.load(path)
            ASSETS_LOADED=True
        except (OSError, ValueError):
            ASSETS_LOADED=False
    return SPRITES
