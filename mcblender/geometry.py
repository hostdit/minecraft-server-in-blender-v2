import math

import numpy as np


def translate(x, y, z):
    m = np.eye(4)
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m


def rotY(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m


def rotX(a):
    c, s = math.cos(a), math.sin(a)
    m = np.eye(4)
    m[1, 1] = c
    m[1, 2] = -s
    m[2, 1] = s
    m[2, 2] = c
    return m


SWAP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)


def voxelise(M, half):
    signs = np.array([[sx, sy, sz, 1.0] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    corners = (signs * np.append(half, 1.0)) @ M.T
    lo = np.floor(corners[:, :3].min(0)).astype(int)
    hi = np.ceil(corners[:, :3].max(0)).astype(int)
    xs = np.arange(lo[0], hi[0])
    ys = np.arange(lo[1], hi[1])
    zs = np.arange(lo[2], hi[2])
    grid = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    centres = np.hstack([grid + 0.5, np.ones((len(grid), 1))])
    local = centres @ np.linalg.inv(M).T
    mask = (np.abs(local[:, :3]) <= half).all(1)
    return grid[mask], local[mask][:, :3]
