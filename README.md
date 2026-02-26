# Qualisys PySide6 SDK

PySide6-based SDK for the Qualisys Real-Time (RT) protocol. Stream motion capture data from QTM using Qt's native networking and signals/slots.

## Installation

```bash
git clone --recursive https://github.com/qualisys/qualisys_pyside6_sdk.git
cd qualisys_pyside6_sdk
pip install -e .
```

If you've already cloned without `--recursive`:
```bash
git submodule update --init
```

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
connection.connectToHost("127.0.0.1")

sys.exit(app.exec())
```

## Discovery

Find QTM instances on the network:

```python
from qtm_rt_pyside6 import QTMDiscovery

discovery = QTMDiscovery()
discovery.discovered.connect(lambda r: print(f"Found: {r.host}:{r.port}"))
discovery.start()
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

- `connectToHost(host, port=22223)` - Connect to QTM
- `disconnect()` - Disconnect
- `streamFrames(components, frames="allframes")` - Start streaming
- `streamFramesStop()` - Stop streaming
- `getParameters(parameters)` - Get XML configuration
- `getCurrentFrame(components)` - Get single frame
- `takeControl(password)` / `releaseControl()` - Control QTM
- `start()` / `stop()` - Start/stop measurement
- `load(filename)` / `save(filename)` - Load/save measurements
- `onResponse(command, callback)` - Register response callback

### Components

Valid streaming components: `2d`, `2dlin`, `3d`, `3dres`, `3dnolabels`, `3dnolabelsres`, `analog`, `analogsingle`, `force`, `forcesingle`, `6d`, `6dres`, `6deuler`, `6deulerres`, `gazevector`, `eyetracker`, `image`, `timecode`, `skeleton`, `skeleton:global`

## Examples

```bash
# Console examples
python examples/basic_example.py         # Stream 3D markers
python examples/discovery_example.py     # Find QTM on network
python examples/parameters_example.py    # Get QTM configuration

# GUI examples
python examples/gui_example.py           # Qt Widgets GUI with table view
python examples/gui_3d_example/main.py   # Qt Quick 3D visualization
```

### GUI Example
Qt Widgets application with connection controls, streaming toggle, and data table.

### 3D Viewer Example
Qt Quick 3D application showing markers as colored spheres in an interactive 3D scene with orbit camera controls.

## Requirements

- Python 3.10+
- PySide6 6.0+

## License

MIT
