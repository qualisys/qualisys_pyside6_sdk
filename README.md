# Qualisys PySide6 SDK

[![PyPI](https://img.shields.io/pypi/v/qtm-rt-pyside6)](https://pypi.org/project/qtm-rt-pyside6/)

PySide6-based SDK for the Qualisys Real-Time (RT) protocol. Stream motion capture data from QTM using Qt's native networking and signals/slots.

## Installation

Requires Python 3.10+ and PySide6 6.5+.

We recommend using a virtual environment to avoid conflicts with other packages:

```bash
# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Then install the package:

```bash
pip install "qtm-rt-pyside6[scene]"
```

The `scene` extra adds Qt Quick 3D (PySide6-Addons) for the [3D scene helpers](#3d-scene).
For the connection, discovery and parameters alone, `pip install qtm-rt-pyside6`
is enough: it needs only PySide6-Essentials (QtCore, QtGui, QtNetwork, QtQml,
QtQuick, QtQuickControls2, QtWidgets). Apps that use other Qt modules, such as
WebEngine or Charts, install `PySide6` (or `PySide6-Addons`) themselves.

## Quick Start

```python
import sys
from PySide6.QtCore import QCoreApplication
from qtm_rt_pyside6 import QTMConnection, QRTPacket


def on_packet(packet: QRTPacket):
    print(f"Frame {packet.framenumber}")
    result = packet.get_3d_markers()
    if result:
        header, markers = result
        for marker in markers:
            print(f"  {marker.x}, {marker.y}, {marker.z}")


app = QCoreApplication(sys.argv)

connection = QTMConnection()
connection.connected.connect(lambda: connection.streamFrames(["3d"]))
connection.packetReceived.connect(on_packet)
connection.error.connect(lambda msg: print(f"Error: {msg}"))
connection.connectToHost("127.0.0.1")

sys.exit(app.exec())
```

## API

### QTMConnection Signals

| Signal | Description |
|--------|-------------|
| `connected()` | Successfully connected and version negotiated |
| `disconnected()` | Disconnected from QTM |
| `error(str)` | Connection or protocol error |
| `packetReceived(QRTPacket)` | Data packet during streaming |
| `eventReceived(QRTEvent)` | QTM event (capture started, etc.) |
| `responseReceived(str, object)` | Command response (command_name, data) |

### QTMConnection Methods

Core methods to get started:

- `connectToHost(host, port=22223, version="1.25", timeout_ms=5000)` — Connect to QTM
- `disconnectFromHost()` — Close the connection
- `streamFrames(components, frames="allframes", udp_port=None, udp_address=None)` — Start streaming; pass `udp_port` to receive frames over UDP instead of TCP
- `streamFramesStop()` — Stop streaming
- `getParameters(parameters)` — Request current configuration as XML

See the class docstring or run `help(QTMConnection)` for the full method
list — control, load/save, trigger, LED, quit, XML settings, etc.

### Components

Valid streaming components: `2d`, `2dlin`, `3d`, `3dres`, `3dnolabels`, `3dnolabelsres`, `analog`, `analogsingle`, `force`, `forcesingle`, `6d`, `6dres`, `6deuler`, `6deulerres`, `gazevector`, `eyetracker`, `image`, `timecode`, `skeleton`, `skeleton:global`

## 3D scene

`qtm_rt_pyside6.scene` turns a connection into a 3D scene: QTM's labeled and
unlabeled markers, its bones, rigid bodies and solved skeletons. A small app:

```python
import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from qtm_rt_pyside6 import QTMConnection
from qtm_rt_pyside6.scene import QtmScene, apply_theme
from qtm_rt_pyside6.scene.quick3d import setup_engine

app = QGuiApplication(sys.argv)
apply_theme(app)
connection = QTMConnection()
scene = QtmScene(connection)
engine = QQmlApplicationEngine()
setup_engine(engine)
engine.rootContext().setContextProperty("qtmScene", scene)
engine.loadData(b"""
import QtQuick
import Qualisys.Scene
Window { width: 1280; height: 800; visible: true; QtmView { anchors.fill: parent; scene: qtmScene } }
""")
connection.connectToHost("127.0.0.1")
sys.exit(app.exec())
```

- **`QtmScene(connection)`** asks QTM for its 3D, 6D and skeleton parameters,
  streams `3d`, `3dnolabels`, `6d` and `skeleton:global`, and asks again after
  QTM events (capture or file playback started, calibration) or when the stream
  no longer matches the parameters. The latest frame wins and is published at
  60 Hz (`frameChanged`); `frameReceived(frame)` fires for every frame, for app
  logic that must not miss one. `pick()`, `bounds()` and `highlight()` serve
  the views; `DemoSource(scene)` feeds simulated data when no QTM is at hand.
- **`SceneFrame`** decodes a packet on first use: `labeled`, `unlabeled`,
  `rigid_bodies`, `joints` (named `"<skeleton>:<segment>"`), `skeleton_bones`,
  `user_bones` and `position(name)`, all in QTM coordinates (mm).
  `frame.mapping` converts to Qt Quick 3D's Y-up scene, honouring QTM's
  `AxisUpwards`; for Z up that is `(x, y, z) -> (x, z, -y)`.
- **`import Qualisys.Scene`** (QML) gives `QtmView`, a ready-made view with QTM's
  mouse (left-drag orbits, right-drag pans, wheel zooms), picking, labels, floor,
  grid, axes and layer switches, and its parts for custom views:
  `QtmCameraController`, `MarkerLayer`, `BoneLayer`, `SkeletonLayer`,
  `RigidBodyLayer`, `LabelOverlay`, `Floor` and `QtmAxes`.
- **Skeletons** are drawn with *keeled* bones by default: octahedral bones with
  one sharp, light ridge that marks each segment's forward axis, so a bone's
  twist is visible. Left bones are blue, right gold. `QtmView.boneStyle` also
  takes `"octahedral"`, `"capsule"` and `"stick"`; `axesMode` adds local-axis
  tripods (`"selected"` or `"all"`).
- **Look**: the `QtmTheme` singleton holds the colors and fonts (neutral dark
  grays, Montserrat and Open Sans, one red accent); every token can be
  overridden. `QtmButton`, `QtmSwitch` and `QtmSection` match it, and
  `apply_theme(app)` sets up Fusion with a matching palette. The fonts are used
  when installed, or from a folder passed to `load_fonts()`.

The data layer (`qtm_rt_pyside6.scene`) needs only PySide6-Essentials;
`qtm_rt_pyside6.scene.quick3d` needs the `scene` extra and says so if it is missing.

**Render thread.** Qt Quick 3D calls the instance tables' `getInstanceBuffer()`
from its render thread, which then needs Python's GIL. A Python call that blocks
the GUI thread until the render thread is done deadlocks: `QTest.qWait()` and
`QQuickWindow.grabWindow()` do. Use `app.exec()`, `processEvents()`, pytest-qt's
`qtbot.wait()` / `waitSignal()` and the asynchronous `QQuickItem.grabToImage()`,
or set `QSG_RENDER_LOOP=basic` to render on the GUI thread.

**PyInstaller** picks up the `Qualisys.Scene` QML files through the package's
hook (`pyinstaller40` entry point); no extra `--add-data` is needed.

## Examples

Ready-to-run scripts live in [examples/](examples/) — see
[examples/README.md](examples/README.md) for what each one demonstrates
and how to run it. `basic_example.py` is the shortest path to verify
your setup; the GUI examples (`gui_example.py` and `gui_3d_example/`)
show how to wire the SDK into a desktop application, and `scene_minimal.py`
is the 3D scene above as a script (`--demo` runs it without QTM).

## Known Limitations

- **No automatic reconnection.** If the connection drops, you must call `connectToHost()` again. Listen to the `disconnected` signal to detect this.
- **Single-threaded.** `QTMConnection` and `QTMDiscovery` are `QObject` subclasses and must be used from the thread that created them (typically the main thread). Use Qt signals for cross-thread communication.
- **PySide6 below 6.12 on Python 3.10 and 3.11 (except on Windows).** PySide6 6.12.0's Linux wheels are built for Python 3.12 but install on 3.10 and 3.11, where apps abort with `free(): invalid pointer` ([PYSIDE-3474](https://qt-project.atlassian.net/browse/PYSIDE-3474)). The package therefore keeps PySide6 below 6.12 there; macOS is untested, so it is included. Use Python 3.12 or later for the latest PySide6.
- **Password sent in plain text.** `takeControl(password)` transmits the password unencrypted over TCP. This is a QTM protocol limitation — use on trusted networks only.

## Development

To work on the SDK itself:

```bash
git clone https://github.com/qualisys/qualisys_pyside6_sdk.git
cd qualisys_pyside6_sdk

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install dev dependencies (pytest, pytest-qt, ruff, build) and the package
pip install -r requirements-dev.txt
pip install -e ".[scene]"
```

Tests that need Qt Quick 3D are skipped without the `scene` extra, and the
render tests are skipped where Qt Quick 3D cannot render (no GPU or software GL).

Run tests and linting:
```bash
pytest -v
ruff check .
ruff format --check .
```

## License

MIT — see [LICENSE](LICENSE) and [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES).
