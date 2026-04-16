# Qualisys PySide6 SDK

PySide6-based SDK for the Qualisys Real-Time (RT) protocol. Stream motion capture data from QTM using Qt's native networking and signals/slots.

## Installation

Requires Python 3.10+ and PySide6 6.0+.

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
pip install qtm-rt-pyside6
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
connection.error.connect(lambda msg: print(f"Error: {msg}"))
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

## Examples

The [examples/](examples/) directory contains ready-to-run scripts (requires QTM running):

- **basic_example.py** - Stream 3D markers to console
- **discovery_example.py** - Find QTM on the network
- **parameters_example.py** - Get QTM configuration as XML
- **gui_example.py** - Qt Widgets GUI with data table
- **gui_3d_example/** - Qt Quick 3D visualization with orbit camera

## Known Limitations

- **No automatic reconnection.** If the connection drops, you must call `connectToHost()` again. Listen to the `disconnected` signal to detect this.
- **Single-threaded.** `QTMConnection` and `QTMDiscovery` are `QObject` subclasses and must be used from the thread that created them (typically the main thread). Use Qt signals for cross-thread communication.
- **Password sent in plain text.** `takeControl(password)` transmits the password unencrypted over TCP. This is a QTM protocol limitation — use on trusted networks only.

## Development

To work on the SDK itself:

```bash
git clone --recursive https://github.com/qualisys/qualisys_pyside6_sdk.git
cd qualisys_pyside6_sdk

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
pip install -e .
```

If you cloned without `--recursive`:
```bash
git submodule update --init
```

Run tests and linting:
```bash
pytest -v
ruff check .
ruff format --check .
```

## License

MIT — see [LICENSE](LICENSE) and [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES).
