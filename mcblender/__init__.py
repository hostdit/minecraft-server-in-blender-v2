from .runtime import current, startServer, stopServer
from .scene import bpy
from .server import Server

__all__ = ["Server", "current", "startServer", "stopServer"]

if bpy is not None:
    from . import ui
    ui.register()
    bpy.app.driver_namespace["mc_start"] = startServer
