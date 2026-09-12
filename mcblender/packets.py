import struct

import numpy as np

from .constants import MAP_BASE, MAP_SHADES, SECTIONS
from .protocol import writeString, writeVarint
from .world import base


def baseBlocks():
    blocks = bytearray(8192 * SECTIONS)
    for y in range(4):
        st = base(y)
        for i in range(256):
            k = (y * 256 + i) * 2
            blocks[k] = st & 0xFF
            blocks[k + 1] = st >> 8
    return blocks


BASE_BLOCKS = baseBlocks()
LIGHT = bytes([0xFF]) * (2048 * SECTIONS * 2)
BIOME = bytes([1]) * 256


def chunkPacket(world, cx, cz):
    blocks = bytearray(BASE_BLOCKS)
    for (x, y, z), st in world.over.items():
        if x >> 4 == cx and z >> 4 == cz:
            k = ((y * 16 + (z & 15)) * 16 + (x & 15)) * 2
            blocks[k] = st & 0xFF
            blocks[k + 1] = st >> 8
    data = bytes(blocks) + LIGHT + BIOME
    return (struct.pack(">ii", cx, cz) + bytes([1]) + struct.pack(">H", (1 << SECTIONS) - 1)
            + writeVarint(len(data)) + data)


def multiBlockChange(cx, cz, records):
    out = bytearray(struct.pack(">ii", cx, cz))
    out.extend(writeVarint(len(records)))
    for x, y, z, st in records:
        out.append(((x & 15) << 4) | (z & 15))
        out.append(y)
        out.extend(writeVarint(st))
    return bytes(out)


def slotPacket(slot, item, damage):
    return bytes([0]) + struct.pack(">hhbh", slot, item, 1, damage) + bytes([0])


def mapPacket(data):
    return (writeVarint(0) + bytes([0]) + writeVarint(0) + bytes([128, 128, 0, 0])
            + writeVarint(len(data)) + bytes(data))


def soundPacket(name, x, y, z, volume=1.0, pitch=63):
    return (writeString(name) + struct.pack(">iiifB", int(x * 8), int(y * 8), int(z * 8), volume, pitch))


def explosionPacket(x, y, z, radius):
    return struct.pack(">ffffifff", x, y, z, radius, 0, 0.0, 0.0, 0.0)


def chatPacket(text):
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    return writeString('{"text":"%s"}' % safe) + bytes([0])


def mapPalette():
    pal = np.zeros((144, 3), dtype=np.float32)
    for i, rgb in enumerate(MAP_BASE):
        if rgb is None:
            continue
        for s, mul in enumerate(MAP_SHADES):
            pal[i * 4 + s] = [v * mul / 255.0 for v in rgb]
    return pal


PALETTE = mapPalette()
PALETTE_UNIT = PALETTE / 255.0


def quantise(px):
    flat = px.reshape(-1, 3).astype(np.float32)
    d = ((flat[:, None, :] - PALETTE_UNIT[None, :, :]) ** 2).sum(-1)
    d[:, :4] = 1e9
    return d.argmin(1).astype(np.uint8).tobytes()
