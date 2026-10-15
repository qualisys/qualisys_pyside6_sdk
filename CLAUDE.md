# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PySide6-based SDK for QTM Real-Time Protocol. Uses Qt's network stack (`QTcpSocket`, `QUdpSocket`) and signals/slots pattern instead of asyncio. Reuses packet parsing code from the original `qtm-rt` SDK, pulled in as a pip dependency (`qtm-rt>=3.0.0`).

## Development Commands

```bash
# Setup environment (use Python 3.10+)
py -3.10 -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements-dev.txt
pip install -e ".[scene]"   # the scene extra adds PySide6-Addons (Qt Quick 3D)

# Run all tests
pytest -v

# Run a single test file or test
pytest tests/test_connection.py -v
pytest tests/test_connection.py::TestQTMConnectionInit::test_creates_socket -v

# Run examples (requires QTM running)
python examples/basic_example.py
python examples/discovery_example.py
```

```bash
# Lint and format
ruff check .
ruff format --check .
ruff format .          # auto-fix formatting
```

Tests use `pytest-qt` (configured in `pyproject.toml` with `qt_api = pyside6`). Use `qtbot.waitSignal()` for signal assertions.

Never call `QTest.qWait()` or `QQuickWindow.grabWindow()` from Python while a Qt Quick 3D scene with the
scene helpers is showing: Qt calls the instance tables' `getInstanceBuffer()` override from its render thread,
which needs the GIL, while those calls block the GUI thread holding it - a deadlock. Use `qtbot.wait()`,
`qtbot.waitSignal()` and `QQuickItem.grabToImage()`, or set `QSG_RENDER_LOOP=basic`.

Version is derived from git tags via `setuptools-scm`. Tag a release with `v0.1.0` format.

## Architecture

### Module Structure

- **`qtm_rt`** - Original SDK installed from PyPI (`qtm-rt>=3.0.0`). We import `packet` and `receiver` for binary parsing
- **`qtm_rt_pyside6/connection.py`** - `QTMConnection(QObject)` main class using `QTcpSocket`
- **`qtm_rt_pyside6/discovery.py`** - `QTMDiscovery(QObject)` for UDP broadcast discovery
- **`qtm_rt_pyside6/scene/`** - 3D scene data layer, QtCore / QtGui only (PySide6-Essentials). Not imported by `qtm_rt_pyside6/__init__.py`.
  - `parameters.py` - parameter XML -> `SceneParameters` (labels, colors, user bones, AxisUpwards, 6D bodies, skeleton hierarchy). QTM colors are `0x00BBGGRR`.
  - `frame.py` - `SceneFrame`: lazily decoded packet (labeled / unlabeled markers, 6D with a column-major 3x3 matrix, `skeleton:global` quaternions); joints are `"<skeleton>:<segment>"`
  - `skeleton.py` - joints and keeled bones `(start, end, keel, side)`; `math3d.py` - `AxisMapping` QTM -> Y-up scene (a proper rotation; Z up is `(x, z, -y)`)
  - `scene.py` - `QtmScene(QObject)`: attaches to a `QTMConnection`, requests parameters, streams, latest frame published at 60 Hz, `pick()` / `bounds()` / `highlight()`; `demo.py` - `DemoSource`
  - `theme.py` - `dark_palette()`, `apply_theme()`, `load_fonts()`. Qt Quick Controls ignore the application palette (they start from their style's; Fusion's is the platform's), so QML windows set `palette: QtmTheme.palette`, which mirrors `dark_palette()` (tested)
- **`qtm_rt_pyside6/scene/quick3d/`** - needs PySide6-Addons (`[scene]` extra). Qt Quick 3D is GPLv3 / commercial, not LGPL, so keep it out of the core and the data layer: `KeelBoneGeometry`, `GridGeometry` and the `QQuick3DInstancing` subclasses, registered as QML `Qualisys.Scene.Native`; `setup_engine(engine)` registers them and adds the import path
- **`qtm_rt_pyside6/scene/qml/Qualisys/Scene/`** - the `Qualisys.Scene` QML module (package data): `QtmView`, `QtmCameraController`, the layers, `LabelOverlay`, `QtmTheme` singleton, `QtmButton` / `QtmSwitch` / `QtmSection`
- **`qtm_rt_pyside6/__pyinstaller/`** - PyInstaller hook (`pyinstaller40` entry point) that bundles the QML module

### Signal Pattern

The SDK uses Qt signals instead of async/await:

```python
# Connection state
connected = Signal()
disconnected = Signal()
error = Signal(str)

# Streaming (high-frequency)
packetReceived = Signal(object)  # QRTPacket
eventReceived = Signal(object)  # QRTEvent

# Request/response (generic)
responseReceived = Signal(str, object)  # (command_name, data)
```

### Response Handling

Commands that expect responses emit via `responseReceived(command, data)`. Use the helper for cleaner code:

```python
connection.onResponse("getparameters", self.handle_parameters)
connection.getParameters(["3d"])
```

### Reused Components from `qtm-rt`

- `qtm_rt.packet` - `QRTPacket`, `QRTEvent`, all struct definitions and namedtuples
- `qtm_rt.receiver` - `Receiver` class for packet reassembly (called from `_onReadyRead`)

### Data Flow

1. `QTMConnection.connectToHost(host)` -> `QTcpSocket.connectToHost()`
2. Socket `connected` signal -> send version command -> emit `connected` signal
3. `streamFrames(components)` -> sends command to QTM
4. Socket `readyRead` -> `Receiver.data_received()` -> packet handlers -> emit `packetReceived`

### Protocol Defaults

- TCP port: 22223 (little-endian)
- UDP discovery port: 22226
- Protocol version: "1.25"
- Logger name: `"qtm_rt_pyside6"`

### Valid Identifiers

**Streaming components:** `2d`, `2dlin`, `3d`, `3dres`, `3dnolabels`, `3dnolabelsres`, `analog`, `analogsingle`, `force`, `forcesingle`, `6d`, `6dres`, `6deuler`, `6deulerres`, `gazevector`, `eyetracker`, `image`, `timecode`, `skeleton`, `skeleton:global`

**Parameter names for `getParameters()`:** `all`, `general`, `3d`, `6d`, `analog`, `force`, `gazevector`, `eyetracker`, `image`, `skeleton`, `skeleton:global`, `calibration`
