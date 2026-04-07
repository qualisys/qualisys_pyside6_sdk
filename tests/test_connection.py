"""Tests for QTMConnection"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtNetwork import QTcpSocket

from qtm_rt_pyside6 import QRTEvent, QRTPacket, QTMConnection


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
        assert hasattr(connection, "connected")
        assert hasattr(connection, "disconnected")
        assert hasattr(connection, "error")
        assert hasattr(connection, "packetReceived")
        assert hasattr(connection, "eventReceived")
        assert hasattr(connection, "responseReceived")

    def test_command_queue_empty_initially(self, connection):
        assert len(connection._command_queue) == 0

    def test_not_streaming_initially(self, connection):
        assert not connection._streaming


class TestQTMConnectionValidation:
    def test_validate_components_valid(self, connection):
        assert connection._validateComponents(["3d", "6d", "analog"])

    def test_validate_components_invalid(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            result = connection._validateComponents(["invalid_component"])
        assert not result

    def test_validate_components_case_insensitive(self, connection):
        assert connection._validateComponents(["3D", "6D", "ANALOG"])

    def test_validate_components_empty_list(self, connection):
        assert connection._validateComponents([])

    def test_validate_all_components(self, connection):
        """Every documented component should be valid."""
        all_components = [
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
        ]
        assert connection._validateComponents(all_components)

    def test_validate_all_parameters(self, connection):
        """Every documented parameter should be valid."""
        all_params = [
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
        ]
        for param in all_params:
            assert param in connection.VALID_PARAMETERS


class TestQTMConnectionCommands:
    def test_stream_frames_not_connected_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            connection.streamFrames(["3d"])

    def test_get_parameters_invalid_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            connection.getParameters(["invalid_param"])

    def test_get_parameters_defaults_to_all(self, connection, qtbot):
        """getParameters() with no args should not error on validation."""
        # Can't test the actual command send (not connected),
        # but verify it doesn't raise on None parameter
        with qtbot.waitSignal(connection.error):
            # Will emit "Not connected" error, not a validation error
            connection.getParameters()

    def test_all_commands_emit_error_when_not_connected(self, connection, qtbot):
        """Every command should emit error when not connected."""
        commands = [
            lambda: connection.getQtmVersion(),
            lambda: connection.getByteOrder(),
            lambda: connection.getState(),
            lambda: connection.getParameters(),
            lambda: connection.getCurrentFrame(["3d"]),
            lambda: connection.streamFrames(["3d"]),
            lambda: connection.streamFramesStop(),
            lambda: connection.takeControl("password"),
            lambda: connection.releaseControl(),
            lambda: connection.newMeasurement(),
            lambda: connection.closeMeasurement(),
            lambda: connection.start(),
            lambda: connection.stop(),
            lambda: connection.load("test.qtm"),
            lambda: connection.save("test.qtm"),
            lambda: connection.loadProject("/path"),
            lambda: connection.trig(),
            lambda: connection.setQtmEvent("test"),
            lambda: connection.sendXml("<xml/>"),
            lambda: connection.calibrate(),
        ]
        for cmd in commands:
            with qtbot.waitSignal(connection.error):
                cmd()


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

    def test_on_response_case_insensitive(self, connection):
        callback = MagicMock()
        connection.onResponse("GetParameters", callback)
        assert "getparameters" in connection._response_callbacks

    def test_remove_nonexistent_callback_no_error(self, connection):
        """Removing a callback that doesn't exist should not raise."""
        connection.removeResponseCallback("nonexistent")

    def test_emit_response_calls_callback(self, connection):
        callback = MagicMock()
        connection.onResponse("test", callback)
        connection._emitResponse("test", "data")
        callback.assert_called_once_with("data")

    def test_emit_response_emits_signal(self, connection, qtbot):
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._emitResponse("test", "data")
        assert blocker.args == ["test", "data"]


