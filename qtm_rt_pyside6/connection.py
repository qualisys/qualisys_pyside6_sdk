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
        noMoreData(): Emitted when QTM signals end-of-file during RT-from-file streaming

    Methods:
        Connection:
            connectToHost(host, port=22223, version="1.25", timeout_ms=5000):
                Open TCP connection and negotiate protocol version.
            disconnectFromHost(): Close the connection.
            isConnected() -> bool: Current connection state.
            quit(): Send the QTM 'quit' command and disconnect.

        Streaming:
            streamFrames(components, frames="allframes",
                         udp_port=None, udp_address=None):
                Start streaming. Pass udp_port for UDP delivery;
                omit udp_address to let QTM send to the TCP client IP.
            streamFramesStop(): Stop streaming.
            getCurrentFrame(components): Request a single frame.

        Configuration:
            getParameters(parameters=None): Request QTM config as XML.
            getQtmVersion(): Request the QTM version string.
            getByteOrder(): Request the protocol byte order.
            getState(): Request the current QTM state (via eventReceived).
            sendXml(xml): Send an XML settings document.

        Measurement control:
            takeControl(password) / releaseControl():
                Acquire or release RT control of QTM.
            newMeasurement() / closeMeasurement():
                Create / close a measurement.
            start(rtFromFile=False) / stop():
                Start / stop measurement or RT from file.
            load(filename) / save(filename, overwrite=False):
                Load / save a measurement file.
            loadProject(projectPath): Load a QTM project.
            trig(): Software / wireless trigger.
            setQtmEvent(event=None): Insert a QTM event label.
            led(camera, mode, color): Control a Miqus camera LED.

        Response callbacks (convenience wrappers over responseReceived):
            onResponse(command, callback): Register a per-command callback.
            removeResponseCallback(command): Unregister a callback.

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
    noMoreData = Signal()  # End-of-file during RT-from-file streaming

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

    # Components that accept a free-form channel-selection suffix after a
    # colon, e.g. 'analog:1,3,5-8'. Components not in this set but with a
    # colon must appear verbatim in VALID_COMPONENTS (e.g. 'skeleton:global').
    CHANNEL_SELECTABLE = {"analog", "analogsingle"}

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
        self._version_negotiated = False
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

    @Slot(str, int, str, int)
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
    def disconnectFromHost(self) -> None:
        """Disconnect from QTM.

        Named to mirror connectToHost() and to avoid colliding with
        QObject.disconnect() (which detaches signal/slot connections).
        """
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

    @Slot(list, str, int, str)
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
            udp_port: Optional UDP port for UDP streaming (1024-65535). When
                set, a local UDP socket is bound on this port and QTM sends
                data packets to it instead of over the TCP connection.
            udp_address: Optional UDP address passed through to QTM. If omitted,
                QTM sends frames to the TCP client's source IP. Set this to
                redirect data to a different host — in that case no local UDP
                socket is bound and packetReceived will not fire locally.

        Packets arrive via packetReceived(QRTPacket) for TCP streaming and
        for the default UDP case (no udp_address). If udp_address is set to
        a remote host, frames are sent there and packetReceived will not
        fire on this connection.
        """
        if not self._validateComponents(components):
            return

        # Validate the documented UDP port range. Binding to 0 would work at
        # the OS level (ephemeral port), but the command sent to QTM would
        # still be "udp:0", so QTM would have no idea where to send frames
        # and packetReceived would never fire. Reject that (and the privileged
        # port range) up front.
        if udp_port is not None and not (1024 <= udp_port <= 65535):
            self.error.emit(f"udp_port must be between 1024 and 65535, got {udp_port}")
            return

        # Guard: if we're not connected, bail out before any side-effecting
        # setup. Otherwise _sendCommand would emit "Not connected" but leave
        # a bound UDP socket and _streaming=True behind.
        if not self.isConnected():
            self.error.emit("Not connected")
            return

        # Set up local UDP receive socket if requested and no remote redirect.
        # If the caller redirects with udp_address, we don't bind locally —
        # the user has chosen to send frames to another host.
        if udp_port is not None and not udp_address and not self._setupUdpSocket(udp_port):
            return  # error already emitted

        self._streaming = True
        # Per the QTM RT protocol the frame-selector token (AllFrames /
        # Frequency:N / FrequencyDivisor:N) must come immediately after
        # "streamframes", *before* the optional UDP redirect. Building the
        # command the other way around makes QTM reply with "Parse Error".
        # Protocol reference:
        # https://docs.qualisys.com/qtm-rt-protocol/#streamframes
        parts = ["streamframes", frames]
        if udp_port is not None:
            if udp_address:
                parts.append(f"udp:{udp_address}:{udp_port}")
            else:
                parts.append(f"udp:{udp_port}")
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

        Response via responseReceived("takecontrol", str).
        """
        self._sendCommand(f"takecontrol {password}")

    @Slot()
    def releaseControl(self) -> None:
        """Release control of QTM.

        Response via responseReceived("releasecontrol", str).
        """
        self._sendCommand("releasecontrol")

    @Slot()
    def newMeasurement(self) -> None:
        """Create a new measurement. Requires control.

        Response via responseReceived("new", str).
        """
        self._sendCommand("new")

    @Slot()
    def closeMeasurement(self) -> None:
        """Close current measurement.

        Response via responseReceived("close", str).
        """
        self._sendCommand("close")

    @Slot(bool)
    def start(self, rtFromFile: bool = False) -> None:
        """Start measurement or RT from file. Requires control.

        Args:
            rtFromFile: If True, start RT from file instead of live capture.

        Response via responseReceived("start", str).
        """
        cmd = "start" + (" rtfromfile" if rtFromFile else "")
        self._sendCommand(cmd)

    @Slot()
    def stop(self) -> None:
        """Stop measurement or RT from file.

        Response via responseReceived("stop", str).
        """
        self._sendCommand("stop")

    @Slot(str)
    def load(self, filename: str) -> None:
        """Load a measurement file.

        Args:
            filename: Path to measurement file.

        Response via responseReceived("load", str).
        """
        self._sendCommand(f"load {filename}")

    @Slot(str, bool)
    def save(self, filename: str, overwrite: bool = False) -> None:
        """Save current measurement.

        Args:
            filename: Filename to save as.
            overwrite: Whether to overwrite existing file.

        Response via responseReceived("save", str).
        """
        cmd = f"save {filename}" + (" overwrite" if overwrite else "")
        self._sendCommand(cmd)

    @Slot(str)
    def loadProject(self, projectPath: str) -> None:
        """Load a QTM project.

        Args:
            projectPath: Path to project.

        Response via responseReceived("loadproject", str).
        """
        self._sendCommand(f"loadproject {projectPath}")

    @Slot()
    def trig(self) -> None:
        """Trigger QTM (for software/wireless trigger mode).

        Response via responseReceived("trig", str).
        """
        self._sendCommand("trig")

    @Slot(str)
    def setQtmEvent(self, event: str | None = None) -> None:
        """Set an event in QTM.

        Args:
            event: Optional event label.

        Response via responseReceived("event", str).
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

        Two valid shapes:

        1. A component that appears verbatim in VALID_COMPONENTS, e.g.
           'skeleton' or 'skeleton:global'. Case-insensitive.
        2. A CHANNEL_SELECTABLE base followed by a free-form channel
           selector, e.g. 'analog:1,3,5-8'. Only 'analog' and
           'analogsingle' support this suffix syntax.

        Anything else (e.g. 'skeleton:garbage' or 'force:foo') is rejected.
        """
        for comp in components:
            lc = comp.lower()
            if lc in self.VALID_COMPONENTS:
                continue
            if ":" in lc and lc.split(":", 1)[0] in self.CHANNEL_SELECTABLE:
                continue
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
        self._version_negotiated = False
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
        self.noMoreData.emit()

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
        # Release any bound UDP socket — symmetric with streamFramesStop
        # and _onSocketDisconnected. Without this, an error aborting a UDP
        # stream would leave the port held.
        self._teardownUdpSocket()
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
                # Guard against a duplicate version handshake accidentally
                # re-emitting connected (e.g. if someone sends "version"
                # again after the initial successful handshake).
                if self._version_negotiated:
                    LOG.debug("Version response received again; ignoring")
                else:
                    self._version_negotiated = True
                    LOG.info("Connected with protocol %s", self._version)
                    self.connected.emit()
            else:
                LOG.error("Version negotiation failed: %s", response_str)
                self.error.emit(f"Version negotiation failed: {response_str}")
                # The protocol handshake failed — close the TCP socket so the
                # caller doesn't sit at a half-open connection. _onSocketDisconnected
                # will clean up the rest of the state.
                self._socket.disconnectFromHost()
            return

        if self._command_queue:
            cmd = self._command_queue.popleft()
            self._emitResponse(cmd, response_str)
