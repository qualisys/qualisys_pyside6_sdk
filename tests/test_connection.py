"""Tests for QTMConnection"""

from collections import deque
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
            lambda: connection.led(1, "on", "green"),
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


class TestQTMConnectionQuit:
    """Test quit command."""

    def test_quit_when_not_connected(self, connection):
        """Quit when not connected should just disconnect without error."""
        connection.quit()  # Should not raise

    def test_quit_emits_disconnect(self, connection, qtbot):
        """Quit should trigger disconnected signal via socket disconnect."""
        with qtbot.waitSignal(connection.disconnected):
            connection._onSocketDisconnected()  # Simulate what quit triggers


class TestQTMConnectionLed:
    """Test LED control command."""

    def test_led_invalid_mode_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error) as blocker:
            connection.led(1, "blink", "green")
        assert "Invalid LED mode" in blocker.args[0]

    def test_led_invalid_color_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error) as blocker:
            connection.led(1, "on", "blue")
        assert "Invalid LED color" in blocker.args[0]

    def test_led_valid_modes(self, connection):
        """All valid modes should be accepted."""
        for mode in ("on", "off", "pulsing"):
            assert mode in connection.VALID_LED_MODES

    def test_led_valid_colors(self, connection):
        """All valid colors should be accepted."""
        for color in ("green", "amber", "all"):
            assert color in connection.VALID_LED_COLORS

    def test_led_not_connected_emits_error(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            connection.led(1, "on", "green")


class TestQTMConnectionAnalogChannelSelection:
    """Test analog channel selection in component validation."""

    def test_analog_with_channels_valid(self, connection):
        assert connection._validateComponents(["analog:1,3,5-8"])

    def test_analogsingle_with_channels_valid(self, connection):
        assert connection._validateComponents(["analogsingle:2,4"])

    def test_invalid_base_with_channels_rejected(self, connection, qtbot):
        with qtbot.waitSignal(connection.error):
            result = connection._validateComponents(["invalid:1,2"])
        assert not result

    def test_skeleton_global_still_valid(self, connection):
        """skeleton:global should still work (colon is part of component name)."""
        assert connection._validateComponents(["skeleton:global"])

    def test_mixed_components_with_channels(self, connection):
        assert connection._validateComponents(["3d", "analog:1,3", "force"])


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

    def test_disconnect_clears_calibration_pending(self, connection):
        """A pending calibration should be reset on disconnect."""
        connection._calibration_pending = True
        connection._onSocketDisconnected()
        assert not connection._calibration_pending


class TestQTMConnectionCalibration:
    """Test the two-phase calibration command flow.

    QTM responds to "calibrate" with:
      1. A command packet "Starting calibration" (acknowledgement)
      2. Minutes later, an XML packet with the calibration result

    The wrapper must deliver only the XML result via responseReceived.
    """

    def test_calibration_pending_false_initially(self, connection):
        assert not connection._calibration_pending

    def test_calibrate_does_not_use_command_queue(self, connection):
        """Calibrate bypasses the queue so its two-phase flow doesn't pop other slots."""
        # Pretend we're connected so calibrate() actually sends.
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)
        connection.calibrate()
        assert connection._calibration_pending
        assert len(connection._command_queue) == 0

    def test_calibrate_starting_message_swallowed(self, connection, qtbot):
        """The 'Starting calibration' ack should be logged, not emitted."""
        connection._calibration_pending = True
        # Pre-existing command in the queue should not be popped by the ack.
        connection._command_queue.append("qtmversion")

        # Listen on responseReceived; it should NOT fire for the ack.
        # Use assertNotEmitted via a brief wait.
        with qtbot.assertNotEmitted(connection.responseReceived, wait=50):
            connection._onCommand(b"Starting calibration")

        assert connection._calibration_pending  # still waiting for XML
        assert connection._command_queue == deque(["qtmversion"])  # untouched

    def test_calibration_xml_emitted_as_calibrate_response(self, connection, qtbot):
        """The XML result should arrive on responseReceived as ('calibrate', xml)."""
        connection._calibration_pending = True
        xml = b"<calibration><residual>0.5</residual></calibration>"

        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onXml(xml)

        assert blocker.args[0] == "calibrate"
        assert "<calibration>" in blocker.args[1]
        assert not connection._calibration_pending

    def test_calibration_xml_does_not_pop_unrelated_queue(self, connection, qtbot):
        """An XML for a pending calibration must not consume an unrelated queued command."""
        connection._calibration_pending = True
        connection._command_queue.append("getparameters")

        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onXml(b"<calibration/>")

        assert blocker.args[0] == "calibrate"
        # getparameters slot is still waiting for its own XML response.
        assert connection._command_queue == deque(["getparameters"])

    def test_normal_xml_still_pops_queue_when_no_pending_calibration(self, connection, qtbot):
        """Sanity check: existing getparameters/etc XML routing is unaffected."""
        assert not connection._calibration_pending
        connection._command_queue.append("getparameters")

        with qtbot.waitSignal(connection.responseReceived) as blocker:
            connection._onXml(b"<Parameters/>")

        assert blocker.args[0] == "getparameters"
        assert len(connection._command_queue) == 0

    def test_error_during_calibration_clears_flag_without_popping_queue(self, connection, qtbot):
        """If QTM errors during calibration, clear the flag — don't pop someone else's slot."""
        connection._calibration_pending = True
        connection._command_queue.append("qtmversion")

        with qtbot.waitSignal(connection.error):
            connection._onError(b"Calibration aborted")

        assert not connection._calibration_pending
        # qtmversion is still waiting — error was attributed to calibrate, not it.
        assert connection._command_queue == deque(["qtmversion"])