class TestQTMConnectionResponseHandling:
    """Test the packet handler methods directly."""

    def test_on_command_skips_initial_message(self, connection):
        """The 'QTM RT Interface connected' message should be silently ignored."""
        connection._command_queue.append("version")
        connection._onCommand(b"QTM RT Interface connected")
        # Queue should still have version — the message was skipped
        assert len(connection._command_queue) == 1
        assert connection._command_queue[0] == "version"

    def test_on_command_version_success(self, connection, qtbot):
        """Successful version negotiation should emit connected signal."""
        connection._command_queue.append("version")
        with qtbot.waitSignal(connection.connected):
            connection._onCommand(b"Version set to 1.25")
        assert len(connection._command_queue) == 0

    def test_on_command_version_failure(self, connection, qtbot):
        """Failed version negotiation should emit error signal."""
        connection._command_queue.append("version")
        with qtbot.waitSignal(connection.error) as blocker:
            connection._onCommand(b"Version NOT supported")
        assert "Version negotiation failed" in blocker.args[0]

    def test_on_command_emits_response(self, connection, qtbot):
        """Command responses should be dispatched via responseReceived."""
        connection._command_queue.append("qtmversion")
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onCommand(b"QTM version is 2024.1")
        assert blocker.args[0] == "qtmversion"

    def test_on_xml_emits_response(self, connection, qtbot):
        """XML responses should be dispatched via responseReceived."""
        connection._command_queue.append("getparameters")
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onXml(b"<General><Frequency>100</Frequency></General>")
        assert blocker.args[0] == "getparameters"
        assert "<General>" in blocker.args[1]

    def test_on_error_emits_error_signal(self, connection, qtbot):
        """Error packets should emit error signal."""
        connection._command_queue.append("somecommand")
        with qtbot.waitSignal(connection.error) as blocker:
            connection._onError(b"Command failed")
        assert "Command failed" in blocker.args[0]

    def test_on_error_stops_streaming(self, connection):
        """Error should stop streaming."""
        connection._streaming = True
        connection._onError(b"Error")
        assert not connection._streaming

    def test_on_error_pops_command_queue(self, connection):
        """Error should discard the failed command from queue."""
        connection._command_queue.append("cmd1")
        connection._command_queue.append("cmd2")
        connection._onError(b"Error")
        assert len(connection._command_queue) == 1
        assert connection._command_queue[0] == "cmd2"

    def test_on_event_emits_signal(self, connection, qtbot):
        """Event packets should emit eventReceived."""
        event = QRTEvent.EventConnected
        with qtbot.waitSignal(connection.eventReceived) as blocker:
            connection._onEvent(event)
        assert blocker.args[0] == event

    def test_on_data_streaming_emits_packet(self, connection, qtbot):
        """Data packets during streaming should emit packetReceived."""
        connection._streaming = True
        mock_packet = MagicMock(spec=QRTPacket)
        with qtbot.waitSignal(connection.packetReceived) as blocker:
            connection._onData(mock_packet)
        assert blocker.args[0] is mock_packet

    def test_on_data_not_streaming_emits_response(self, connection, qtbot):
        """Data packets when not streaming should emit responseReceived."""
        connection._command_queue.append("getcurrentframe")
        mock_packet = MagicMock(spec=QRTPacket)
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onData(mock_packet)
        assert blocker.args[0] == "getcurrentframe"
        assert blocker.args[1] is mock_packet


class TestQTMConnectionCommandQueue:
    """Test that the command queue handles multiple rapid commands correctly."""

    def test_multiple_commands_queued(self, connection):
        """Commands should queue, not overwrite."""
        connection._command_queue.append("qtmversion")
        connection._command_queue.append("getparameters")
        assert len(connection._command_queue) == 2

    def test_responses_matched_in_order(self, connection, qtbot):
        """Responses should be matched to commands in FIFO order."""
        connection._command_queue.append("qtmversion")
        connection._command_queue.append("getparameters")

        # First response matches first command
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onCommand(b"QTM version is 2024.1")
        assert blocker.args[0] == "qtmversion"

        # Second response matches second command
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onXml(b"<Parameters/>")
        assert blocker.args[0] == "getparameters"

        assert len(connection._command_queue) == 0

    def test_error_only_discards_one_command(self, connection, qtbot):
        """An error response should only discard the front command."""
        connection._command_queue.append("cmd1")
        connection._command_queue.append("cmd2")

        connection._onError(b"Error for cmd1")
        assert len(connection._command_queue) == 1

        # Next response should match cmd2
        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onCommand(b"OK")
        assert blocker.args[0] == "cmd2"

    def test_response_with_empty_queue_ignored(self, connection):
        """Responses with no pending commands should not crash."""
        # Should not raise
        connection._onCommand(b"Unexpected response")
        connection._onXml(b"<Unexpected/>")


class TestQTMConnectionDisconnect:
    """Test cleanup on disconnect."""

    def test_disconnect_clears_command_queue(self, connection):
        connection._command_queue.append("cmd1")
        connection._command_queue.append("cmd2")
        connection._onSocketDisconnected()
        assert len(connection._command_queue) == 0

    def test_disconnect_clears_callbacks(self, connection):
        connection.onResponse("test", MagicMock())
        connection._onSocketDisconnected()
        assert len(connection._response_callbacks) == 0

    def test_disconnect_stops_streaming(self, connection):
        connection._streaming = True
        connection._onSocketDisconnected()
        assert not connection._streaming

    def test_disconnect_emits_signal(self, connection, qtbot):
        with qtbot.waitSignal(connection.disconnected):
            connection._onSocketDisconnected()
