# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PySide6-based SDK for QTM Real-Time Protocol. Uses Qt's network stack (`QTcpSocket`, `QUdpSocket`) and signals/slots pattern instead of asyncio. Reuses packet parsing code from the original `qtm-rt` SDK via git submodule.

## Development Commands

```bash
# Setup environment (use Python 3.10+)
py -3.10 -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements-dev.txt
pip install -e .

# Initialize submodule (required after clone)
git submodule update --init

# Run tests
pytest -v

# Run examples (requires QTM running)
python examples/basic_example.py
python examples/discovery_example.py
```

## Architecture

### Module Structure

- **`qtm_rt/`** - Git submodule of original SDK. We import `packet.py` and `receiver.py` for binary parsing
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

### Reused Components from Submodule

- `qtm_rt.packet` - `QRTPacket`, `QRTEvent`, all struct definitions and namedtuples
- `qtm_rt.receiver` - `Receiver` class for packet reassembly (called from `_onReadyRead`)

### Data Flow

1. `QTMConnection.connectToHost(host)` → `QTcpSocket.connectToHost()`
2. Socket `connected` signal → send version command → emit `connected` signal
3. `streamFrames(components)` → sends command to QTM
4. Socket `readyRead` → `Receiver.data_received()` → packet handlers → emit `packetReceived`
