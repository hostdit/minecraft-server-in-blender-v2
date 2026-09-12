import os
import sys

import bpy


def projectRoot():
    here = globals().get("__file__", "")
    if here:
        root = os.path.dirname(os.path.abspath(here))
        if os.path.isdir(os.path.join(root, "mcblender")):
            return root
    if bpy.data.filepath:
        root = os.path.dirname(bpy.data.filepath)
        if os.path.isdir(os.path.join(root, "mcblender")):
            return root
    raise RuntimeError("run.py must sit next to the mcblender package, or the .blend must be saved beside it")


def load():
    root = projectRoot()
    if root not in sys.path:
        sys.path.insert(0, root)
    for name in [n for n in sys.modules if n == "mcblender" or n.startswith("mcblender.")]:
        del sys.modules[name]
    import mcblender
    return mcblender


load()
