import math

import numpy as np

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:
    bpy = None
    bmesh = None
    Matrix = None
    Vector = None

from .constants import (AIR, BLACK, BLOCK_COLOURS, COLL, CONE_H, CONE_R0, CONE_R1, DEFAULT_COLOUR,
                        DOMAIN_H, EYE, FIRE, FPS, GLOWSTONE, GREEN, GREY, GROUND, LAVA, NETHERRACK,
                        SILVER, WOOL, XMAX, XMIN)
from .geometry import SWAP, translate
from .world import inside

WOOL_COLOURS = {13: (0.1, 0.45, 0.1), 5: (0.35, 0.75, 0.15), 15: (0.05, 0.05, 0.05),
                0: (0.95, 0.95, 0.95), 7: (0.3, 0.3, 0.3), 8: (0.6, 0.6, 0.6),
                14: (0.7, 0.1, 0.1)}
WOOL_DEFAULT = (0.8, 0.8, 0.8)
RANK_STATES = (0, SILVER, GREY, BLACK, FIRE << 4)


def makeMaterial(name, rgb, emission=0.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
    if getattr(mat, "node_tree", None) is None:
        try:
            mat.use_nodes = True
        except Exception:
            return mat
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            node.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
            node.inputs["Roughness"].default_value = 0.85
            if emission > 0.0:
                key = "Emission Color" if "Emission Color" in node.inputs else "Emission"
                node.inputs[key].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
                node.inputs["Emission Strength"].default_value = emission
            break
    return mat


def smokeMaterial():
    mat = bpy.data.materials.get("MC_Smoke")
    if mat is not None:
        return mat
    mat = bpy.data.materials.new("MC_Smoke")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        if node.type != "OUTPUT_MATERIAL":
            nodes.remove(node)
    out = nodes[0]
    vol = nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 8.0
    vol.inputs["Color"].default_value = (0.25, 0.22, 0.2, 1.0)
    vol.inputs["Blackbody Intensity"].default_value = 4.0
    links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat


def unitCube():
    mesh = bpy.data.meshes.get("MC_UnitCube")
    if mesh is not None:
        return mesh
    mesh = bpy.data.meshes.new("MC_UnitCube")
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.materials.append(None)
    return mesh


class Scene:
    def __init__(self):
        self.collection = None
        self.player = None
        self.camera = None
        self.domain = None
        self.blocks = {}
        self.parts = {}
        self.materials = {}

    def material(self, state):
        bid = state >> 4
        key = state if bid == WOOL else bid << 4
        mat = self.materials.get(key)
        if mat is None:
            if bid == WOOL:
                rgb = WOOL_COLOURS.get(state & 15, WOOL_DEFAULT)
            else:
                rgb = BLOCK_COLOURS.get(bid, DEFAULT_COLOUR)
            mat = makeMaterial("MC_Mat_%d" % key, rgb, 4.0 if bid in (LAVA, GLOWSTONE) else 0.0)
            self.materials[key] = mat
        return mat

    def cube(self, name, state):
        obj = bpy.data.objects.new(name, unitCube())
        self.collection.objects.link(obj)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = self.material(state)
        return obj

    def build(self, volcano):
        self.wipe()
        coll = bpy.data.collections.get(COLL)
        if coll is None:
            coll = bpy.data.collections.new(COLL)
        if coll.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)
        self.collection = coll
        self.buildTerrain()
        self.buildVolcano(volcano)
        self.buildPlayer()
        self.buildCamera()
        self.buildLight()
        self.setWorld()
        scene = bpy.context.scene
        scene.render.fps = FPS
        scene.frame_start = 1
        scene.frame_end = 6000

    def buildTerrain(self):
        span = XMAX - XMIN
        bm = bmesh.new()
        grid = {}
        for i in range(span + 1):
            for j in range(span + 1):
                grid[(i, j)] = bm.verts.new((XMIN + i, XMIN + j, float(GROUND)))
        for i in range(span):
            for j in range(span):
                bm.faces.new((grid[(i, j)], grid[(i + 1, j)], grid[(i + 1, j + 1)], grid[(i, j + 1)]))
        walls = []
        lo, hi = float(XMIN), float(XMAX)
        for k in range(span):
            s, e = XMIN + k, XMIN + k + 1
            for layer in range(GROUND):
                y0, y1 = float(layer), float(layer + 1)
                for quad in (((s, lo, y0), (e, lo, y0), (e, lo, y1), (s, lo, y1)),
                             ((e, hi, y0), (s, hi, y0), (s, hi, y1), (e, hi, y1)),
                             ((lo, e, y0), (lo, s, y0), (lo, s, y1), (lo, e, y1)),
                             ((hi, s, y0), (hi, e, y0), (hi, e, y1), (hi, s, y1))):
                    walls.append((bm.faces.new([bm.verts.new(p) for p in quad]), layer))
        mesh = bpy.data.meshes.new("MC_Terrain")
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(makeMaterial("MC_Grass", BLOCK_COLOURS[2]))
        mesh.materials.append(makeMaterial("MC_Dirt", BLOCK_COLOURS[3]))
        mesh.materials.append(makeMaterial("MC_Bedrock", BLOCK_COLOURS[7]))
        offset = span * span
        for index, (_, layer) in enumerate(walls):
            mesh.polygons[offset + index].material_index = 0 if layer == GROUND - 1 else (2 if layer == 0 else 1)
        mesh.update()
        obj = bpy.data.objects.new("MC_Terrain", mesh)
        self.collection.objects.link(obj)

    def buildVolcano(self, volcano):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=CONE_R0, radius2=CONE_R1, depth=CONE_H)
        mesh = bpy.data.meshes.new("MC_Volcano")
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(makeMaterial("MC_Netherrack", BLOCK_COLOURS[NETHERRACK]))
        cone = bpy.data.objects.new("MC_Volcano", mesh)
        cone.location = (volcano.cx + 0.5, volcano.cz + 0.5, GROUND + CONE_H / 2)
        self.collection.objects.link(cone)
        lava = self.cube("MC_Crater", LAVA << 4)
        lava.location = (volcano.cx - CONE_R1 + 0.5, volcano.cz - CONE_R1 + 0.5, GROUND + CONE_H - 4)
        lava.scale = (CONE_R1 * 2, CONE_R1 * 2, 1)
        self.buildSmokeDomain(volcano)
        self.buildSmokeFlow(volcano)

    def buildSmokeDomain(self, volcano):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        mesh = bpy.data.meshes.new("MC_SmokeDomain")
        bm.to_mesh(mesh)
        bm.free()
        domain = bpy.data.objects.new("MC_SmokeDomain", mesh)
        domain.location = (volcano.cx + 0.5, volcano.cz + 0.5, GROUND + CONE_H - 6 + DOMAIN_H / 2)
        domain.scale = (44.0, 44.0, float(DOMAIN_H))
        self.collection.objects.link(domain)
        mod = domain.modifiers.new("Fluid", "FLUID")
        mod.fluid_type = "DOMAIN"
        ds = mod.domain_settings
        ds.domain_type = "GAS"
        ds.resolution_max = 64
        ds.use_adaptive_domain = False
        ds.cache_type = "REPLAY"
        ds.cache_frame_end = 6000
        ds.alpha = -0.002
        ds.beta = 0.5
        ds.vorticity = 0.25
        ds.use_dissolve_smoke = True
        ds.dissolve_speed = 40
        mesh.materials.append(smokeMaterial())
        self.domain = domain

    def buildSmokeFlow(self, volcano):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        mesh = bpy.data.meshes.new("MC_SmokeFlow")
        bm.to_mesh(mesh)
        bm.free()
        flow = bpy.data.objects.new("MC_SmokeFlow", mesh)
        flow.location = (volcano.cx + 0.5, volcano.cz + 0.5, GROUND + CONE_H - 2.5)
        flow.scale = (CONE_R1 * 2 - 1, CONE_R1 * 2 - 1, 2.0)
        flow.hide_render = True
        flow.display_type = "WIRE"
        self.collection.objects.link(flow)
        mod = flow.modifiers.new("Fluid", "FLUID")
        mod.fluid_type = "FLOW"
        fs = mod.flow_settings
        fs.flow_type = "BOTH"
        fs.flow_behavior = "INFLOW"
        fs.use_initial_velocity = True
        fs.velocity_coord = (0.0, 0.0, 9.0)
        fs.density = 1.0
        fs.fuel_amount = 1.5
        fs.temperature = 3.0
        fs.surface_distance = 0.5

    def buildPlayer(self):
        self.player = self.cube("MC_Player", 45 << 4)
        self.player.scale = (0.6, 0.6, 1.8)
        self.player.hide_render = True

    def buildCamera(self):
        camData = bpy.data.cameras.new("MC_CameraData")
        camData.sensor_fit = "VERTICAL"
        camData.angle = math.radians(70.0)
        cam = bpy.data.objects.new("MC_Camera", camData)
        cam.location = (0.5, 0.5, GROUND + 1 + EYE)
        cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        self.collection.objects.link(cam)
        bpy.context.scene.camera = cam
        self.camera = cam

    def buildLight(self):
        data = bpy.data.lights.new("MC_SunData", type="SUN")
        data.energy = 3.0
        data.angle = math.radians(3.0)
        sun = bpy.data.objects.new("MC_Sun", data)
        sun.location = (30.0, -30.0, 60.0)
        sun.rotation_euler = (math.radians(50.0), 0.0, math.radians(35.0))
        self.collection.objects.link(sun)

    def setWorld(self):
        world = bpy.context.scene.world
        if world is None:
            world = bpy.data.worlds.new("MC_World")
            bpy.context.scene.world = world
        if getattr(world, "node_tree", None) is None:
            world.use_nodes = True
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                node.inputs[0].default_value = (0.45, 0.62, 0.85, 1.0)
                node.inputs[1].default_value = 1.0
                break

    def addBlock(self, x, y, z, state):
        if bpy is None or self.collection is None or (x, y, z) in self.blocks:
            return
        obj = self.cube("MC_Block_%d_%d_%d" % (x, y, z), state)
        obj.location = (float(x), float(z), float(y))
        self.blocks[(x, y, z)] = obj

    def removeBlock(self, x, y, z):
        obj = self.blocks.pop((x, y, z), None)
        if obj is not None:
            self.dropObj(obj)

    def dropObj(self, obj):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except ReferenceError:
            pass

    def makeDebris(self, state, pos):
        if bpy is None or self.collection is None:
            return None
        obj = self.cube("MC_Debris", state)
        obj.location = (pos[0] - 0.5, pos[2] - 0.5, pos[1] - 0.5)
        return obj

    def placeKaiju(self, mats):
        if bpy is None or self.collection is None:
            return
        for name, (M, half) in mats.items():
            obj = self.parts.get(name)
            if obj is None:
                obj = self.cube("MC_Kaiju_" + name, GREEN)
                self.parts[name] = obj
            bl = SWAP @ M @ SWAP
            scale = np.diag([half[0] * 2, half[2] * 2, half[1] * 2, 1.0])
            obj.matrix_world = Matrix((bl @ scale @ translate(-0.5, -0.5, -0.5)).tolist())

    def removeKaiju(self):
        for obj in self.parts.values():
            self.dropObj(obj)
        self.parts = {}

    def updatePlayer(self, x, y, z, yaw, pitch):
        if bpy is None or self.player is None:
            return
        self.player.location = (x - 0.3, z - 0.3, y)
        self.camera.location = (x, z, y + EYE)
        self.camera.rotation_euler = (math.radians(90.0 - pitch), 0.0, math.radians(yaw))

    def wipe(self):
        if bpy is None:
            return
        coll = bpy.data.collections.get(COLL)
        if coll is not None:
            for obj in list(coll.objects):
                self.dropObj(obj)
            try:
                bpy.data.collections.remove(coll)
            except ReferenceError:
                pass
        self.__init__()


