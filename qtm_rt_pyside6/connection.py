"""QTM Connection using Qt network stack"""

import logging
import struct
from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QTcpSocket, QUdpSocket
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

    # Valid LED modes and colors
    VALID_LED_MODES = {"on", "off", "pulsing"}
    VALID_LED_COLORS = {"green", "amber", "all"}

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

    def __init__(self, parent: QObject | None = None) -> None:
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

        # UDP receive socket, created lazily when streamFrames is called with
        # a udp_port. Data packets arriving via UDP are fed into a separate
        # Receiver that shares the TCP packet handlers, so downstream consumers
        # see the same signals regardless of transport.
        self._udp_socket: QUdpSocket | None = None
        self._udp_receiver: Receiver | None = None

        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._onConnectTimeout)

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
    def connectToHost(self, host: str, port: int = 22223, version: str = "1.25", timeout_ms: int = 5000) -> None:
        """Connect to QTM at the specified host and port.

        Args:
            host: IP address or hostname of QTM
            port: Port number (default 22223 for little endian)
            version: Protocol version (default "1.25")
            timeout_ms: Connection timeout in milliseconds (default 5000). Set to 0 to disable.
        """
        LOG.info("Connecting to %s:%d", host, port)
        self._version = version
        if timeout_ms > 0:
            self._connect_timer.start(timeout_ms)
        self._socket.connectToHost(host, port)

    @Slot()
    def disconnect(self) -> None:
        """Disconnect from QTM."""
        LOG.info("Disconnecting")
        self._socket.disconnectFromHost()

    def isConnected(self) -> bool:
        """Check if connected to QTM."""
        return self._socket.state() == QAbstractSocket.SocketState.ConnectedState

    @Slot()
    def getQtmVersion(self) -> None:
        """Request QTM version. Response via responseReceived("qtmversion", str)."""
        self._sendCommand("qtmversion")

    @Slot()
    def getByteOrder(self) -> None:
        """Request byte order. Response via responseReceived("byteorder", str)."""
        self._sendCommand("byteorder")

    @Slot()
    def getState(self) -> None:
        """Request current QTM state. Response via eventReceived(QRTEvent)."""
        self._sendCommand("getstate", expect_response=False)

    @Slot(list)
    def getParameters(self, parameters: list[str] | None = None) -> None:
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
    def getCurrentFrame(self, components: list[str]) -> None:
        """Request a single frame of data.

        Args:
            components: List of component types to receive.

        Response via responseReceived("getcurrentframe", QRTPacket).
        """
        if not self._validateComponents(components):
            return

        cmd = f"getcurrentframe {' '.join(components)}"
        self._sendCommand(cmd)

    @Slot(list, str)
    def streamFrames(
        self,
        components: list[str],
        frames: str = "allframes",
        udp_port: int | None = None,
        udp_address: str | None = None,
    ) -> None:
        """Start streaming frames from QTM.

        Args:
            components: List of component types to stream. Valid values:
                '2d', '2dlin', '3d', '3dres', '3dnolabels', '3dnolabelsres',
                'analog', 'analogsingle', 'force', 'forcesingle',
                '6d', '6dres', '6deuler', '6deulerres',
                'gazevector', 'eyetracker', 'image', 'timecode',
                'skeleton', 'skeleton:global'
                Components may include channel selection suffix, e.g.,
                'analog:1,3,5-8' or 'analogsingle:2,4'.
            frames: Frame selection - 'allframes', 'frequency:N', or 'frequencydivisor:N'
            udp_port: Optional UDP port for UDP streaming (1023-65535). When
                set, a local UDP socket is bound on this port and QTM sends
                data packets to it instead of over the TCP connection.
            udp_address: Optional UDP address passed through to QTM. If omitted,
                QTM sends frames to the TCP client's source IP. Set this to
                redirect data to a different host — in that case no local UDP
                socket is bound and packetReceived will not fire locally.

        Packets arrive via packetReceived(QRTPacket) regardless of whether
        transport is TCP or UDP.
        """
        if not self._validateComponents(components):
            return

        # Set up local UDP receive socket if requested and no remote redirect.
        # If the caller redirects with udp_address, we don't bind locally —
        # the user has chosen to send frames to another host.
        if udp_port is not None and not udp_address and not self._setupUdpSocket(udp_port):
            return  # error already emitted

        self._streaming = True
        parts = ["streamframes"]
        if udp_port is not None:
            if udp_address:
                parts.append(f"udp:{udp_address}:{udp_port}")
            else:
                parts.append(f"udp:{udp_port}")
        parts.append(frames)
        parts.extend(components)
        self._sendCommand(" ".join(parts))

    @Slot()
    def streamFramesStop(self) -> None:
        """Stop streaming frames."""
        self._streaming = False
        self._sendCommand("streamframes stop", expect_response=False)
        self._teardownUdpSocket()

    @Slot(str)
    def takeControl(self, password: str) -> None:
        """Take control of QTM.

        Args:
            password: Password as configured in QTM.

        Response via responseReceived("takecontrol", bytes).
        """
        self._sendCommand(f"takecontrol {password}")

    @Slot()
    def releaseControl(self) -> None:
        """Release control of QTM.

        Response via responseReceived("releasecontrol", bytes).
        """
        self._sendCommand("releasecontrol")

    @Slot()
    def newMeasurement(self) -> None:
        """Create a new measurement. Requires control.

        Response via responseReceived("new", bytes).
        """
        self._sendCommand("new")

    @Slot()
    def closeMeasurement(self) -> None:
        """Close current measurement.

        Response via responseReceived("close", bytes).
        """
        self._sendCommand("close")

    @Slot(bool)
    def start(self, rtFromFile: bool = False) -> None:
        """Start measurement or RT from file. Requires control.

        Args:
            rtFromFile: If True, start RT from file instead of live capture.

        Response via responseReceived("start", bytes).
        """
        cmd = "start" + (" rtfromfile" if rtFromFile else "")
        self._sendCommand(cmd)

    @Slot()
    def stop(self) -> None:
        """Stop measurement or RT from file.

        Response via responseReceived("stop", bytes).
        """
        self._sendCommand("stop")

    @Slot(str)
    def load(self, filename: str) -> None:
        """Load a measurement file.

        Args:
            filename: Path to measurement file.

        Response via responseReceived("load", bytes).
        """
        self._sendCommand(f"load {filename}")

    @Slot(str, bool)
    def save(self, filename: str, overwrite: bool = False) -> None:
        """Save current measurement.

        Args:
            filename: Filename to save as.
            overwrite: Whether to overwrite existing file.

        Response via responseReceived("save", bytes).
        """
        cmd = f"save {filename}" + (" overwrite" if overwrite else "")
        self._sendCommand(cmd)

    @Slot(str)
    def loadProject(self, projectPath: str) -> None:
        """Load a QTM project.

        Args:
            projectPath: Path to project.

        Response via responseReceived("loadproject", bytes).
        """
        self._sendCommand(f"loadproject {projectPath}")

    @Slot()
    def trig(self) -> None:
        """Trigger QTM (for software/wireless trigger mode).

        Response via responseReceived("trig", bytes).
        """
        self._sendCommand("trig")

    @Slot(str)
    def setQtmEvent(self, event: str | None = None) -> None:
        """Set an event in QTM.

        Args:
            event: Optional event label.

        Response via responseReceived("event", bytes).
        """
        cmd = "event" + (f" {event}" if event else "")
        self._sendCommand(cmd)

    @Slot(str)
    def sendXml(self, xml: str) -> None:
        """Send XML settings to QTM.

        Args:
            xml: XML document string.

        Response via responseReceived("xml", str).
        """
        self._sendCommand(xml, command_type=QRTPacketType.PacketXML, command_name="xml")

    @Slot()
    def calibrate(self) -> None:
        """Start calibration. Response comes via responseReceived("calibrate", xml).

        Note: Calibration can take several minutes. The response will arrive
        when calibration completes.
        """
        self._sendCommand("calibrate")

    @Slot()
    def quit(self) -> None:
        """Send quit command and disconnect.

        This ends the session with QTM and closes the socket.
        """
        if self.isConnected():
            self._sendCommand("quit", expect_response=False)
        self._socket.disconnectFromHost()

    @Slot(int, str, str)
    def led(self, camera: int, mode: str, color: str) -> None:
        """Control Miqus camera LEDs.

        Args:
            camera: Camera number.
            mode: LED mode - 'on', 'off', or 'pulsing'.
            color: LED color - 'green', 'amber', or 'all'.

        Response via responseReceived("led", str).
        """
        if mode.lower() not in self.VALID_LED_MODES:
            self.error.emit(f"Invalid LED mode: {mode}")
            return
        if color.lower() not in self.VALID_LED_COLORS:
            self.error.emit(f"Invalid LED color: {color}")
            return
        self._sendCommand(f"led {camera} {mode} {color}")

    def onResponse(self, command: str, callback: Callable) -> None:
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

    def removeResponseCallback(self, command: str) -> None:
        """Remove a response callback."""
        self._response_callbacks.pop(command.lower(), None)

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _validateComponents(self, components: list[str]) -> bool:
        """Validate component list.

        Components may include a channel selection suffix separated by a colon,
        e.g., 'analog:1,3,5-8'. The base component before the colon is validated.
        """
        for comp in components:
            base = comp.split(":")[0].lower()
            if base not in self.VALID_COMPONENTS:
                self.error.emit(f"Invalid component: {comp}")
                return False
        return True

    def _sendCommand(
        self,
        command: str,
        expect_response: bool = True,
        command_type: QRTPacketType = QRTPacketType.PacketCommand,
        command_name: str | None = None,
    ) -> None:
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
            name = command_name or command.split()[0].lower()
            self._command_queue.append(name)

        LOG.debug("Sending: %s", command)
        self._socket.write(packet)

    def _emitResponse(self, command: str, data: object) -> None:
        """Emit response via signal and/or callback."""
        self.responseReceived.emit(command, data)

        callback = self._response_callbacks.get(command)
        if callback:
            callback(data)

    def _setupUdpSocket(self, udp_port: int) -> bool:
        """Bind a UDP socket on udp_port for receiving streamed frames.

        Returns True on success; emits error() and returns False on failure.
        """
        # Tear down any previous UDP session (e.g. if streamFrames is called
        # twice without a streamFramesStop in between).
        self._teardownUdpSocket()

        socket = QUdpSocket(self)
        # Bind to any local interface. QTM sends to the source IP of the TCP
        # connection by default, which the OS routes to the correct interface.
        if not socket.bind(QHostAddress.AnyIPv4, udp_port):
            err = f"Failed to bind UDP port {udp_port}: {socket.errorString()}"
            LOG.error(err)
            socket.deleteLater()
            self.error.emit(err)
            return False

        socket.readyRead.connect(self._onUdpReadyRead)
        self._udp_socket = socket
        self._udp_receiver = Receiver(self._handlers)
        LOG.info("UDP receive socket bound on port %d", socket.localPort())
        return True

    def _teardownUdpSocket(self) -> None:
        """Close and release the UDP receive socket, if any."""
        if self._udp_socket is not None:
            self._udp_socket.close()
            self._udp_socket.deleteLater()
            self._udp_socket = None
            self._udp_receiver = None

    def _onUdpReadyRead(self) -> None:
        """Read pending UDP datagrams and route them through the packet handlers.

        Each QTM UDP datagram is a complete RT packet, but we still feed them
        through a Receiver so the parsing path is identical to TCP and any
        future protocol variations are handled uniformly.
        """
        socket = self._udp_socket
        receiver = self._udp_receiver
        if socket is None or receiver is None:
            return
        while socket.hasPendingDatagrams():
            datagram, _host, _port = socket.readDatagram(socket.pendingDatagramSize())
            if datagram:
                receiver.data_received(bytes(datagram))

    # -------------------------------------------------------------------------
    # Socket event handlers
    # -------------------------------------------------------------------------

    def _onSocketConnected(self) -> None:
        """Handle socket connected - negotiate protocol version."""
        self._connect_timer.stop()
        LOG.info("Socket connected, negotiating version %s", self._version)
        self._sendCommand(f"version {self._version}")

    def _onSocketDisconnected(self) -> None:
        """Handle socket disconnected."""
        self._connect_timer.stop()
        LOG.info("Disconnected")
        self._streaming = False
        self._command_queue.clear()
        self._response_callbacks.clear()
        self._receiver = Receiver(self._handlers)
        self._teardownUdpSocket()
        self.disconnected.emit()

    def _onSocketError(self, error: QAbstractSocket.SocketError) -> None:
        """Handle socket error."""
        self._connect_timer.stop()
        error_string = self._socket.errorString()
        LOG.error("Socket error: %s", error_string)
        self.error.emit(error_string)

    def _onConnectTimeout(self) -> None:
        """Handle connection timeout."""
        if not self.isConnected():
            LOG.error("Connection timed out")
            self._socket.abort()
            self.error.emit("Connection timed out")

    def _onReadyRead(self) -> None:
        """Handle incoming data."""
        data = self._socket.readAll().data()
        self._receiver.data_received(data)

    # -------------------------------------------------------------------------
    # Packet handlers (called by Receiver)
    # -------------------------------------------------------------------------

    def _onData(self, packet: QRTPacket) -> None:
        """Handle data packet."""
        # Check if this is a response to getCurrentFrame
        if self._command_queue and self._command_queue[0] == "getcurrentframe":
            cmd = self._command_queue.popleft()
            self._emitResponse(cmd, packet)
        elif self._streaming:
            self.packetReceived.emit(packet)
        elif self._command_queue:
            cmd = self._command_queue.popleft()
            self._emitResponse(cmd, packet)

    def _onNoMoreData(self, data: bytes) -> None:
        """Handle no more data packet (end of file during RT from file)."""
        LOG.debug("No more data")

    def _onEvent(self, event: QRTEvent) -> None:
        """Handle event packet."""
        LOG.info("Event: %s", event)
        self.eventReceived.emit(event)

    def _onError(self, response: bytes) -> None:
        """Handle error packet."""
        error_msg = response.decode("utf-8", errors="replace")
        LOG.error("QTM error: %s", error_msg)
        self._streaming = False
        # Discard the command that caused the error
        if self._command_queue:
            self._command_queue.popleft()
        self.error.emit(error_msg)

    def _onXml(self, response: bytes) -> None:
        """Handle XML response."""
        xml_str = response.decode("utf-8", errors="replace")
        LOG.debug("XML response: %s...", xml_str[:70])

        if self._command_queue:
            cmd = self._command_queue.popleft()
            self._emitResponse(cmd, xml_str)

    def _onCommand(self, response: bytes) -> None:
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
            self._emitResponse(cmd, response_str)
