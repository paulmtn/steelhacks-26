"""Sprite registry and the asset-free fallback palette.

Replace the coordinates below when the team receives a .pyxres file.  Keeping
the names stable means gameplay and rendering code do not need to change.
"""
SPRITES={"player":(0,0,0,8,8,0),"walker":(0,8,0,8,8,0),
         "runner":(0,16,0,8,8,0),"xp":(0,24,0,3,3,0),
         "gold":(0,29,0,3,3,0),"merchant":(0,34,0,8,8,0)}
# Pyxel palette: 10 is yellow and 13 is blue.
FALLBACK_COLORS={"player":11,"walker":3,"runner":9,"xp":13,"gold":10,"merchant":12}
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
