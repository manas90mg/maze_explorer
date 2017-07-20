import math

import cocos
import cocos.collision_model as cm
import cocos.euclid as eu
from cocos.rect import Rect

import config

def world_to_view(v):
    """world coords to view coords; v an eu.Vector2, returns (float, float)"""
    return v.x * config.scale_x, v.y * config.scale_y

#def reflection_y(a):
#    assert isinstance(a, eu.Vector2)
#    return eu.Vector2(a.x, -a.y)

class Sensor():
    def __init__(self, angle, max_range):
        self.angle = angle
        self.max_range = max_range
        self.proximity = self.max_range
        self.line = None

    def proximity_norm(self):
        return max(0, min(self.proximity / self.max_range, self.max_range))

class Player(cocos.sprite.Sprite):
    palette = {}  # injected later
    """Player

    Responsabilities:
        Keeps state information for player
    """

    def __init__(self, cx, cy, btype, img, velocity=None):
        super(Player, self).__init__(img)

        settings = config.settings['player']
        palette = config.settings['view']['palette']
        self.palette = palette

        self.radius = settings['radius']
        # the 1.05 so that visual radius a bit greater than collision radius
        # FIXME: Both `scale_x` and `scale_y`
        self.scale = (self.radius * 1.05) * config.scale_x / (self.image.width / 2.0)
        self.btype = btype
        self.color = self.palette[btype]
        self.cshape = cm.CircleShape(eu.Vector2(cx, cy), self.radius)
        self.update_center(self.cshape.center)
        if velocity is None:
            velocity = eu.Vector2(0.0, 0.0)
        self.velocity = velocity

        self.impulse_dir = eu.Vector2(0.0, 1.0)

        self.top_speed = settings['top_speed']
        self.angular_velocity = settings['angular_velocity']
        self.accel = settings['accel']
        self.deaccel = settings['deaccel']

        self.game_over = False
        self.battery_use = settings['battery_use']
        self.rewards = settings['rewards']

        self.stats = {
            "battery": 100,
            "reward": 0,
            "score": 0
        }

        sensor_num = settings['sensors']['num']
        sensor_fov = settings['sensors']['fov']
        sensor_max = settings['sensors']['max_range']

        # Create sensors
        self.sensors = []
        for i in xrange(0, sensor_num):
            rad = (i-((sensor_num)/2))*sensor_fov;
            sensor = Sensor(rad, sensor_max)
            self.sensors.append(sensor)
            #print('Initialised sensor', i, rad)

    def get_reward(self):
        """
        Return reward and reset for next step
        """
        reward = self.stats['reward']
        self.stats['reward'] = 0

        return reward

    def get_state(self):
        """
        Create state from sensors and battery
        """
        # Create observation from sensor proximities
        observation = [o.proximity_norm() for o in self.sensors]
        # Include battery level in state
        observation.append(self.stats['battery']/100)

        return observation

    #def reset(self):
    #    self.impulse_dir = eu.Vector2(0.0, 1.0)

    def update_center(self, cshape_center):
        """cshape_center must be eu.Vector2"""
        assert isinstance(cshape_center, eu.Vector2)

        self.position = world_to_view(cshape_center)
        self.cshape.center = cshape_center

    def update_terminal(self):
        """
        Check terminal conditions
        """
        # Out of battery, set terminal state
        if self.stats['battery'] <= 0:
            self.stats['battery'] = 0
            # TODO: Let agent keep playing in hopes of finding end-goal
            #self.game_over = True

        if self.game_over:
            self.stats['reward'] += self.rewards['terminal']

    def update_rotation(self, dt, buttons):
        """
        Updates rotation and impulse direction
        """
        assert isinstance(buttons, dict)

        ma = buttons['right'] - buttons['left']
        if ma != 0:
            self.stats['battery'] -= self.battery_use['angular']
            self.rotation += ma * dt * self.angular_velocity

        # Redirect velocity in new direction
        a = math.radians(self.rotation)
        self.impulse_dir = eu.Vector2(math.sin(a), math.cos(a))

    def do_move(self, dt, buttons):
        """
        Updates velocity and returns Rects for start/finish positions
        """
        assert isinstance(dt, int) or isinstance(dt, float)
        assert isinstance(buttons, dict)

        newVel = self.velocity

        # Redirect existing vel to new direction.
        nv = newVel.magnitude()
        newVel = nv * self.impulse_dir

        mv = buttons['up']
        if mv != 0:
            self.stats['battery'] -= self.battery_use['linear']
            newVel += dt * mv * self.accel * self.impulse_dir
            nv = newVel.magnitude()
            if nv > self.top_speed:
                newVel *= self.top_speed / nv
        else:
            newVel += dt * self.deaccel * -newVel

        # Position collision rects
        oldRect = self.get_rect()
        newRect = oldRect.copy()
        newRect.x, newRect.y = self.get_destination(dt, newVel)

        return oldRect, newRect, newVel

    def get_destination(self, dt, velocity):
        """
        Apply velocity and return new position
        """
        assert isinstance(velocity, eu.Vector2)

        oldPos = self.cshape.center
        remaining_dt = dt
        newPos = oldPos.copy()

        while remaining_dt > 1.e-6:
            newPos = oldPos + remaining_dt * velocity
            consumed_dt = remaining_dt
            # what about screen boundaries ? if colision bounce
            #if new.x < r:
            #    consumed_dt = (r - ppos.x) / newVel.x
            #    new = ppos + consumed_dt * newVel
            #    newVel = -reflection_y(newVel)
            #if new.x > (self.width - r):
            #    consumed_dt = (self.width - r - ppos.x) / newVel.x
            #    new = ppos + consumed_dt * newVel
            #    newVel = -reflection_y(newVel)
            #if new.y < r:
            #    consumed_dt = (r - ppos.y) / newVel.y
            #    new = ppos + consumed_dt * newVel
            #    newVel = reflection_y(newVel)
            #if new.y > (self.height - r):
            #    consumed_dt = (self.height - r - ppos.y) / newVel.y
            #    new = ppos + consumed_dt * newVel
            #    newVel = reflection_y(newVel)
            remaining_dt -= consumed_dt

        # Upper left corner of Rect
        # FIXME: Use top, left
        newPos.x -= self.cshape.r
        newPos.y -= self.cshape.r

        return newPos

    def get_rect(self):
        ppos = self.cshape.center
        r = self.cshape.r

        # FIXME: Use top, bottom, left, right
        return Rect(ppos.x-r, ppos.y-r, r*2, r*2)
