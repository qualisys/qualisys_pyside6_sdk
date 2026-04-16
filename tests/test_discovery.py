"""Tests for QTMDiscovery"""

import struct

import pytest
from PySide6.QtNetwork import QUdpSocket
from qtm_rt.packet import QRTPacketType, RTheader

from qtm_rt_pyside6 import QTMDiscovery
from qtm_rt_pyside6.discovery import QTMDiscoveryResponse


@pytest.fixture
def app(qapp):
    """Use pytest-qt's qapp fixture"""
    return qapp


@pytest.fixture
def discovery(app):
    """Create a QTMDiscovery instance"""
    return QTMDiscovery()


def _build_discovery_packet(info: str, port: int, packet_type: int | None = None) -> bytes:
    """Build a fake discovery response datagram."""
    if packet_type is None:
        packet_type = QRTPacketType.PacketDiscover.value
    info_bytes = info.encode("utf-8") + b"\x00"
    port_bytes = struct.pack(">H", port)
    size = RTheader.size + len(info_bytes) + len(port_bytes)
    header = RTheader.pack(size, packet_type)
    return header + info_bytes + port_bytes


class TestQTMDiscoveryInit:
    def test_socket_none_initially(self, discovery):
        assert discovery._socket is None

    def test_has_signals(self, discovery):
        assert hasattr(discovery, "discovered")
        assert hasattr(discovery, "finished")

    def test_default_timeout(self, discovery):
        assert discovery._timeout_ms == 1000

    def test_custom_timeout(self, app):
        d = QTMDiscovery(timeout_ms=5000)
        assert d._timeout_ms == 5000


class TestQTMDiscoveryLifecycle:
    def test_start_creates_socket(self, discovery, qtbot):
        discovery.start()
        assert discovery._socket is not None
        assert isinstance(discovery._socket, QUdpSocket)
        discovery.stop()

    def test_stop_cleans_up_socket(self, discovery, qtbot):
        discovery.start()
        discovery.stop()
        assert discovery._socket is None

    def test_stop_without_start(self, discovery):
        """Calling stop before start should not raise."""
        discovery.stop()
        assert discovery._socket is None

    def test_start_twice_cleans_up_first(self, discovery, qtbot):
        """Starting twice should stop the first socket."""
        discovery.start()
        first_socket = discovery._socket
        discovery.start()
        assert discovery._socket is not first_socket
        discovery.stop()

    def test_finished_signal_on_timeout(self, discovery, qtbot):
        discovery._timeout_ms = 100  # Short timeout for test
        with qtbot.waitSignal(discovery.finished, timeout=500):
            discovery.start()


class TestQTMDiscoveryResponseParsing:
    """Test the _parseResponse method directly."""

    def test_parse_valid_response(self, discovery):
        datagram = _build_discovery_packet("QTM 2024.1 on TestHost", 22223)
        result = discovery._parseResponse(datagram, "192.168.1.100")
        assert result is not None
        assert result.info == "QTM 2024.1 on TestHost"
        assert result.host == "192.168.1.100"
        assert result.port == 22223

    def test_parse_too_short(self, discovery):
        """Datagrams shorter than minimum should return None."""
        result = discovery._parseResponse(b"\x00\x01", "192.168.1.1")
        assert result is None

    def test_parse_invalid_size_field(self, discovery):
        """Size field larger than datagram should return None."""
        datagram = _build_discovery_packet("QTM", 22223)
        # Overwrite size field to be too large
        bad_datagram = RTheader.pack(9999, QRTPacketType.PacketDiscover.value) + datagram[RTheader.size :]
        result = discovery._parseResponse(bad_datagram, "192.168.1.1")
        assert result is None

    def test_parse_accepts_packet_command(self, discovery):
        """QTM replies with packet_type == PacketCommand (1), not PacketDiscover (7).
        The parser must accept those replies so discovery actually works."""
        datagram = _build_discovery_packet("QTM", 22223, packet_type=QRTPacketType.PacketCommand.value)
        result = discovery._parseResponse(datagram, "192.168.1.1")
        assert result is not None
        assert result.info == "QTM"
        assert result.port == 22223

    def test_parse_ipv6_mapped_address_normalized(self, discovery):
        """IPv6-mapped IPv4 addresses should be normalized."""
        datagram = _build_discovery_packet("QTM", 22223)
        result = discovery._parseResponse(datagram, "::ffff:192.168.1.100")
        assert result is not None
        assert result.host == "192.168.1.100"

    def test_parse_real_ipv6_unchanged(self, discovery):
        """Real IPv6 addresses should not be modified."""
        datagram = _build_discovery_packet("QTM", 22223)
        result = discovery._parseResponse(datagram, "fe80::1")
        assert result is not None
        assert result.host == "fe80::1"

    def test_parse_different_ports(self, discovery):
        """Various port numbers should parse correctly."""
        for port in [22223, 22224, 0, 65535]:
            datagram = _build_discovery_packet("QTM", port)
            result = discovery._parseResponse(datagram, "10.0.0.1")
            assert result is not None
            assert result.port == port

    def test_parse_empty_info(self, discovery):
        """Empty info string should still parse."""
        datagram = _build_discovery_packet("", 22223)
        result = discovery._parseResponse(datagram, "10.0.0.1")
        assert result is not None
        assert result.info == ""


class TestQTMDiscoveryResponse:
    def test_dataclass_fields(self):
        response = QTMDiscoveryResponse(info="QTM 2024.1", host="192.168.1.1", port=22223)
        assert response.info == "QTM 2024.1"
        assert response.host == "192.168.1.1"
        assert response.port == 22223

    def test_dataclass_equality(self):
        r1 = QTMDiscoveryResponse(info="QTM", host="1.2.3.4", port=22223)
        r2 = QTMDiscoveryResponse(info="QTM", host="1.2.3.4", port=22223)
        assert r1 == r2
