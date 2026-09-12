# Minecraft server in Blender

A working Minecraft 1.8.9 server implemented entirely in Blender. Real client with a real protocol and no server software. The process listening on port 25565 is Blender.

Version two. The first one rendered the world. This one uses Blender's timeline, its smoke solver and Cycles to push things back the other way, into a client from 2015 that has no business displaying them. A volcano whose plume is a real fluid simulation. A path traced render of your own point of view, on a map item in your hand. A 39 block creeper that walks across the world and detonates.

## Why

The first Blender build used none of Blender. Now, it does.

## What it does

Everything the first build did:

- Server list ping with MOTD, player count and a favicon
- Offline mode login, no encryption
- Creative mode, so you can fly and place things
- Keep-alives
- The world as real geometry, a player object that tracks your position, the scene camera driven by your yaw and pitch at eye height (not perfected)
- Blocks you place appear as objects
- Start and Stop in the 3D viewport sidebar, with live position, packet counts and the outbound queue draining

New in this one:

- A 7x7 chunk world, 80 blocks high, with a server-side block store, so breaking terrain works
- **The volcano.** A Mantaflow gas domain sits over the crater. Every second frame the density and flame grids are sampled, quantised to wool, fire and air and sent as Multi Block Change. Lava runs down the cone in four channels. Lava bombs leave the crater on a ballistic arc and land where they land
- **The map.** You spawn holding one. `!map` renders your point of view in Cycles at 128x128, matches every pixel to the 1.8 map palette.
- **The kaiju.** `!kaiju` spawns a creeper at the far corner and it walks at you. Six boxes with a walk cycle, revoxelised every frame, about 4,300 blocks. Anything it steps through gets a velocity and becomes debris. Break 40 of its blocks and it hisses, flashes white and explodes leaving a crater
- Chat commands with matching buttons on the panel: `!erupt` `!kaiju` `!map` `!boom` `!reset`

## What it doesn't do

No (real) mobs, no second player, no survival, no chat between players. The kaiju isn't an entity, it is blocks.

The terrain in Blender is still one mesh. Break a block and it goes from the game and from the server's store, but the Blender slab doesn't lose a face.

## Requirements

Blender 4.x or later. Minecraft Java 1.8.9, protocol 47.

Nothing to install. Blender ships CPython, numpy and Mantaflow.

## Layout

The single file is no longer. The code is a package.

```
run.py
mcblender/
  constants.py
  protocol.py
  packets.py
  world.py
  geometry.py
  volcano.py
  kaiju.py
  scene.py
  server.py
  runtime.py
  ui.py
```

`protocol` is varints, strings and position encoding. `packets` builds payloads and holds the map palette. `world` is the block store, the debris integrator and the display diffing. `geometry` is matrices and the voxeliser. `volcano` and `kaiju` are the two set pieces. `scene` builds the Blender side, samples the smoke and drives playback. `server` is the socket loop and the packet handlers. `runtime` is the timer, the frame handler, start and stop. `ui` is the operators and the panel.

`scene.py` is the only module that imports `bpy`. Everything else imports fine outside Blender, so the simulation, the protocol and the voxeliser can all be tested headlessly.

## Setup

**1. Save the .blend first.** The script looks for `favicon.png` next to the .blend file, and an unsaved file has no path.

**2. Launch Blender from a terminal** if you want to see the output.

On Windows, Blender has one built in: Window > Toggle System Console. A console window appears alongside Blender showing everything the script prints. Toggle it again to hide it.

On macOS:

```
/Applications/Blender.app/Contents/MacOS/Blender
```

Without this you get no connection log and no error output.

**3. Scripting workspace.** Click **Open** in the text editor header and pick `run.py` from disk, then **Run Script** or Alt+P. Pasting still works, but only if the .blend sits in the same folder as the `mcblender` package, because that's how the launcher finds it.

If you have the old single-file version in this .blend, delete that text block. It'll bind the same port.

**4. Open the sidebar.** Press **N** in the 3D viewport, then the **MC Server** tab. Start and Stop at the top, the five set piece buttons under them, live status below that.

