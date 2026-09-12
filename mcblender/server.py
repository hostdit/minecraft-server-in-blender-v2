import base64
import errno
import os
import socket
import struct
import tempfile

import numpy as np

from .constants import (AIR, BEDROCK, CONE_H, FACE_OFFSETS, FIRE, GROUND, KAIJU_HITS, KAIJU_START,
                        KEEPALIVE, LAVA, MAP_SAMPLES, MOTD, PORT, SMOKE_EVERY, UUID, VIEW)
from .kaiju import Kaiju
from .packets import (chatPacket, chunkPacket, mapPacket, multiBlockChange, quantise, slotPacket,
                      soundPacket)
from .protocol import decodePosition, encodePosition, readString, readVarint, writeString, writeVarint
from .scene import Scene, bpy, play, sampleSmoke
from .volcano import Volcano
from .world import Debris, Display, World, inside

HANDSHAKE = 0
STATUS = 1
LOGIN = 2
PLAY = 3


def loadFavicon():
    if bpy is None or not bpy.data.filepath:
        return ""
    path = os.path.join(os.path.dirname(bpy.data.filepath), "favicon.png")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
    except OSError:
        return ""


class Server:
    def __init__(self):
        self.listener = None
        self.sock = None
        self.inbuf = bytearray()
        self.outbuf = bytearray()
        self.state = HANDSHAKE
        self.running = False
        self.username = ""
        self.keepId = 0
        self.lastKeep = 0.0
        self.clock = 0.0
        self.packetsIn = 0
        self.packetsOut = 0
        self.favicon = ""
        self.pos = (0.5, 5.0, 0.5)
        self.look = (0.0, 0.0)
        self.dirty = False
        self.world = World()
        self.scene = Scene()
        self.volcano = Volcano()
        self.volcano.build(self.world)
        self.world.dirty = set()
        self.kaiju = Kaiju()
        self.debris = Debris()
        self.debris.makeObj = self.scene.makeDebris
        self.debris.dropObj = self.scene.dropObj
        self.display = Display(self.world, self.sendChunkChanges)
        self.smoke = {}
        self.layers = [{}, {}, {}]
        self.frame = 0
        self.lastFrame = -1
        self.wantMap = False
        self.mapCount = 0
        self.busy = False

    def start(self):
        self.stop()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.setblocking(False)
        try:
            listener.bind(("0.0.0.0", PORT))
            listener.listen(5)
        except OSError:
            listener.close()
            raise
        self.listener = listener
        self.favicon = loadFavicon()
        if bpy is not None:
            self.scene.build(self.volcano)
        self.running = True
        self.clock = 0.0
        print("[mcblender] listening on port %d" % PORT)

    def stop(self):
        self.running = False
        self.closeClient("stopped")
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
        self.listener = None

    def closeClient(self, reason):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            print("[mcblender] client gone: %s" % reason)
        self.sock = None
        self.state = HANDSHAKE
        self.inbuf = bytearray()
        self.outbuf = bytearray()
        self.display.shown = {}

    def connected(self):
        return self.state == PLAY

    def poll(self, delta):
        self.clock += delta
        self.accept()
        self.receive()
        if self.world.dirty:
            self.display.frame(self.layers, self.connected())
        if self.wantMap:
            self.wantMap = False
            self.renderMap()
        self.flush()
        self.keepalive()
        if self.dirty:
            self.scene.updatePlayer(self.pos[0], self.pos[1], self.pos[2], self.look[0], self.look[1])
            self.dirty = False

    def accept(self):
        if self.listener is None or self.sock is not None:
            return
        try:
            conn, addr = self.listener.accept()
        except (BlockingIOError, OSError):
            return
        conn.setblocking(False)
        self.sock = conn
        self.state = HANDSHAKE
        self.inbuf = bytearray()
        self.outbuf = bytearray()
        print("[mcblender] connection from %s" % addr[0])

    def receive(self):
        if self.sock is None:
            return
        try:
            data = self.sock.recv(65536)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return
            self.closeClient("recv error %s" % exc)
            return
        if not data:
            self.closeClient("closed by client")
            return
        self.inbuf.extend(data)
        self.drain()

    def drain(self):
        while self.sock is not None:
            length, offset = readVarint(self.inbuf, 0)
            if length is None or length < 0 or len(self.inbuf) < offset + length:
                return
            body = bytes(self.inbuf[offset:offset + length])
            del self.inbuf[:offset + length]
            self.packetsIn += 1
            try:
                self.handle(body)
            except Exception as exc:
                print("[mcblender] handler error: %s" % exc)

    def handle(self, body):
        packetId, pos = readVarint(body, 0)
        if packetId is None:
            return
        if self.state == HANDSHAKE:
            if packetId == 0x00:
                _proto, pos = readVarint(body, pos)
                _addr, pos = readString(body, pos)
                nxt, pos = readVarint(body, pos + 2)
                self.state = STATUS if nxt == 1 else LOGIN
        elif self.state == STATUS:
            if packetId == 0x00:
                self.send(0x00, writeString(self.statusJson()))
            elif packetId == 0x01:
                self.send(0x01, body[pos:pos + 8])
                self.flush()
                self.closeClient("ping complete")
        elif self.state == LOGIN:
            if packetId == 0x00:
                self.username, pos = readString(body, pos)
                self.send(0x02, writeString(UUID) + writeString(self.username))
                self.state = PLAY
                self.join()
                print("[mcblender] %s joined" % self.username)
        elif self.state == PLAY:
            self.handlePlay(packetId, body, pos)

    def handlePlay(self, packetId, body, pos):
        if packetId == 0x04:
            x, y, z = struct.unpack_from(">ddd", body, pos)
            self.pos = (x, y, z)
            self.dirty = True
        elif packetId == 0x05:
            yaw, pitch = struct.unpack_from(">ff", body, pos)
            self.look = (yaw, pitch)
            self.dirty = True
        elif packetId == 0x06:
            x, y, z, yaw, pitch = struct.unpack_from(">dddff", body, pos)
            self.pos = (x, y, z)
            self.look = (yaw, pitch)
            self.dirty = True
        elif packetId == 0x07:
            self.dig(body, pos)
        elif packetId == 0x08:
            self.place(body, pos)
        elif packetId == 0x01:
            text, _ = readString(body, pos)
            print("[mcblender] <%s> %s" % (self.username, text))
            self.command(text.strip().lower())

    def dig(self, body, pos):
        status = body[pos]
        if status not in (0, 2):
            return
        c = decodePosition(struct.unpack_from(">Q", body, pos + 1)[0])
        if c in self.kaiju.cells:
            self.kaiju.hit(self, self.frame)
        elif inside(c) and self.world.get(c) >> 4 != BEDROCK:
            self.world.set(c, AIR)
            self.scene.removeBlock(*c)

    def place(self, body, pos):
        packed = struct.unpack_from(">Q", body, pos)[0]
        face = body[pos + 8]
        item = struct.unpack_from(">h", body, pos + 9)[0]
        if face > 5 or item < 1 or item > 255:
            return
        bx, by, bz = decodePosition(packed)
        dx, dy, dz = FACE_OFFSETS[face]
        c = (bx + dx, by + dy, bz + dz)
        if inside(c) and self.world.get(c) == AIR:
            self.world.set(c, item << 4)
            self.scene.addBlock(c[0], c[1], c[2], item << 4)

    def command(self, text):
        if text == "!erupt":
            self.erupt()
        elif text == "!kaiju":
            self.spawnKaiju()
        elif text == "!boom":
            self.detonate()
        elif text == "!map":
            self.wantMap = True
        elif text == "!reset":
            self.reset()

    def erupt(self):
        self.volcano.erupt(self.frame)
        self.sound("random.explode", self.volcano.cx, GROUND + CONE_H, self.volcano.cz, 6.0, 30)
        self.chat("Volcano: erupting")
        play(True)

    def spawnKaiju(self):
        self.kaiju.spawn(*KAIJU_START)
        self.chat("Kaiju: %d hits to kill it" % KAIJU_HITS)
        play(False)

    def detonate(self):
        if self.kaiju.active:
            self.kaiju.hits = KAIJU_HITS - 1
            self.kaiju.hit(self, self.frame)

    def reset(self):
        self.kaiju.active = False
        self.kaiju.phase = "idle"
        self.kaiju.cells = {}
        self.scene.removeKaiju()
        for d in self.debris.items:
            if d[3] is not None:
                self.scene.dropObj(d[3])
        self.debris.items = []
        self.volcano.erupting = False
        self.smoke = {}
        self.layers = [{}, {}, {}]
        self.display.frame(self.layers, self.connected())
        self.chat("Reset")

    def fling(self, c, vel):
        st = self.world.get(c)
        if st == AIR or st >> 4 in (BEDROCK, FIRE, LAVA):
            return
        self.world.set(c, AIR)
        self.scene.removeBlock(*c)
        self.debris.spawn([c[0] + 0.5, c[1] + 0.5, c[2] + 0.5], vel, st)

    def simulate(self, frame):
        if frame == self.lastFrame:
            return
        self.lastFrame = frame
        self.frame = frame
        self.volcano.frame(frame, self.world, self.debris, self.sound)
        kaijuLayer = self.kaiju.frame(frame, self)
        debrisLayer = self.debris.step(self.world)
        self.layers = [debrisLayer, kaijuLayer, self.smoke]
        self.display.frame(self.layers, self.connected())

    def onFrame(self, scene, depsgraph):
        if self.busy or not self.running:
            return
        self.busy = True
        try:
            frame = scene.frame_current
            if self.volcano.erupting and frame % SMOKE_EVERY == 0:
                self.smoke = sampleSmoke(self.scene.domain, depsgraph, self.world)
            elif not self.volcano.erupting:
                self.smoke = {}
            self.simulate(frame)
        except Exception as exc:
            print("[mcblender] frame error: %s" % exc)
        finally:
            self.busy = False

    def renderMap(self):
        if bpy is None or not self.connected():
            return
        scene = bpy.context.scene
        r = scene.render
        saved = (r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath,
                 r.engine, r.image_settings.file_format, scene.cycles.samples)
        path = os.path.join(tempfile.gettempdir(), "mc_map.png")
        r.resolution_x = r.resolution_y = 128
        r.resolution_percentage = 100
        r.filepath = path
        r.engine = "CYCLES"
        r.image_settings.file_format = "PNG"
        scene.cycles.samples = MAP_SAMPLES
        scene.cycles.use_denoising = True
        try:
            win = bpy.context.window_manager.windows[0]
            with bpy.context.temp_override(window=win, screen=win.screen, scene=scene):
                bpy.ops.render.render(write_still=True)
        except Exception as exc:
            print("[mcblender] render failed: %s (use the Render Map button in the sidebar)" % exc)
            return
        finally:
            (r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath,
             r.engine, r.image_settings.file_format, scene.cycles.samples) = saved
        img = bpy.data.images.load(path, check_existing=True)
        img.reload()
        px = np.empty(128 * 128 * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(128, 128, 4)[::-1, :, :3]
        self.send(0x34, mapPacket(quantise(px)))
        self.mapCount += 1
        self.chat("Map rendered in Cycles, %d samples" % MAP_SAMPLES)

    def join(self):
        payload = struct.pack(">i", 1) + bytes([1, 0, 0, 1]) + writeString("flat") + bytes([0])
        self.send(0x01, payload)
        self.send(0x05, encodePosition(0, GROUND + 1, 0))
        for cx in range(-VIEW, VIEW + 1):
            for cz in range(-VIEW, VIEW + 1):
                self.send(0x21, chunkPacket(self.world, cx, cz))
        self.pos = (0.5, float(GROUND + 1), 0.5)
        self.look = (0.0, 0.0)
        self.dirty = True
        self.send(0x08, struct.pack(">dddffB", 0.5, float(GROUND + 1), 0.5, 0.0, 0.0, 0))
        self.send(0x2F, slotPacket(36, 358, 0))
        self.chat("Served from Blender. !erupt  !kaiju  !map  !boom  !reset")
        self.lastKeep = self.clock
        self.display.shown = {}
        self.display.frame(self.layers, True)

    def sendChunkChanges(self, cx, cz, records):
        self.send(0x22, multiBlockChange(cx, cz, records))

    def chat(self, text):
        self.send(0x02, chatPacket(text))

    def sound(self, name, x, y, z, volume=1.0, pitch=63):
        self.send(0x29, soundPacket(name, x, y, z, volume, pitch))

    def keepalive(self):
        if not self.connected() or self.clock - self.lastKeep < KEEPALIVE:
            return
        self.keepId += 1
        self.send(0x00, writeVarint(self.keepId))
        self.lastKeep = self.clock

    def statusJson(self):
        online = 1 if self.connected() else 0
        icon = ',"favicon":"data:image/png;base64,%s"' % self.favicon if self.favicon else ""
        return ('{"version":{"name":"1.8.9","protocol":47},"players":{"max":1,"online":%d},'
                '"description":{"text":"%s"}%s}' % (online, MOTD, icon))

    def send(self, packetId, payload):
        if self.sock is None:
            return
        body = writeVarint(packetId) + bytes(payload)
        self.outbuf.extend(writeVarint(len(body)) + body)
        self.packetsOut += 1

    def flush(self):
        if self.sock is None or not self.outbuf:
            return
        while self.outbuf:
            try:
                sent = self.sock.send(bytes(self.outbuf[:65536]))
            except BlockingIOError:
                return
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                self.closeClient("send error %s" % exc)
                return
            if sent <= 0:
                return
            del self.outbuf[:sent]
