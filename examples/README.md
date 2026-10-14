# Examples

Ready-to-run scripts demonstrating `qtm-rt-pyside6`. Each example is
self-contained — install the package, start QTM, and run.

## Prerequisites

- A QTM installation reachable on the network (or `127.0.0.1` if local).
- `qtm-rt-pyside6` installed (`pip install qtm-rt-pyside6`, or
  `pip install -e .` from a checkout). The 3D examples need the `scene`
  extra: `pip install "qtm-rt-pyside6[scene]"` (or `pip install -e ".[scene]"`).
- For the streaming examples, QTM should be playing back data — load a
  file in QTM and choose **Play → Play with Real-Time output**, or run
  a live capture.
- The 3D and Widgets GUI examples need a display; the rest run in a
  plain console.

## Quick reference

| Script | What it shows | Run |
|---|---|---|
| [`basic_example.py`](basic_example.py) | Stream 3D markers to the console, exit cleanly after 100 frames | `python basic_example.py` |
| [`discovery_example.py`](discovery_example.py) | UDP-broadcast discovery of QTM instances on the network | `python discovery_example.py [interface_ip]` |
| [`parameters_example.py`](parameters_example.py) | Request QTM configuration as XML and parse 3D markers, 6DOF bodies, and skeletons out of it | `python parameters_example.py` |
| [`gui_example.py`](gui_example.py) | Qt Widgets app combining discovery, connect/disconnect, and a live data table with frame rate | `python gui_example.py` |
| [`scene_minimal.py`](scene_minimal.py) | The smallest 3D viewer: `QtmScene` + `QtmView` in a window | `python scene_minimal.py [host]` or `--demo` |
| [`gui_3d_example/main.py`](gui_3d_example/main.py) | 3D viewer on the scene helpers: markers, bones, rigid bodies and keeled skeletons, a panel listing QTM's definitions, highlighting | `python gui_3d_example/main.py` (`--demo` without QTM) |

If you're new to the SDK, start with `basic_example.py` to confirm the
connection works, then look at `discovery_example.py` or one of the GUI
examples depending on what you're building.

## Notes on individual examples

### `basic_example.py`
Minimal connect-and-stream loop. Exits automatically after 100 frames
(`FRAME_LIMIT`) so it's safe to run unattended.

### `discovery_example.py`
Sends a UDP broadcast on port 22226 and prints every QTM instance that
replies within the 2-second timeout.

On machines with multiple network interfaces, the broadcast may not
reach the QTM subnet when bound to "any" interface. Pass the local
interface IP as the first argument to bind explicitly:

```
python discovery_example.py 192.168.10.100
```

### `parameters_example.py`
Connects, requests `3d`, `6d`, and `skeleton` parameters, parses the
returned XML, and prints marker / body / skeleton names. Useful as a
template for any "fetch and inspect QTM configuration" task.

### `gui_example.py`
PySide6 / QtWidgets app with discovery, connection management, and a
live data table. A good starting point for desktop tools built on top
of the SDK.

### `scene_minimal.py`
About 15 lines of app around the 3D scene helpers: a `QtmScene` follows
the connection (parameters, streaming, refreshes) and the `QtmView` QML
type draws it with QTM's mouse controls. `--demo` feeds simulated data
instead of connecting.

### `gui_3d_example/`
A fuller 3D viewer on the same helpers. `main.py` adds host discovery,
connect / disconnect and demo data around a `QtmScene`; `main.qml` puts a
panel of QTM's markers (grouped by name prefix), skeletons and rigid
bodies next to a `QtmView`. Clicking a name or a point highlights it; the
panel also switches the bone style, local axes and labels. The look comes
from the `QtmTheme` singleton; drop Montserrat / Open Sans font files into
a `fonts` folder next to the script to use them without installing them.

## Known limitation: TCP streaming only in these examples

All streaming examples use TCP (the default). The SDK also supports
UDP streaming via `streamFrames(..., udp_port=...)` — see the
`QTMConnection` docstring or `help(QTMConnection)` for details. None
of the bundled examples currently demonstrate UDP; contributions
welcome.
