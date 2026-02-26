"""Tests for QTMDiscovery"""

import pytest
from PySide6.QtNetwork import QUdpSocket

from qtm_rt_pyside6 import QTMDiscovery


@pytest.fixture
def app(qapp):
    """Use pytest-qt's qapp fixture"""
    return qapp


@pytest.fixture
def discovery(app):
    """Create a QTMDiscovery instance"""
    return QTMDiscovery()


class TestQTMDiscoveryInit:
    def test_socket_none_initially(self, discovery):
        assert discovery._socket is None

    def test_has_signals(self, discovery):
        assert hasattr(discovery, "discovered")
        assert hasattr(discovery, "finished")

    def test_default_timeout(self, discovery):
        assert discovery._timeout_ms == 1000


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

    def test_finished_signal_on_timeout(self, discovery, qtbot):
        discovery._timeout_ms = 100  # Short timeout for test
        with qtbot.waitSignal(discovery.finished, timeout=500):
            discovery.start()