**5. Press Numpad 0** for camera view. That camera is driven by your head.

**7. Connect** to `localhost:25565` in Minecraft 1.8.9 via Direct Connect.

Optional: a 64x64 PNG named `favicon.png` beside the .blend shows as the server icon in the multiplayer list. Must be exactly 64x64 or the client drops it.

Optional but worth it: Preferences > System > Cycles Render Devices, pick Metal or OptiX and tick your GPU. It's the difference between a map render taking a second and taking fifteen.

Re-running the script is safe it is how you pick up edits. It drops the cached package, reimports every module, stops the old server, releases the port and wipes the `MC_Server` collection. Press Start to bring the new code up. (There is probably a cleaner way but this worked.)

## How it works

Blender embeds CPython with the full standard library, so `import socket` gives you a TCP server in Blender's process.

`bpy` is not thread-safe. The socket runs on `bpy.app.timers` at a 20ms tick, doing one pass of accept, read, flush and keep-alive before returning. Blender stays fully responsive while it serves.

**VarInts.** The protocol's variable width integer format, used for every packet length and ID.

**Packet framing.** Length, then packet ID, then payload. TCP is a stream, so packets arrive split across reads or several at once.

**Chunks.** The reason this targets 1.8.9 and not a current version. In 1.8, a chunk section is a flat array of `(id << 4) | meta` shorts, then block light, then sky light. 12,544 bytes for one section plus biome data and you can send it uncompressed. Modern versions use palette-encoded, bit packed longs and expect zlib. The join sequence here is 49 chunks of five sections each, so about 3MB in one burst.

**The frame handler.** This is another new thing. `bpy.app.handlers.frame_change_post` fires once per frame during playback, after the depsgraph has evaluated, which is the only part the smoke grids hold this frame's values. The timer keeps doing the socket and flushes whatever the frame handler queued.

**Three layers and a diff.** Debris, kaiju and smoke are dicts of cell to block state, stacked in that order over the world. A display object holds what the client was last shown, diffs the composite against it, groups the changes by chunk and sends one `0x22` Multi Block Change each. Blocks that stop being covered revert to whatever the world says is underneath. Without the diff a kaiju walking at you is 4,300 block changes a frame instead of a few hundred.

**Smoke.** `density_grid` and `flame_grid` come back as flat float lists at the domain resolution. Cells are about 0.9 blocks, so several of them vote for one block and the strongest wins: flame becomes fire, dense smoke black wool, thinner smoke comes out grey then light grey.

**The map.** `0x34` Maps takes 128 columns of 128 rows of palette indices, which are base colour times four plus shade. The render goes to a temp PNG, because Blender won't hand you the Render Result buffer from Python, then comes back in, gets flipped and every pixel is matched to the nearest of the 144 palette entries with numpy.

**Voxelising.** Take a box's world space AABB, build a grid of cell centres, multiply by the inverse of the box matrix, keep the ones that land inside. Six body parts, 4,300 blocks, under 10ms a frame. The creeper face is a mask applied to the front layer of the head.

**Coordinates.** Minecraft is Y-up and Blender is Z-up, so a Minecraft position `(x, y, z)` becomes a Blender position `(x, z, y)`. Camera rotation is `(90 - pitch, 0, yaw)` in degrees, which lines Blender's default camera axis up with Minecraft's yaw. Everything is computed in Minecraft space and swapped on the way into an object matrix.

## Notes from the second pass

**The single file had to go.** The first version was one script of about 750 lines that... worked. This one was way more (closer to 1600) and is now more easily manageable and editable.

**Reimporting a package from the text editor.** Python caches modules, so editing `kaiju.py` and pressing Run Script gets you the old kaiju. The launcher drops every `mcblender.*` key out of `sys.modules` before importing, so a rerun is just a rerun.

**The frame handler is re-entrant if you let it.** Rendering the map advances nothing, but it does pump events, and a slow frame can overlap the next one. There's a guard flag. Without it you get two simulation steps for one frame and the kaiju walks at double speed while it renders.

## Licence

MIT. Do what you like with it.
