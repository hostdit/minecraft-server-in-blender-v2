import math

from .constants import (AIR, BEDROCK, DIRT, FIRE, GRASS, GRAVITY, MAX_DEBRIS_OBJECTS, TOP,
                        XMAX, XMIN)


def base(y):
    if y == 0:
        return BEDROCK << 4
    if y in (1, 2):
        return DIRT << 4
    if y == 3:
        return GRASS << 4
    return AIR


def inside(c):
    return XMIN <= c[0] < XMAX and XMIN <= c[2] < XMAX and 0 <= c[1] < TOP


def cellOf(p):
    return (math.floor(p[0]), math.floor(p[1]), math.floor(p[2]))


class World:
    def __init__(self):
        self.over = {}
        self.dirty = set()

    def get(self, c):
        st = self.over.get(c)
        if st is None:
            return base(c[1])
        return st

    def set(self, c, state):
        if state == base(c[1]):
            self.over.pop(c, None)
        else:
            self.over[c] = state
        self.dirty.add(c)

    def solid(self, c):
        if c[1] < 0:
            return True
        if c[1] >= TOP:
            return False
        st = self.get(c)
        return st != AIR and (st >> 4) != FIRE


class Debris:
    def __init__(self):
        self.items = []
        self.makeObj = None
        self.dropObj = None

    def spawn(self, pos, vel, state):
        obj = None
        if self.makeObj is not None and sum(1 for d in self.items if d[3] is not None) < MAX_DEBRIS_OBJECTS:
            obj = self.makeObj(state, pos)
        self.items.append([list(pos), list(vel), state, obj])

    def step(self, world):
        alive = []
        layer = {}
        for d in self.items:
            p, v, st, obj = d
            v[1] -= GRAVITY
            n = [p[0] + v[0], p[1] + v[1], p[2] + v[2]]
            here = cellOf(p)
            there = cellOf(n)
            if there != here and world.solid(there):
                if inside(here) and world.get(here) == AIR:
                    world.set(here, st)
                if obj is not None and self.dropObj is not None:
                    self.dropObj(obj)
                continue
            p[:] = n
            if p[1] > TOP + 40 or p[0] < XMIN - 40 or p[0] > XMAX + 40 or p[2] < XMIN - 40 or p[2] > XMAX + 40:
                if obj is not None and self.dropObj is not None:
                    self.dropObj(obj)
                continue
            if obj is not None:
                obj.location = (p[0] - 0.5, p[2] - 0.5, p[1] - 0.5)
            alive.append(d)
            c = cellOf(p)
            if inside(c):
                layer[c] = st
        self.items = alive
        return layer


class Display:
    def __init__(self, world, sendChunk):
        self.world = world
        self.sendChunk = sendChunk
        self.shown = {}

    def frame(self, layers, connected):
        dirty = self.world.dirty
        self.world.dirty = set()
        if not connected:
            self.shown = {}
            return
        cells = set(self.shown) | dirty
        for layer in layers:
            cells |= layer.keys()
        byChunk = {}
        for c in cells:
            want = None
            for layer in layers:
                want = layer.get(c)
                if want is not None:
                    break
            ground = self.world.get(c)
            if want is None:
                want = ground
            cur = self.shown.get(c, ground)
            if want != cur or c in dirty:
                byChunk.setdefault((c[0] >> 4, c[2] >> 4), []).append((c[0], c[1], c[2], want))
            if want == ground:
                self.shown.pop(c, None)
            else:
                self.shown[c] = want
        for (cx, cz), recs in byChunk.items():
            self.sendChunk(cx, cz, recs)
