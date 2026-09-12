import math
import random

from .constants import (AIR, COBBLE, CONE_H, CONE_R0, CONE_R1, GRASS, GROUND, LAVA,
                        NETHERRACK, OBSIDIAN, VOLCANO)
from .world import inside


class Volcano:
    def __init__(self):
        self.cx, self.cz = VOLCANO
        self.erupting = False
        self.start = 0
        self.channels = []

    def radius(self, h):
        return CONE_R0 - (CONE_R0 - CONE_R1) * h / CONE_H

    def build(self, world):
        for h in range(CONE_H):
            r = self.radius(h)
            y = GROUND + h
            for dx in range(-CONE_R0, CONE_R0 + 1):
                for dz in range(-CONE_R0, CONE_R0 + 1):
                    d = math.hypot(dx, dz)
                    if d > r:
                        continue
                    c = (self.cx + dx, y, self.cz + dz)
                    if h >= CONE_H - 4 and d <= CONE_R1:
                        world.set(c, LAVA << 4 if h == CONE_H - 4 else AIR)
                    else:
                        world.set(c, NETHERRACK << 4)

    def erupt(self, frame):
        self.erupting = True
        self.start = frame
        self.channels = [[random.uniform(0, math.tau), 0] for _ in range(4)]

    def lavaAt(self, world, angle, step):
        h = CONE_H - 1 - step
        y = GROUND + max(h, 0)
        r = self.radius(h) + 1 if h >= 0 else CONE_R0 + 1 - h
        for a in (angle, angle + 0.09):
            c = (round(self.cx + math.cos(a) * r), y, round(self.cz + math.sin(a) * r))
            if inside(c) and world.get(c) >> 4 in (AIR, NETHERRACK, GRASS):
                world.set(c, LAVA << 4)

    def frame(self, frame, world, debris, sound):
        if not self.erupting:
            return
        t = frame - self.start
        if t % 4 == 0:
            for ch in self.channels:
                if ch[1] < CONE_H + 6:
                    self.lavaAt(world, ch[0], ch[1])
                    ch[1] += 1
        if t % 6 == 0:
            vel = [random.uniform(-0.4, 0.4), random.uniform(0.75, 1.0), random.uniform(-0.4, 0.4)]
            st = random.choice((OBSIDIAN << 4, COBBLE << 4, NETHERRACK << 4, NETHERRACK << 4))
            debris.spawn([self.cx + 0.5, GROUND + CONE_H + 1.5, self.cz + 0.5], vel, st)
            if t % 24 == 0:
                sound("liquid.lavapop", self.cx, GROUND + CONE_H, self.cz, 2.0, 40)
