import errno

from .scene import bpy
from .constants import PORT, TICK
from .server import Server

NS_SERVER = "mcblender_server"
NS_TICK = "mcblender_tick"


def tick():
    server = bpy.app.driver_namespace.get(NS_SERVER)
    if server is None or not server.running:
        return None
    try:
        server.poll(TICK)
    except Exception as exc:
        print("[mcblender] tick error: %s" % exc)
    return TICK


def onFrame(scene, depsgraph):
    server = bpy.app.driver_namespace.get(NS_SERVER)
    if server is not None:
        server.onFrame(scene, depsgraph)


def stopServer():
    ns = bpy.app.driver_namespace
    previous = ns.get(NS_TICK)
    if previous is not None and bpy.app.timers.is_registered(previous):
        bpy.app.timers.unregister(previous)
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for fn in list(bpy.app.handlers.frame_change_post):
        if getattr(fn, "__name__", "") == "onFrame":
            bpy.app.handlers.frame_change_post.remove(fn)
    server = ns.get(NS_SERVER)
    if server is not None:
        try:
            server.stop()
        except Exception as exc:
            print("[mcblender] stop error: %s" % exc)
    ns[NS_SERVER] = None
    ns[NS_TICK] = None
    print("[mcblender] stopped")


def startServer():
    stopServer()
    server = Server()
    try:
        server.start()
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print("[mcblender] port %d is still held by something else" % PORT)
        else:
            print("[mcblender] could not start: %s" % exc)
        return
    ns = bpy.app.driver_namespace
    ns[NS_SERVER] = server
    ns[NS_TICK] = tick
    bpy.app.timers.register(tick, first_interval=TICK)
    bpy.app.handlers.frame_change_post.append(onFrame)


def current():
    if bpy is None:
        return None
    server = bpy.app.driver_namespace.get(NS_SERVER)
    if server is None or not server.running:
        return None
    return server
