"""QTM Discovery using Qt network stack"""

import struct
import logging
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer
from PySide6.QtNetwork import QUdpSocket, QHostAddress, QNetworkInterface

from qtm_rt.packet import QRTPacketType, RTheader

LOG = logging.getLogger("qtm_rt_pyside6")

# Discovery packet format
QRT_DISCOVERY_P1 = struct.Struct("<II")
QRT_DISCOVERY_P2 = struct.Struct(">H")
QRT_DISCOVERY_PACKET_SIZE = QRT_DISCOVERY_P1.size + QRT_DISCOVERY_P2.size
QRT_DISCOVERY_BASE_PORT = struct.Struct(">H")
QRT_DISCOVERY_PORT = 22226


@dataclass
class QTMDiscoveryResponse:
    """Information about a discovered QTM instance."""
    info: str       # QTM info string (hostname, version, etc.)
    host: str       # IP address
    port: int       # Base port number


class QTMDiscovery(QObject):
    """Discover QTM instances on the network using UDP broadcast.

    Signals:
        discovered(QTMDiscoveryResponse): Emitted for each discovered QTM instance
        finished(): Emitted when discovery timeout is reached

    Example:
        discovery = QTMDiscovery()
        discovery.discovered.connect(on_qtm_found)
        discovery.finished.connect(on_discovery_done)
        discovery.start()
    """

    discovered = Signal(object)  # QTMDiscoveryResponse
    finished = Signal()

    def __init__(self, parent: Optional[QObject] = None, timeout_ms: int = 1000):
        """Initialize QTM discovery.

        Args:
            parent: Parent QObject
            timeout_ms: Discovery timeout in milliseconds (default 1000)
        """
        super().__init__(parent)

        self._timeout_ms = timeout_ms
        self._socket: Optional[QUdpSocket] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._onTimeout)
        self._local_port: int = 0

    @Slot()
    def start(self, interface: Optional[str] = None):
        """Start discovery.

        Args:
            interface: Optional IP address of network interface to use.
                      If None, uses all interfaces.
        """
        if self._socket is not None:
            self.stop()

        self._socket = QUdpSocket(self)
        self._socket.readyRead.connect(self._onReadyRead)

        # Bind to any available port
        if interface:
            bind_address = QHostAddress(interface)
        else:
            bind_address = QHostAddress.AnyIPv4

        if not self._socket.bind(bind_address, 0):
            LOG.error("Failed to bind UDP socket: %s", self._socket.errorString())
            self.finished.emit()
            return

        self._local_port = self._socket.localPort()
        LOG.debug("Discovery socket bound to port %d", self._local_port)

        # Send discovery packet
        self._sendDiscoveryPacket()

        # Start timeout timer
        self._timer.start(self._timeout_ms)

    @Slot()
    def stop(self):
        """Stop discovery."""
        self._timer.stop()

        if self._socket is not None:
            self._socket.close()
            self._socket.deleteLater()
            self._socket = None

    def _sendDiscoveryPacket(self):
        """Send broadcast discovery packet."""
        if self._socket is None or self._local_port == 0:
            return

        packet = (
            QRT_DISCOVERY_P1.pack(
                QRT_DISCOVERY_PACKET_SIZE,
                QRTPacketType.PacketDiscover.value
            )
            + QRT_DISCOVERY_P2.pack(self._local_port)
        )

        broadcast_addr = QHostAddress.Broadcast
        bytes_sent = self._socket.writeDatagram(packet, broadcast_addr, QRT_DISCOVERY_PORT)

        if bytes_sent == -1:
            LOG.error("Failed to send discovery packet: %s", self._socket.errorString())
        else:
            LOG.debug("Sent discovery packet to broadcast:%d", QRT_DISCOVERY_PORT)

    def _onReadyRead(self):
        """Handle incoming UDP datagram."""
        while self._socket and self._socket.hasPendingDatagrams():
            datagram, host, port = self._socket.readDatagram(
                self._socket.pendingDatagramSize()
            )

            if not datagram:
                continue

            try:
                response = self._parseResponse(datagram, host.toString())
                if response:
                    LOG.debug("Discovered QTM: %s at %s:%d",
                             response.info, response.host, response.port)
                    self.discovered.emit(response)
            except Exception as e:
                LOG.warning("Failed to parse discovery response: %s", e)

    def _parseResponse(self, datagram: bytes, host: str) -> Optional[QTMDiscoveryResponse]:
        """Parse discovery response datagram."""
        if len(datagram) < RTheader.size + 3:
            return None

        size, packet_type = RTheader.unpack_from(datagram, 0)

        # Extract info string (null-terminated, before the 2-byte port at end)
        info_end = size - 3  # -1 for null terminator, -2 for port
        info_start = RTheader.size
        info = struct.unpack_from(f"{info_end - info_start}s", datagram, info_start)[0]
        info = info.decode("utf-8", errors="replace").rstrip("\x00")

        # Extract base port (last 2 bytes, big endian)
        base_port = QRT_DISCOVERY_BASE_PORT.unpack_from(datagram, size - 2)[0]

        return QTMDiscoveryResponse(info=info, host=host, port=base_port)

    def _onTimeout(self):
        """Handle discovery timeout."""
        LOG.debug("Discovery timeout")
        self.stop()
        self.finished.emit()