def sampleSmoke(domain, depsgraph, world):
    if domain is None or depsgraph is None:
        return {}
    ev = domain.evaluated_get(depsgraph)
    mod = ev.modifiers.get("Fluid")
    if mod is None or mod.domain_settings is None:
        return {}
    ds = mod.domain_settings
    res = tuple(int(v) for v in ds.domain_resolution)
    if min(res) <= 0:
        return {}
    dens = np.array(ds.density_grid, dtype=np.float32)
    if dens.size != res[0] * res[1] * res[2]:
        return {}
    flame = np.array(ds.flame_grid, dtype=np.float32)
    if flame.size != dens.size:
        flame = np.zeros_like(dens)
    dens = dens.reshape(res[2], res[1], res[0])
    flame = flame.reshape(res[2], res[1], res[0])
    dims = ev.dimensions
    cell = (dims.x / res[0], dims.y / res[1], dims.z / res[2])
    origin = ev.matrix_world @ Vector(ev.bound_box[0])
    hot = np.argwhere((dens > 0.08) | (flame > 0.25))
    if len(hot) == 0:
        return {}
    k, j, i = hot[:, 0], hot[:, 1], hot[:, 2]
    bx = np.floor(origin.x + (i + 0.5) * cell[0]).astype(int)
    bz = np.floor(origin.y + (j + 0.5) * cell[1]).astype(int)
    by = np.floor(origin.z + (k + 0.5) * cell[2]).astype(int)
    d = dens[k, j, i]
    f = flame[k, j, i]
    rank = np.where(f > 0.25, 4, np.where(d > 0.5, 3, np.where(d > 0.22, 2, 1)))
    out = {}
    best = {}
    for x, y, z, r in zip(bx.tolist(), by.tolist(), bz.tolist(), rank.tolist()):
        c = (x, y, z)
        if r > best.get(c, 0):
            best[c] = r
    for c, r in best.items():
        if inside(c) and world.get(c) == AIR:
            out[c] = RANK_STATES[r]
    return out


def play(fromStart):
    if bpy is None:
        return
    try:
        scene = bpy.context.scene
        if fromStart:
            scene.frame_set(1)
        win = bpy.context.window_manager.windows[0]
        if win.screen.is_animation_playing:
            return
        with bpy.context.temp_override(window=win, screen=win.screen, scene=scene):
            bpy.ops.screen.animation_play()
    except Exception as exc:
        print("[mcblender] could not start playback (%s), press space in Blender" % exc)
