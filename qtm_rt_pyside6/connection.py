"""QTM Connection using Qt network stack"""

import logging
import struct
from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket
from qtm_rt.packet import QRTEvent, QRTPacket, QRTPacketType, RTCommand, RTheader
from qtm_rt.receiver import Receiver

LOG = logging.getLogger("qtm_rt_pyside6")


class QTMConnection(QObject):
    """Connection to QTM using Qt's network stack.

    Signals:
        connected: Emitted when successfully connected and version negotiated
        disconnected: Emitted when disconnected from QTM
        error(str): Emitted on connection or protocol errors
        packetReceived(QRTPacket): Emitted for each data packet during streaming
        eventReceived(QRTEvent): Emitted for QTM events
        responseReceived(str, object): Emitted for command responses (command_name, data)

    Example:
        connection = QTMConnection()
        connection.connected.connect(on_connected)
        connection.packetReceived.connect(on_packet)
        connection.connectToHost("127.0.0.1")
    """

    # Connection state signals
    connected = Signal()
    disconnected = Signal()
    error = Signal(str)

    # Streaming signals
    packetReceived = Signal(object)  # QRTPacket
    eventReceived = Signal(object)  # QRTEvent

    # Command response signal (command_name, data)
    responseReceived = Signal(str, object)

    # Valid components for streaming
    VALID_COMPONENTS = {
        "2d",
        "2dlin",
        "3d",
        "3dres",
        "3dnolabels",
        "3dnolabelsres",
        "analog",
        "analogsingle",
        "force",
        "forcesingle",
        "6d",
        "6dres",
        "6deuler",
        "6deulerres",
        "gazevector",
        "eyetracker",
        "image",
        "timecode",
        "skeleton",
        "skeleton:global",
    }

    # Valid parameters for getParameters
    VALID_PARAMETERS = {
        "all",
        "general",
        "3d",
        "6d",
        "analog",
        "force",
        "gazevector",
        "eyetracker",
        "image",
        "skeleton",
        "skeleton:global",
        "calibration",
    }

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self._socket = QTcpSocket(self)
        self._socket.connected.connect(self._onSocketConnected)
        self._socket.disconnected.connect(self._onSocketDisconnected)
        self._socket.readyRead.connect(self._onReadyRead)
        self._socket.errorOccurred.connect(self._onSocketError)

        self._version = "1.25"
        self._command_queue: deque[str] = deque()
        self._streaming = False
        self._response_callbacks: dict[str, Callable] = {}

        # Packet handlers using the reusable Receiver from original SDK
        self._handlers = {
            QRTPacketType.PacketError: self._onError,
            QRTPacketType.PacketData: self._onData,
            QRTPacketType.PacketCommand: self._onCommand,
            QRTPacketType.PacketEvent: self._onEvent,
            QRTPacketType.PacketXML: self._onXml,
            QRTPacketType.PacketNoMoreData: self._onNoMoreData,
        }
        self._receiver = Receiver(self._handlers)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    @Slot(str, int)
    def connectToHost(self, host: str, port: int = 22223, version: str = "1.25"):
        """Connect to QTM at the specified host and port.

        Args:
            host: IP address or hostname of QTM
            port: Port number (default 22223 for little endian)
            version: Protocol version (default "1.25")
        """
        self._version = version
        self._socket.connectToHost(host, port)

    @Slot()
    def disconnect(self):
        """Disconnect from QTM."""
        self._socket.disconnectFromHost()

    def isConnected(self) -> bool:
        """Check if connected to QTM."""
        return self._socket.state() == QAbstractSocket.SocketState.ConnectedState

    @Slot()
    def getQtmVersion(self):
        """Request QTM version. Response via responseReceived("qtmversion", str)."""
        self._sendCommand("qtmversion")

    @Slot()
    def getByteOrder(self):
        """Request byte order. Response via responseReceived("byteorder", str)."""
        self._sendCommand("byteorder")

    @Slot()
    def getState(self):
        """Request current QTM state. Response via eventReceived(QRTEvent)."""
        self._sendCommand("getstate", expect_response=False)

    @Slot(list)
    def getParameters(self, parameters: list[str] | None = None):
        """Request QTM parameters in XML format.

        Args:
            parameters: List of parameter types. Valid values: 'all', 'general',
                '3d', '6d', 'analog', 'force', 'gazevector', 'eyetracker',
                'image', 'skeleton', 'skeleton:global', 'calibration'.
                Defaults to ['all'].

        Response via responseReceived("getparameters", xml_string).
        """
        if parameters is None:
            parameters = ["all"]
        else:
            for param in parameters:
                if param not in self.VALID_PARAMETERS:
                    self.error.emit(f"Invalid parameter: {param}")
                    return

        cmd = f"getparameters {' '.join(parameters)}"
        self._sendCommand(cmd)

    @Slot(list)
    def getCurrentFrame(self, components: list[str]):
        """Request a single frame of data.

        Args:
            components: List of component types to receive.

        Response via responseReceived("getcurrentframe", QRTPacket).
        """
        if not self._validateComponents(components):
            return

        cmd = f"getcurrentframe {' '.join(components)}"
        self._sendCommand(cmd)

    @Slot(str, list)
    def streamFrames(self, components: list[str], frames: str = "allframes"):
        """Start streaming frames from QTM.

        Args:
            components: List of component types to stream. Valid values:
                '2d', '2dlin', '3d', '3dres', '3dnolabels', '3dnolabelsres',
                'analog', 'analogsingle', 'force', 'forcesingle',
                '6d', '6dres', '6deuler', '6deulerres',
                'gazevector', 'eyetracker', 'image', 'timecode',
                'skeleton', 'skeleton:global'
            frames: Frame selection - 'allframes', 'frequency:N', or 'frequencydivisor:N'

        Packets arrive via packetReceived(QRTPacket) signal.
        """
        if not self._validateComponents(components):
            return

        self._streaming = True
        cmd = f"streamframes {frames} {' '.join(components)}"
        self._sendCommand(cmd)

    @Slot()
    def streamFramesStop(self):
        """Stop streaming frames."""
        self._streaming = False
        self._sendCommand("streamframes stop", expect_response=False)

    @Slot(str)
    def takeControl(self, password: str):
        """Take control of QTM.

        Args:
            password: Password as configured in QTM.

        Response via responseReceived("takecontrol", bytes).
        """
        self._sendCommand(f"takecontrol {password}")

    @Slot()
    def releaseControl(self):
        """Release control of QTM.

        Response via responseReceived("releasecontrol", bytes).
        """
        self._sendCommand("releasecontrol")

    @Slot()
    def newMeasurement(self):
        """Create a new measurement. Requires control.

        Response via responseReceived("new", bytes).
        """
        self._sendCommand("new")

    @Slot()
    def closeMeasurement(self):
        """Close current measurement.

        Response via responseReceived("close", bytes).
        """
        self._sendCommand("close")

    @Slot(bool)
    def start(self, rtFromFile: bool = False):
        """Start measurement or RT from file. Requires control.

        Args:
            rtFromFile: If True, start RT from file instead of live capture.

        Response via responseReceived("start", bytes).
        """
        cmd = "start" + (" rtfromfile" if rtFromFile else "")
        self._sendCommand(cmd)

    @Slot()
    def stop(self):
        """Stop measurement or RT from file.

        Response via responseReceived("stop", bytes).
        """
        self._sendCommand("stop")

    @Slot(str)
    def load(self, filename: str):
        """Load a measurement file.

        Args:
            filename: Path to measurement file.

        Response via responseReceived("load", bytes).
        """
        self._sendCommand(f"load {filename}")

    @Slot(str, bool)
    def save(self, filename: str, overwrite: bool = False):
        """Save current measurement.

        Args:
            filename: Filename to save as.
            overwrite: Whether to overwrite existing file.

        Response via responseReceived("save", bytes).
        """
        cmd = f"save {filename}" + (" overwrite" if overwrite else "")
        self._sendCommand(cmd)

    @Slot(str)
    def loadProject(self, projectPath: str):
        """Load a QTM project.

        Args:
            projectPath: Path to project.

        Response via responseReceived("loadproject", bytes).
        """
        self._sendCommand(f"loadproject {projectPath}")

    @Slot()
    def trig(self):
        """Trigger QTM (for software/wireless trigger mode).

        Response via responseReceived("trig", bytes).
        """
        self._sendCommand("trig")

    @Slot(str)
    def setQtmEvent(self, event: str | None = None):
        """Set an event in QTM.

        Args:
            event: Optional event label.

        Response via responseReceived("event", bytes).
        """
        cmd = "event" + (f" {event}" if event else "")
        self._sendCommand(cmd)

    @Slot(str)
    def sendXml(self, xml: str):
        """Send XML settings to QTM.

        Args:
            xml: XML document string.

        Response via responseReceived("xml", bytes).
        """
        self._sendCommand(xml, command_type=QRTPacketType.PacketXML)

    @Slot()
    def calibrate(self):
        """Start calibration. Response comes via responseReceived("calibrate", xml).

        Note: Calibration can take several minutes. The response will arrive
        when calibration completes.
        """
        self._sendCommand("calibrate")

    def onResponse(self, command: str, callback: Callable):
        """Register a callback for a specific command response.

        This is a convenience method for cleaner code when you only care
        about specific command responses.

        Args:
            command: Command name (e.g., "getparameters", "qtmversion")
            callback: Function to call with the response data

        Example:
            connection.onResponse("getparameters", self.handleParameters)
            connection.getParameters(["3d"])
        """
        self._response_callbacks[command.lower()] = callback

    def removeResponseCallback(self, command: str):
        """Remove a response callback."""
        self._response_callbacks.pop(command.lower(), None)

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _validateComponents(self, components: list[str]) -> bool:
        """Validate component list."""
        for comp in components:
            if comp.lower() not in self.VALID_COMPONENTS:
                self.error.emit(f"Invalid component: {comp}")
                return False
        return True

    def _sendCommand(
        self, command: str, expect_response: bool = True, command_type: QRTPacketType = QRTPacketType.PacketCommand
    ):
        """Send a command to QTM."""
        if not self.isConnected():
            self.error.emit("Not connected")
            return

        cmd_bytes = command.encode()
        cmd_length = len(cmd_bytes)

        packet = struct.pack(
            RTCommand % cmd_length,
            RTheader.size + cmd_length + 1,
            command_type.value,
            cmd_bytes,
            b"\0",
        )

        if expect_response:
            # Queue command name for matching response
            self._command_queue.append(command.split()[0].lower())

        LOG.debug("Sending: %s", command)
        self._socket.write(packet)

    def _emitResponse(self, command: str, data):
        """Emit response via signal and/or callback."""
        self.responseReceived.emit(command, data)

        callback = self._response_callbacks.get(command)
        if callback:
            callback(data)

    # -------------------------------------------------------------------------
    # Socket event handlers
    # -------------------------------------------------------------------------

    def _onSocketConnected(self):
        """Handle socket connected - negotiate protocol version."""
        LOG.info("Socket connected, negotiating version %s", self._version)
        self._command_queue.append("version")
        self._sendCommand(f"version {self._version}")

    def _onSocketDisconnected(self):
        """Handle socket disconnected."""
        LOG.info("Disconnected")
        self._streaming = False
        self._command_queue.clear()
        self._response_callbacks.clear()
        self._receiver = Receiver(self._handlers)
        self.disconnected.emit()

    def _onSocketError(self, error: QAbstractSocket.SocketError):
        """Handle socket error."""
        error_string = self._socket.errorString()
        LOG.error("Socket error: %s", error_string)
        self.error.emit(error_string)

    def _onReadyRead(self):
        """Handle incoming data."""
        data = self._socket.readAll().data()
        self._receiver.data_received(data)

    # -------------------------------------------------------------------------
    # Packet handlers (called by Receiver)
    # -------------------------------------------------------------------------

    def _onData(self, packet: QRTPacket):
        """Handle data packet."""
        if self._streaming:
            self.packetReceived.emit(packet)
        else:
            # Single frame request response
            if self._command_queue:
                cmd = self._command_queue.popleft()
                self._emitResponse(cmd, packet)

    def _onNoMoreData(self, data):
        """Handle no more data packet (end of file during RT from file)."""
        LOG.debug("No more data")

    def _onEvent(self, event: QRTEvent):
        """Handle event packet."""
        LOG.info("Event: %s", event)
        self.eventReceived.emit(event)

    def _onError(self, response: bytes):
        """Handle error packet."""
        error_msg = response.decode("utf-8", errors="replace")
        LOG.error("QTM error: %s", error_msg)
        self._streaming = False
        # Discard the command that caused the error
        if self._command_queue:
            self._command_queue.popleft()
        self.error.emit(error_msg)

    def _onXml(self, response: bytes):
        """Handle XML response."""
        xml_str = response.decode("utf-8", errors="replace")
        LOG.debug("XML response: %s...", xml_str[:70])

        if self._command_queue:
            cmd = self._command_queue.popleft()
            self._emitResponse(cmd, xml_str)

    def _onCommand(self, response: bytes):
        """Handle command response."""
        response_str = response.decode("utf-8", errors="replace")
        LOG.debug("Response: %s", response_str)

        # Skip initial connection message
        if response_str == "QTM RT Interface connected":
            return

        # Handle version negotiation
        if self._command_queue and self._command_queue[0] == "version":
            self._command_queue.popleft()
            if response_str.startswith("Version set to"):
                LOG.info("Connected with protocol %s", self._version)
                self.connected.emit()
            else:
                self.error.emit(f"Version negotiation failed: {response_str}")
            return

        if self._command_queue:
            cmd = self._command_queue.popleft()
            self._emitResponse(cmd, response)
