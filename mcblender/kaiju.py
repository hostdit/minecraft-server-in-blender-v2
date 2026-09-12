import math
import random

import numpy as np

from .constants import (AIR, BEDROCK, BLACK, FACE, GREEN, GROUND, KAIJU_HITS, KAIJU_PRIME,
                        KAIJU_SCALE, KAIJU_SPEED, LIME, PARTS, WHITE)
from .geometry import rotX, rotY, translate, voxelise
from .packets import explosionPacket
from .world import inside


class Kaiju:
    def __init__(self):
        self.active = False
        self.phase = "idle"
        self.pos = [0.0, 0.0]
        self.yaw = 0.0
        self.hits = 0
        self.primeStart = 0
        self.cells = {}
        self.mats = {}
        self.lastFrame = 0

    def spawn(self, x, z):
        self.active = True
        self.phase = "walk"
        self.pos = [x, z]
        self.hits = 0
        self.cells = {}

    def centre(self):
        return (self.pos[0], GROUND + 13 * KAIJU_SCALE, self.pos[1])

    def matrices(self, frame):
        S = KAIJU_SCALE
        walking = self.phase == "walk"
        swing = math.sin(frame * 0.25) * 0.6 if walking else 0.0
        bob = abs(math.sin(frame * 0.25)) * 0.4 * S if walking else 0.0
        root = translate(self.pos[0], GROUND + bob, self.pos[1]) @ rotY(self.yaw)
        out = {}
        for name, c, h, pivot, sign in PARTS:
            local = translate(c[0] * S, c[1] * S, c[2] * S)
            if pivot is not None:
                local = translate(0, pivot * S, 0) @ rotX(swing * sign) @ translate(0, -pivot * S, 0) @ local
            out[name] = (root @ local, np.array(h, dtype=float) * S)
        return out

    def colour(self, name, c, local, flash):
        if name == "head":
            S = KAIJU_SCALE
            hx, hy, hz = 4 * S, 4 * S, 4 * S
            if local[2] > hz - 1.0:
                col = min(7, max(0, int((local[0] + hx) / S)))
                row = min(7, max(0, int((hy - local[1]) / S)))
                if FACE[row][col] == "#":
                    return BLACK
        if flash:
            return WHITE
        if (c[0] * 73856093 ^ c[1] * 19349663 ^ c[2] * 83492791) & 7 == 0:
            return LIME
        return GREEN

    def hit(self, server, frame):
        if not self.active or self.phase != "walk":
            return
        self.hits += 1
        left = KAIJU_HITS - self.hits
        if left > 0:
            if left % 5 == 0 or left < 5:
                server.chat("Kaiju: %d hits left" % left)
            return
        self.phase = "prime"
        self.primeStart = frame
        cx, cy, cz = self.centre()
        server.sound("creeper.primed", cx, cy, cz, 4.0, 63)
        server.chat("Kaiju: ssssssss")

    def frame(self, frame, server):
        if not self.active:
            return {}
        if self.phase == "walk":
            dx = server.pos[0] - self.pos[0]
            dz = server.pos[2] - self.pos[1]
            dist = math.hypot(dx, dz)
            if dist > 1e-6:
                self.yaw = math.atan2(dx, dz)
            if dist > 9.0:
                self.pos[0] += dx / dist * KAIJU_SPEED
                self.pos[1] += dz / dist * KAIJU_SPEED
        elif self.phase == "prime" and frame - self.primeStart >= KAIJU_PRIME:
            self.explode(server)
            return {}
        flash = self.phase == "prime" and ((frame - self.primeStart) // 5) % 2 == 0
        self.mats = self.matrices(frame)
        cells = {}
        for name, (M, half) in self.mats.items():
            grid, local = voxelise(M, half)
            for (x, y, z), l in zip(grid.tolist(), local.tolist()):
                c = (x, y, z)
                if inside(c):
                    cells[c] = self.colour(name, c, l, flash)
        cx, cy, cz = self.centre()
        for c in cells:
            if c not in self.cells:
                vel = [c[0] + 0.5 - cx, 0.0, c[2] + 0.5 - cz]
                n = math.hypot(vel[0], vel[2]) or 1.0
                vel = [vel[0] / n * 0.35 + random.uniform(-0.1, 0.1), random.uniform(0.45, 0.7),
                       vel[2] / n * 0.35 + random.uniform(-0.1, 0.1)]
                server.fling(c, vel)
        self.cells = cells
        server.scene.placeKaiju(self.mats)
        return cells

    def explode(self, server):
        cx, cy, cz = self.centre()
        for c, st in self.cells.items():
            vel = [c[0] + 0.5 - cx, c[1] + 0.5 - cy, c[2] + 0.5 - cz]
            n = math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2) or 1.0
            k = random.uniform(0.5, 0.95)
            vel = [vel[0] / n * k, vel[1] / n * k + 0.25, vel[2] / n * k]
            server.debris.spawn([c[0] + 0.5, c[1] + 0.5, c[2] + 0.5], vel, st)
        fx, fz = round(self.pos[0]), round(self.pos[1])
        for dx in range(-9, 10):
            for dz in range(-9, 10):
                d = math.hypot(dx, dz)
                if d > 9:
                    continue
                depth = int(math.sqrt(max(0.0, 81 - d * d)) / 3)
                for y in range(max(1, GROUND - depth), GROUND + 12):
                    c = (fx + dx, y, fz + dz)
                    if not inside(c):
                        continue
                    st = server.world.get(c)
                    if st == AIR or st >> 4 == BEDROCK:
                        continue
                    server.world.set(c, AIR)
                    server.scene.removeBlock(*c)
                    if y >= GROUND - 1 and d > 4:
                        server.debris.spawn([c[0] + 0.5, c[1] + 0.5, c[2] + 0.5],
                                            [dx / d * 0.5, random.uniform(0.3, 0.6), dz / d * 0.5], st)
        server.send(0x27, explosionPacket(cx, cy, cz, 12.0))
        server.sound("random.explode", cx, cy, cz, 6.0, 40)
        server.chat("Kaiju: boom")
        self.cells = {}
        self.active = False
        self.phase = "dead"
        server.scene.removeKaiju()
