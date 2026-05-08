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
pip install -e .

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

Version is derived from git tags via `setuptools-scm`. Tag a release with `v0.1.0` format.

## Architecture

### Module Structure

- **`qtm_rt`** - Original SDK installed from PyPI (`qtm-rt>=3.0.0`). We import `packet` and `receiver` for binary parsing
- **`qtm_rt_pyside6/connection.py`** - `QTMConnection(QObject)` main class using `QTcpSocket`
- **`qtm_rt_pyside6/discovery.py`** - `QTMDiscovery(QObject)` for UDP broadcast discovery

### Signal Pattern

The SDK uses Qt signals instead of async/await:

```python
# Connection state
connected = Signal()
disconnected = Signal()
error = Signal(str)

# Streaming (high-frequency)
packetReceived = Signal(object)   # QRTPacket
eventReceived = Signal(object)    # QRTEvent

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
