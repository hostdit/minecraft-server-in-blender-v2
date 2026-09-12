from .scene import bpy
from .constants import KAIJU_HITS, PORT
from .runtime import current, startServer, stopServer


class MCSERVER_OT_start(bpy.types.Operator):
    bl_idname = "mcserver.start"
    bl_label = "Start"
    bl_description = "Bind the port and build the world"

    def execute(self, context):
        startServer()
        return {"FINISHED"}


class MCSERVER_OT_stop(bpy.types.Operator):
    bl_idname = "mcserver.stop"
    bl_label = "Stop"
    bl_description = "Close the socket and release the port"

    def execute(self, context):
        stopServer()
        return {"FINISHED"}


class MCSERVER_OT_erupt(bpy.types.Operator):
    bl_idname = "mcserver.erupt"
    bl_label = "Erupt"
    bl_description = "Rewind to frame 1, play, and feed the smoke sim into the world"

    def execute(self, context):
        server = current()
        if server is not None:
            server.erupt()
        return {"FINISHED"}


class MCSERVER_OT_kaiju(bpy.types.Operator):
    bl_idname = "mcserver.kaiju"
    bl_label = "Spawn Kaiju"
    bl_description = "Spawn the creeper and start it walking toward the player"

    def execute(self, context):
        server = current()
        if server is not None:
            server.spawnKaiju()
        return {"FINISHED"}


class MCSERVER_OT_boom(bpy.types.Operator):
    bl_idname = "mcserver.boom"
    bl_label = "Detonate"
    bl_description = "Skip the fight and blow the kaiju up"

    def execute(self, context):
        server = current()
        if server is not None:
            server.detonate()
        return {"FINISHED"}


class MCSERVER_OT_map(bpy.types.Operator):
    bl_idname = "mcserver.map"
    bl_label = "Render Map"
    bl_description = "Render the player's view in Cycles and push it into the held map"

    def execute(self, context):
        server = current()
        if server is not None:
            server.renderMap()
        return {"FINISHED"}


class MCSERVER_OT_reset(bpy.types.Operator):
    bl_idname = "mcserver.reset"
    bl_label = "Reset"
    bl_description = "Remove the kaiju, debris and plume"

    def execute(self, context):
        server = current()
        if server is not None:
            server.reset()
        return {"FINISHED"}


class MCSERVER_PT_panel(bpy.types.Panel):
    bl_label = "Minecraft Server"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MC Server"

    def draw(self, context):
        layout = self.layout
        server = current()
        row = layout.row(align=True)
        row.operator("mcserver.start", icon="PLAY")
        row.operator("mcserver.stop", icon="PAUSE")
        box = layout.box()
        if server is None:
            box.label(text="Stopped", icon="RADIOBUT_OFF")
            return
        box.label(text="Listening on %d" % PORT, icon="RADIOBUT_ON")
        if server.connected():
            box.label(text="Player: %s" % (server.username or "?"))
            box.label(text="X %.1f  Y %.1f  Z %.1f" % server.pos)
        else:
            box.label(text="Waiting for a client")
        box.label(text="In %d   Out %d   Queued %d" % (server.packetsIn, server.packetsOut, len(server.outbuf)))
        col = layout.column(align=True)
        col.operator("mcserver.erupt", icon="LIGHT_SUN")
        col.operator("mcserver.kaiju", icon="MONKEY")
        col.operator("mcserver.boom", icon="PARTICLES")
        col.operator("mcserver.map", icon="RENDER_STILL")
        col.operator("mcserver.reset", icon="LOOP_BACK")
        box = layout.box()
        box.label(text="Frame %d" % server.frame)
        box.label(text="Plume blocks: %d" % len(server.smoke))
        box.label(text="Debris flying: %d" % len(server.debris.items))
        if server.kaiju.active:
            box.label(text="Kaiju: %s, %d/%d hits" % (server.kaiju.phase, server.kaiju.hits, KAIJU_HITS))
        box.label(text="Maps rendered: %d" % server.mapCount)


CLASSES = (MCSERVER_OT_start, MCSERVER_OT_stop, MCSERVER_OT_erupt, MCSERVER_OT_kaiju,
           MCSERVER_OT_boom, MCSERVER_OT_map, MCSERVER_OT_reset, MCSERVER_PT_panel)


def register():
    for cls in CLASSES:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
