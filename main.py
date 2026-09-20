"""Night Shift: asset-free Pyxel 2.x survival game."""
import math, time, random, os
try:
    import pyxel
except ImportError:
    pyxel = None
from game.config import *
from game.data import Vec2, SHOP_ITEMS
from game.entities import Player, Shop
from game.pools import EntityPools
from game.spatial_hash import SpatialHash
from game.state import GameMode, PlayerProgress, StateMachine
from game.systems.movement import move_player, move_zombies, update_player_facing
from game.systems.combat import (
    damage_at_point, fire, fire_beam, hail_burst, nearest_target,
    strike_lightning_chain, update_bullets,
)
from game.systems.spawn import spawn_zombie
from game.systems.shop import update_shop, shop_obstacle, shop_touching
from game.systems.progression import cleanup_dead, collect_pickups, buy, apply_ability, buy_permanent, tick_zombie_hit_effects
from render.draw import draw_world
from render.assets import load_assets

class Game:
    def __init__(self):
        self.state=StateMachine(); self.progress=PlayerProgress()
        self.pools=EntityPools(MAX_ZOMBIES,MAX_BULLETS,MAX_PARTICLES,MAX_PICKUPS)
        self.grid=SpatialHash(); self.player=Player(active=True,pos=Vec2(WORLD_WIDTH/2,WORLD_HEIGHT/2))
        self.shop=Shop(pos=Vec2(WORLD_WIDTH/2+32,WORLD_HEIGHT/2+55),park_timer=SHOP_PARK_DURATION)
        self.spawn_clock=0; self.fire_clock=0
        self.dev=False; self.demo_mode=False; self.hitboxes=False
        self.camera=Vec2(); self.last=time.perf_counter()
    def restart(self): self.__init__()
    def update(self, dt):
        if self.state.mode == GameMode.GAME_OVER: return
        if self.state.mode == GameMode.SHOP:
            near=self._near_shop()
            if not near: self.state.transition(GameMode.PLAYING); return
            if pyxel.btnp(pyxel.KEY_E): self.state.transition(GameMode.PLAYING)
            shop_items = [
                item for item in SHOP_ITEMS
                if item.name in self.progress.shop_inventory
            ]
            shop_keys = (pyxel.KEY_1, pyxel.KEY_2, pyxel.KEY_3, pyxel.KEY_4)
            for index, item in enumerate(shop_items):
                if pyxel.btnp(shop_keys[index]):
                    buy(self.progress, item.name)
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
        self.player.is_moving=bool(dx or dy)
        obstacle=shop_obstacle(self.shop)
        move_player(
            self.player,
            dx,
            dy,
            dt,
            (PLAYER_SPEED + self.progress.speed_bonus) * self.progress.move_multiplier,
            obstacle=obstacle,
        )
        if self.progress.orb_active:
            self.player.orb_angle = (self.player.orb_angle + dt * 2.5) % (2 * math.pi)
            self.player.orb_fire_timer = max(0.0, self.player.orb_fire_timer - dt)
        self.camera.x=max(0,min(WORLD_WIDTH-WIDTH,self.player.pos.x-WIDTH/2))
        self.camera.y=max(0,min(WORLD_HEIGHT-HEIGHT,self.player.pos.y-HEIGHT/2))
        self.progress.survival_time += dt; self.player.invulnerable=max(0,self.player.invulnerable-dt)
        if self.progress.shield_unlocked and self.progress.shield_hits <= 0:
            self.progress.shield_regen_timer = max(0.0, self.progress.shield_regen_timer - dt)
            if self.progress.shield_regen_timer <= 0:
                self.progress.shield_hits = self.progress.shield_max_hits
                self.progress.shield_ready = True
        if self.progress.fire_from_heaven_active:
            self.progress.fire_from_heaven_timer -= dt
        if self.progress.morning_star_active:
            self.progress.morning_star_angle = (self.progress.morning_star_angle + dt * 3.0) % (2 * math.pi)
            self.progress.morning_star_hit_timer = max(0.0, self.progress.morning_star_hit_timer - dt)
        if self.progress.hail_active:
            self.progress.hail_timer -= dt
        self.spawn_clock-=dt; self.fire_clock-=dt
        if self.spawn_clock<=0:
            spawn_zombie(self.pools.zombies,self.progress.wave)
            self.spawn_clock=max(.12,SPAWN_INTERVAL/(1+self.progress.survival_time/90))
        # Zombies mid-death-animation don't act or fight anymore -- excluded
        # from grid/movement/targeting/damage -- but zombies_all (unfiltered)
        # still gets drawn and still needs its hurt/death timers ticked down.
        zombies_all=list(self.pools.zombies.active())
        zombies=[z for z in zombies_all if not z.dying]
        hp_before={id(z): z.hp for z in zombies}
        self.grid.clear()
        for z in zombies: self.grid.insert(z)
        move_zombies(zombies,self.player,dt,ZOMBIE_SPEED+self.progress.wave*.5,obstacle=obstacle)
        if update_shop(self.shop,dt,zombies,self.player):
            if self.progress.shield_hits > 0:
                self.progress.shield_hits -= 1
                self.progress.shield_ready = self.progress.shield_hits > 0
                if self.progress.shield_hits == 0:
                    self.progress.shield_regen_timer = SHIELD_REGEN_TIME
                self.player.invulnerable = CONTACT_INVULN
            else:
                self.progress.health = 0
                self.player.invulnerable = CONTACT_INVULN
        for z in self.grid.query(self.player.pos.x,self.player.pos.y,24):
            if self.player.invulnerable<=0 and (z.pos.x-self.player.pos.x)**2+(z.pos.y-self.player.pos.y)**2 < 100:
                if self.progress.shield_hits > 0:
                    self.progress.shield_hits -= 1
                    self.progress.shield_ready = self.progress.shield_hits > 0
                    if self.progress.shield_hits == 0:
                        self.progress.shield_regen_timer = SHIELD_REGEN_TIME
                    self.player.invulnerable = CONTACT_INVULN
                else:
                    self.progress.health-=ZOMBIE_DAMAGE; self.player.invulnerable=CONTACT_INVULN
        target=nearest_target(
            self.player,
            zombies,
            self.grid,
            viewport=(self.camera.x, self.camera.y, WIDTH, HEIGHT),
            obstacle=obstacle,
        )
        aim_dx,aim_dy=(target.pos.x-self.player.pos.x,target.pos.y-self.player.pos.y) if target else (0,0)
        update_player_facing(self.player,dx,dy,aim_dx,aim_dy)
        self.player.anim_time+=dt
        self.player.is_firing=bool(target)
        if target and self.fire_clock<=0:
            dx,dy=target.pos.x-self.player.pos.x,target.pos.y-self.player.pos.y; d=math.hypot(dx,dy) or 1
            ramp=min(1.0,max(0,self.progress.damage-1)/BULLET_DAMAGE_RAMP)
            bullet_radius=BULLET_COIN_RADIUS+(BULLET_FULL_RADIUS-BULLET_COIN_RADIUS)*ramp
            for shot in range(self.progress.shots):
                spread=(shot-(self.progress.shots-1)/2)*.12
                sx,sy=dx/d*math.cos(spread)-dy/d*math.sin(spread), dx/d*math.sin(spread)+dy/d*math.cos(spread)
                fire(self.pools.bullets,self.player.pos.x,self.player.pos.y,sx,sy,BULLET_SPEED,self.progress.damage,bullet_radius)
            self.fire_clock=self.progress.fire_rate
        if target and self.progress.orb_count and self.player.orb_fire_timer <= 0:
            for orb_index in range(self.progress.orb_count):
                angle = self.player.orb_angle + (2 * math.pi * orb_index / self.progress.orb_count)
                orb_x = self.player.pos.x + math.cos(angle) * ORB_ORBIT_DISTANCE
                orb_y = self.player.pos.y + math.sin(angle) * ORB_ORBIT_DISTANCE
                dx,dy=target.pos.x-orb_x,target.pos.y-orb_y
                fire_beam(
                    self.pools.particles,
                    zombies,
                    self.grid,
                    orb_x, orb_y, dx, dy,
                    ORB_BULLET_SPEED,
                    ORB_DAMAGE + max(0, self.progress.damage - 1),
                )
            self.player.orb_fire_timer = ORB_FIRE_RATE
        if self.progress.fire_from_heaven_active and self.progress.fire_from_heaven_timer <= 0:
            for _ in range(self.progress.fire_from_heaven_count):
                strike_lightning_chain(
                    self.pools.particles,
                    zombies,
                    FIRE_FROM_HEAVEN_DAMAGE + max(0, self.progress.damage - 1),
                    self.player.pos.x,
                    self.player.pos.y,
                    viewport=(self.camera.x, self.camera.y, WIDTH, HEIGHT),
                    chain_range=FIRE_FROM_HEAVEN_CHAIN_RANGE,
                    chain_count=FIRE_FROM_HEAVEN_CHAIN_COUNT,
                )
            self.progress.fire_from_heaven_timer = FIRE_FROM_HEAVEN_RATE
        if self.progress.morning_star_active and self.progress.morning_star_hit_timer <= 0:
            for spike_index in range(self.progress.morning_star_count):
                angle = self.progress.morning_star_angle + (
                    2 * math.pi * spike_index / self.progress.morning_star_count
                )
                star_x = self.player.pos.x + math.cos(angle) * MORNING_STAR_DISTANCE
                star_y = self.player.pos.y + math.sin(angle) * MORNING_STAR_DISTANCE
                damage_at_point(
                    zombies, self.grid, star_x, star_y, 5,
                    MORNING_STAR_DAMAGE + self.progress.morning_star_count - 1
                    + max(0, self.progress.damage - 1),
                )
            self.progress.morning_star_hit_timer = MORNING_STAR_HIT_RATE
        if self.progress.hail_active and self.progress.hail_timer <= 0:
            hail_burst(
                self.pools.particles,
                zombies,
                self.grid,
                self.player.pos.x,
                self.player.pos.y,
                HAIL_RADIUS,
                HAIL_DAMAGE + self.progress.hail_level - 1
                + max(0, self.progress.damage - 1),
            )
            self.progress.hail_timer = HAIL_RATE
        update_bullets(self.pools.bullets,zombies,dt,WORLD_WIDTH,WORLD_HEIGHT,self.grid,obstacle=obstacle)
        # Anything that lost hp this frame but is still alive flashes its
        # "hurt" sheet; the ones that hit 0 are instead marked dying below.
        for z in zombies:
            if z.hp < hp_before[id(z)] and z.hp > 0:
                z.hurt_timer = ZOMBIE_HURT_DURATION
        for effect in self.pools.particles.active():
            effect.ttl -= dt
            if effect.ttl <= 0:
                self.pools.particles.release(effect)
        reward_multiplier = 3 if self.demo_mode else 1
        cleanup_dead(
            zombies,
            self.pools,
            self.progress,
            reward_multiplier,
        )
        tick_zombie_hit_effects(zombies_all, self.pools.zombies, dt)
        if collect_pickups(self.player,self.pools.pickups.active(),self.progress,dt): self.state.transition(GameMode.LEVEL_UP)
        self.progress.wave=1+int(self.progress.score/200)
        if self._near_shop() and pyxel.btnp(pyxel.KEY_E): self.state.transition(GameMode.SHOP)
        if self.progress.health <= 0:
            if self.progress.extra_lives > 0:
                self.progress.extra_lives -= 1
                self.progress.health = self.progress.max_health
                self.player.invulnerable = CONTACT_INVULN
            else:
                self.state.transition(GameMode.GAME_OVER)
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
        self.camera, self.shop, self.dev, self.demo_mode,
    )
    def _near_shop(self):
        return shop_touching(self.shop, self.player.pos.x, self.player.pos.y, self.player.radius)
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
