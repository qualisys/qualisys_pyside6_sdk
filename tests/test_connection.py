"""Tests for QTMConnection"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtNetwork import QTcpSocket

from qtm_rt_pyside6 import QTMConnection


@pytest.fixture
def app(qapp):
    """Use pytest-qt's qapp fixture"""
    return qapp


@pytest.fixture
def connection(app):
    """Create a QTMConnection instance"""
    return QTMConnection()


class TestQTMConnectionInit:
    def test_creates_socket(self, connection):
        assert connection._socket is not None
        assert isinstance(connection._socket, QTcpSocket)

    def test_not_connected_initially(self, connection):
        assert not connection.isConnected()

    def test_has_signals(self, connection):
        # Verify signals exist
        assert hasattr(connection, "connected")
        assert hasattr(connection, "disconnected")
        assert hasattr(connection, "error")
        assert hasattr(connection, "packetReceived")
        assert hasattr(connection, "eventReceived")
        assert hasattr(connection, "responseReceived")


class TestQTMConnectionValidation:
    def test_validate_components_valid(self, connection):
        assert connection._validateComponents(["3d", "6d", "analog"])

    def test_validate_components_invalid(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            result = connection._validateComponents(["invalid_component"])
        assert not result

    def test_validate_components_case_insensitive(self, connection):
        assert connection._validateComponents(["3D", "6D", "ANALOG"])


class TestQTMConnectionCommands:
    def test_stream_frames_not_connected_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            connection.streamFrames(["3d"])

    def test_get_parameters_invalid_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            connection.getParameters(["invalid_param"])

    def test_get_parameters_valid_values(self, connection):
        # Should not raise for valid parameters
        valid_params = ["all", "general", "3d", "6d", "analog", "force"]
        for param in valid_params:
            assert param in connection.VALID_PARAMETERS


class TestQTMConnectionCallbacks:
    def test_on_response_registers_callback(self, connection):
        callback = MagicMock()
        connection.onResponse("getparameters", callback)
        assert "getparameters" in connection._response_callbacks

    def test_remove_response_callback(self, connection):
        callback = MagicMock()
        connection.onResponse("getparameters", callback)
        connection.removeResponseCallback("getparameters")
        assert "getparameters" not in connection._response_callbacks
