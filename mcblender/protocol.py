import struct


def writeVarint(value):
    out = bytearray()
    value &= 0xFFFFFFFF
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def readVarint(buf, pos):
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            return None, pos
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
        if shift > 35:
            return None, pos
    if result >= 0x80000000:
        result -= 0x100000000
    return result, pos


def writeString(text):
    raw = text.encode("utf-8")
    return writeVarint(len(raw)) + raw


def readString(buf, pos):
    length, pos = readVarint(buf, pos)
    if length is None or length < 0:
        return "", pos
    return buf[pos:pos + length].decode("utf-8", "replace"), pos + length


def encodePosition(x, y, z):
    packed = ((x & 0x3FFFFFF) << 38) | ((y & 0xFFF) << 26) | (z & 0x3FFFFFF)
    return struct.pack(">Q", packed)


def decodePacked(raw):
    return struct.unpack(">Q", raw)[0]


def decodePosition(packed):
    x = packed >> 38
    y = (packed >> 26) & 0xFFF
    z = packed & 0x3FFFFFF
    if x >= 1 << 25:
        x -= 1 << 26
    if y >= 1 << 11:
        y -= 1 << 12
    if z >= 1 << 25:
        z -= 1 << 26
    return x, y, z
