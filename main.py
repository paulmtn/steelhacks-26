"""Night Shift: asset-free Pyxel 2.x survival game."""
import math, time, random, os
try:
    import pyxel
except ImportError:
    pyxel = None
from game.config import *
from game.data import Vec2, SHOP_ITEMS
from game.entities import Player
from game.pools import EntityPools
from game.spatial_hash import SpatialHash
from game.state import GameMode, PlayerProgress, StateMachine
from game.systems.movement import move_player, move_zombies
from game.systems.combat import fire, update_bullets, nearest_target
from game.systems.spawn import spawn_zombie
from game.systems.progression import cleanup_dead, collect_pickups, buy, apply_ability, buy_permanent
from render.draw import draw_world
from render.assets import load_assets

class Game:
    def __init__(self):
        self.state=StateMachine(); self.progress=PlayerProgress()
        self.pools=EntityPools(MAX_ZOMBIES,MAX_BULLETS,MAX_PARTICLES,MAX_PICKUPS)
        self.grid=SpatialHash(); self.player=Player(active=True,pos=Vec2(WORLD_WIDTH/2,WORLD_HEIGHT/2))
        self.merchant=Vec2(WORLD_WIDTH/2,WORLD_HEIGHT/2+55); self.spawn_clock=0; self.fire_clock=0
        self.dev=False; self.demo_mode=False; self.hitboxes=False
        self.camera=Vec2(); self.last=time.perf_counter()
    def restart(self): self.__init__()
    def update(self, dt):
        if self.state.mode == GameMode.GAME_OVER: return
        if self.state.mode == GameMode.SHOP:
            near=self._near_merchant()
            if not near: self.state.transition(GameMode.PLAYING); return
            if pyxel.btnp(pyxel.KEY_E): self.state.transition(GameMode.PLAYING)
            for key,name in ((pyxel.KEY_1,'heal'),(pyxel.KEY_2,'damage'),(pyxel.KEY_3,'speed')):
                if pyxel.btnp(key): buy(self.progress,name)
            return
        if self.state.mode == GameMode.LEVEL_UP:
            for i,key in enumerate((pyxel.KEY_1,pyxel.KEY_2,pyxel.KEY_3)):
                if pyxel.btnp(key) and i < len(self.progress.ability_choices):
                    apply_ability(self.progress,self.progress.ability_choices[i].name); self.state.transition(GameMode.PLAYING)
            return
        if self.state.mode == GameMode.UPGRADES:
            for key,name in ((pyxel.KEY_1,"Damage"),(pyxel.KEY_2,"Vitality"),(pyxel.KEY_3,"Magnet")):
                if pyxel.btnp(key): buy_permanent(self.progress,name)
            if pyxel.btnp(pyxel.KEY_U): self.state.transition(GameMode.PLAYING)
            return
        dx=(pyxel.btn(pyxel.KEY_D) or pyxel.btn(pyxel.KEY_RIGHT))-(pyxel.btn(pyxel.KEY_A) or pyxel.btn(pyxel.KEY_LEFT))
        dy=(pyxel.btn(pyxel.KEY_S) or pyxel.btn(pyxel.KEY_DOWN))-(pyxel.btn(pyxel.KEY_W) or pyxel.btn(pyxel.KEY_UP))
        move_player(self.player,dx,dy,dt,PLAYER_SPEED+self.progress.speed_bonus)
        self.camera.x=max(0,min(WORLD_WIDTH-WIDTH,self.player.pos.x-WIDTH/2))
        self.camera.y=max(0,min(WORLD_HEIGHT-HEIGHT,self.player.pos.y-HEIGHT/2))
        self.progress.survival_time += dt; self.player.invulnerable=max(0,self.player.invulnerable-dt)
        self.spawn_clock-=dt; self.fire_clock-=dt
        if self.spawn_clock<=0:
            spawn_zombie(self.pools.zombies,self.progress.wave)
            self.spawn_clock=max(.12,SPAWN_INTERVAL/(1+self.progress.survival_time/90))
        zombies=list(self.pools.zombies.active()); self.grid.clear()
        for z in zombies: self.grid.insert(z)
        move_zombies(zombies,self.player,dt,ZOMBIE_SPEED+self.progress.wave*.5)
        for z in self.grid.query(self.player.pos.x,self.player.pos.y,24):
            if self.player.invulnerable<=0 and (z.pos.x-self.player.pos.x)**2+(z.pos.y-self.player.pos.y)**2 < 100:
                self.progress.health-=ZOMBIE_DAMAGE; self.player.invulnerable=CONTACT_INVULN
        target=nearest_target(
            self.player,
            zombies,
            self.grid,
            viewport=(self.camera.x, self.camera.y, WIDTH, HEIGHT),
        )
        if target and self.fire_clock<=0:
            dx,dy=target.pos.x-self.player.pos.x,target.pos.y-self.player.pos.y; d=math.hypot(dx,dy) or 1
            for shot in range(self.progress.shots):
                spread=(shot-(self.progress.shots-1)/2)*.12
                sx,sy=dx/d*math.cos(spread)-dy/d*math.sin(spread), dx/d*math.sin(spread)+dy/d*math.cos(spread)
                fire(self.pools.bullets,self.player.pos.x,self.player.pos.y,sx,sy,BULLET_SPEED,self.progress.damage)
            self.fire_clock=self.progress.fire_rate
        update_bullets(self.pools.bullets,zombies,dt,WORLD_WIDTH,WORLD_HEIGHT,self.grid)
        reward_multiplier = 3 if self.demo_mode else 1
        cleanup_dead(
            self.pools.zombies.active(),
            self.pools,
            self.progress,
            reward_multiplier,
        )
        if collect_pickups(self.player,self.pools.pickups.active(),self.progress,dt): self.state.transition(GameMode.LEVEL_UP)
        self.progress.wave=1+int(self.progress.score/200)
        if (self.player.pos.x-self.merchant.x)**2+(self.player.pos.y-self.merchant.y)**2 < 18**2 and pyxel.btnp(pyxel.KEY_E): self.state.transition(GameMode.SHOP)
        if self.progress.health<=0: self.state.transition(GameMode.GAME_OVER)
    def input(self):
        if pyxel.btnp(pyxel.KEY_F3): self.dev=not self.dev
        if pyxel.btnp(pyxel.KEY_F2): self.demo_mode=not self.demo_mode
        if pyxel.btnp(pyxel.KEY_F4):
            self.progress.xp += 50; self.progress.coins += 100
            if self.progress.xp >= self.progress.xp_to_next:
                self.progress.xp -= self.progress.xp_to_next; self.progress.level += 1
                self.progress.xp_to_next=int(self.progress.xp_to_next*1.35+4)
                from game.data import ABILITIES
                self.progress.ability_choices=random.sample(ABILITIES,3); self.state.transition(GameMode.LEVEL_UP)
        if pyxel.btnp(pyxel.KEY_U) and self.state.mode == GameMode.PLAYING: self.state.transition(GameMode.UPGRADES)
        if self.state.mode==GameMode.GAME_OVER and pyxel.btnp(pyxel.KEY_R): self.restart()
    def draw(self): draw_world(
        pyxel, self.player, self.pools, self.progress, self.state.mode,
        self.camera, self.merchant, self.dev, self.demo_mode,
    )
    def _near_merchant(self): return (self.player.pos.x-self.merchant.x)**2+(self.player.pos.y-self.merchant.y)**2 < 24**2
    def run(self):
        pyxel.init(WIDTH,HEIGHT,title='Night Shift',fps=FPS)
        resource_path = os.path.join(os.path.dirname(__file__), "assets.pyxres")
        load_assets(pyxel, resource_path if os.path.exists(resource_path) else None)
        pyxel.run(self._update,self.draw)
    def _update(self):
        now=time.perf_counter(); dt=min(DT_MAX,max(0.0,now-self.last)); self.last=now
        self.input(); self.update(dt)
if __name__=='__main__':
    if pyxel is None: raise SystemExit('Install dependencies with: pip install -r requirements.txt')
    Game().run()
