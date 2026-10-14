"""Tests for QTMConnection"""

import struct
from unittest.mock import MagicMock

import pytest
from PySide6.QtNetwork import QTcpSocket
from qtm_rt.packet import RTheader

from qtm_rt_pyside6 import QRTEvent, QRTPacket, QRTPacketType, QTMConnection
from qtm_rt_pyside6.connection import STREAM_SYNC


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
        assert hasattr(connection, "noMoreData")

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

    def test_validate_skeleton_global_accepted(self, connection):
        """'skeleton:global' is a distinct component in the QTM protocol."""
        assert connection._validateComponents(["skeleton:global"])
        assert connection._validateComponents(["SKELETON:GLOBAL"])

    def test_validate_skeleton_garbage_rejected(self, connection, qtbot):
        """Skeleton doesn't accept arbitrary colon-suffixes — only :global."""
        with qtbot.waitSignal(connection.error) as blocker:
            result = connection._validateComponents(["skeleton:garbage"])
        assert not result
        assert "skeleton:garbage" in blocker.args[0]

    def test_validate_channel_selection_on_analog(self, connection):
        """Only analog / analogsingle support free-form channel selection."""
        assert connection._validateComponents(["analog:1,3,5-8"])
        assert connection._validateComponents(["analogsingle:2,4"])

    def test_validate_channel_selection_rejected_on_other_bases(self, connection, qtbot):
        """Channel-selection syntax on non-analog components is invalid."""
        with qtbot.waitSignal(connection.error) as blocker:
            result = connection._validateComponents(["force:foo"])
        assert not result
        assert "force:foo" in blocker.args[0]

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

    def test_stream_frames_udp_not_connected_does_not_leak_state(self, connection, qtbot):
        """streamFrames(..., udp_port=...) while not connected must not leave a
        bound UDP socket or _streaming=True behind."""
        assert not connection.isConnected()
        with qtbot.waitSignal(connection.error) as blocker:
            connection.streamFrames(["3d"], udp_port=22224)
        assert blocker.args[0] == "Not connected"
        assert connection._udp_socket is None
        assert connection._udp_receiver is None
        assert not connection._streaming

    @pytest.mark.parametrize("bad_port", [-1, 0, 1023, 65536, 100000])
    def test_stream_frames_rejects_out_of_range_udp_port(self, connection, qtbot, bad_port):
        """udp_port must be inside 1024-65535. The OS would accept 0
        (ephemeral bind) but QTM would receive 'udp:0' and never send frames,
        so the caller gets a silent failure. Ports <= 1023 are privileged on
        Unix and shouldn't be used for an application listener anyway."""
        with qtbot.waitSignal(connection.error) as blocker:
            connection.streamFrames(["3d"], udp_port=bad_port)
        assert "udp_port must be between" in blocker.args[0]
        # Validation happens before any state mutation.
        assert connection._udp_socket is None
        assert not connection._streaming

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
        """Failed version negotiation should emit error signal AND tear down the TCP socket.

        Without the disconnect, the caller is left at a half-open TCP connection
        with no agreed protocol — any command they send would be silently ignored.
        """
        connection._command_queue.append("version")
        connection._socket.disconnectFromHost = MagicMock()
        with qtbot.waitSignal(connection.error) as blocker:
            connection._onCommand(b"Version NOT supported")
        assert "Version negotiation failed" in blocker.args[0]
        connection._socket.disconnectFromHost.assert_called_once()

    def test_duplicate_version_response_does_not_reemit_connected(self, connection, qtbot):
        """A second 'Version set to ...' response should not fire connected again."""
        # First handshake: should emit connected.
        connection._command_queue.append("version")
        with qtbot.waitSignal(connection.connected):
            connection._onCommand(b"Version set to 1.25")
        assert connection._version_negotiated

        # Second handshake (shouldn't happen in practice but shouldn't re-emit).
        connection._command_queue.append("version")
        with qtbot.assertNotEmitted(connection.connected, wait=50):
            connection._onCommand(b"Version set to 1.25")

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

    def test_on_error_tears_down_udp_socket(self, connection):
        """Error aborting a stream must release the UDP socket too, otherwise
        the port stays bound even though streaming has stopped."""
        assert connection._setupUdpSocket(22224)
        assert connection._udp_socket is not None
        connection._onError(b"fail")
        assert connection._udp_socket is None
        assert connection._udp_receiver is None

    def test_on_event_emits_signal(self, connection, qtbot):
        """Event packets should emit eventReceived."""
        event = QRTEvent.EventConnected
        with qtbot.waitSignal(connection.eventReceived) as blocker:
            connection._onEvent(event)
        assert blocker.args[0] == event

    def test_on_no_more_data_emits_signal(self, connection, qtbot):
        """End-of-file during RT-from-file should surface as noMoreData()."""
        with qtbot.waitSignal(connection.noMoreData):
            connection._onNoMoreData(b"")

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


class TestQTMConnectionStreamFramesQueue:
    """QTM never replies to a successful streamframes or streamframes stop: it
    starts or stops sending frames, and sends an error packet only if it rejects
    the command. The SDK follows each with a qtmversion, whose reply marks the
    point where QTM handled it. Replies to later commands must not be handed to
    streamframes, a streamframes error must not discard a later command, and no
    frame may be taken for a reply. Packets are fed through the real Receiver.

    Reference: https://docs.qualisys.com/qtm-rt-protocol/#streamframes
    """

    VERSION_REPLY = b"QTM Version is 2026.3"

    @pytest.fixture
    def live(self, connection):
        """A connection with a mocked, connected socket and the version handshake done."""
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)
        connection._onSocketConnected()
        self._feed(connection, QRTPacketType.PacketCommand, b"QTM RT Interface connected")
        self._feed(connection, QRTPacketType.PacketCommand, b"Version set to 1.25")
        assert connection._version_negotiated
        assert len(connection._command_queue) == 0
        return connection

    @pytest.fixture
    def responses(self, live):
        """Every (command, data) emitted through responseReceived."""
        received = []
        live.responseReceived.connect(lambda command, data: received.append((command, data)))
        return received

    @pytest.fixture
    def frames(self, live):
        """The frame numbers of every packet emitted through packetReceived."""
        received = []
        live.packetReceived.connect(lambda packet: received.append(packet.framenumber))
        return received

    @staticmethod
    def _feed(connection, packet_type, payload=b""):
        """Deliver one RT packet from QTM, as _onReadyRead would."""
        if packet_type in (QRTPacketType.PacketError, QRTPacketType.PacketCommand, QRTPacketType.PacketXML):
            payload += b"\0"
        connection._receiver.data_received(RTheader.pack(RTheader.size + len(payload), packet_type.value) + payload)

    @classmethod
    def _feed_frame(cls, connection, framenumber=1):
        # Data payload: timestamp uint64, framenumber uint32, component_count uint32
        cls._feed(connection, QRTPacketType.PacketData, struct.pack("<QII", 1000, framenumber, 0))

    @classmethod
    def _feed_version(cls, connection):
        cls._feed(connection, QRTPacketType.PacketCommand, cls.VERSION_REPLY)

    @staticmethod
    def _written(connection):
        return [bytes(call.args[0]) for call in connection._socket.write.call_args_list]

    @pytest.mark.parametrize("stop", [False, True], ids=["start", "stop"])
    def test_qtmversion_follows_streamframes(self, live, stop):
        live.streamFrames(["3d"])
        if stop:
            live.streamFramesStop()
        written = self._written(live)[-2:]
        assert (b"streamframes stop" if stop else b"streamframes allframes 3d") in written[0]
        assert b"qtmversion" in written[1]
        assert list(live._command_queue) == ["streamframes", STREAM_SYNC] + ([STREAM_SYNC] if stop else [])

    @pytest.mark.parametrize(
        "stream_start",
        [
            pytest.param(["frame", "frame", "version"], id="frames-first"),
            pytest.param(["version", "frame"], id="version-reply-first"),
            pytest.param(["nomoredata", "version"], id="no-measurement"),
        ],
    )
    def test_get_parameters_while_streaming(self, live, responses, frames, stream_start):
        """connect -> getParameters -> streamFrames -> getParameters: the second
        XML reply belongs to getparameters, not to streamframes."""
        callback = MagicMock()
        live.onResponse("getparameters", callback)

        live.getParameters(["general"])
        self._feed(live, QRTPacketType.PacketXML, b"<QTM_Parameters_Ver_1.25>first</QTM_Parameters_Ver_1.25>")
        callback.assert_called_once()

        live.streamFrames(["3d"])
        for i, packet in enumerate(stream_start):
            if packet == "frame":
                self._feed_frame(live, framenumber=i)
            elif packet == "nomoredata":
                self._feed(live, QRTPacketType.PacketNoMoreData)
            else:
                self._feed_version(live)

        live.getParameters(["general"])
        self._feed(live, QRTPacketType.PacketXML, b"<QTM_Parameters_Ver_1.25>second</QTM_Parameters_Ver_1.25>")
        assert [command for command, _data in responses] == ["getparameters", "getparameters"]
        assert "second" in responses[1][1]
        assert callback.call_count == 2
        assert len(live._command_queue) == 0

        # Every frame went to packetReceived, before and after
        self._feed_frame(live, framenumber=99)
        assert frames == [i for i, packet in enumerate(stream_start) if packet == "frame"] + [99]

    def test_rejected_streamframes_does_not_discard_next_command(self, live, qtbot, responses):
        """QTM's error for a rejected streamframes is the streamframes' own; the
        getparameters sent after it must still receive its XML reply."""
        live.streamFrames(["3d"], frames="frequency:0")
        live.getParameters(["general"])

        with qtbot.waitSignal(live.error) as blocker:
            self._feed(live, QRTPacketType.PacketError, b"Parse Error")
        assert blocker.args[0] == "Parse Error"
        assert not live._streaming
        assert list(live._command_queue) == [STREAM_SYNC, "getparameters"]

        self._feed_version(live)
        self._feed(live, QRTPacketType.PacketXML, b"<QTM_Parameters_Ver_1.25/>")
        assert [command for command, _data in responses] == ["getparameters"]
        assert len(live._command_queue) == 0

    def test_error_for_later_command_before_first_frame(self, live, qtbot, responses):
        """With a measurement running, an error for the command after
        streamframes can arrive before the first frame. It belongs to that
        command, and the next reply to the command after it."""
        live.streamFrames(["3d"])
        live.takeControl("wrong")
        live.getQtmVersion()

        self._feed_version(live)  # streamframes accepted
        with qtbot.waitSignal(live.error):
            self._feed(live, QRTPacketType.PacketError, b"Wrong or missing password")
        assert list(live._command_queue) == ["qtmversion"]

        self._feed_version(live)
        assert responses == [("qtmversion", self.VERSION_REPLY.decode())]
        assert len(live._command_queue) == 0

    def test_frames_of_running_stream_do_not_accept_replacement(self, live, qtbot, responses, frames):
        """streamFrames() while a stream runs: frames QTM sent before it handled
        the new streamframes are not taken as acceptance, so the replacement's
        rejection does not discard the command queued after it."""
        live.streamFrames(["3d"])
        self._feed_version(live)
        self._feed_frame(live, framenumber=1)

        live.streamFrames(["3d", "6d"])
        live.getParameters(["general"])
        self._feed_frame(live, framenumber=2)
        self._feed_frame(live, framenumber=3)
        assert frames == [1, 2, 3]
        assert list(live._command_queue) == ["streamframes", STREAM_SYNC, "getparameters"]

        with qtbot.waitSignal(live.error):
            self._feed(live, QRTPacketType.PacketError, b"Parse Error")
        self._feed_version(live)
        self._feed(live, QRTPacketType.PacketXML, b"<QTM_Parameters_Ver_1.25/>")
        assert [command for command, _data in responses] == ["getparameters"]
        assert len(live._command_queue) == 0

    def test_get_current_frame_refused_while_streaming(self, live, qtbot, responses, frames):
        """QTM refuses getcurrentframe while streaming, and stream frames before
        its error could not be told from a reply, so the SDK refuses it itself."""
        live.streamFrames(["3d"])
        self._feed_version(live)
        writes = len(self._written(live))

        with qtbot.waitSignal(live.error) as blocker:
            live.getCurrentFrame(["3d"])
        assert blocker.args[0] == "Cannot send current frame while streaming data."
        assert len(self._written(live)) == writes
        assert live._streaming

        self._feed_frame(live, framenumber=7)
        assert frames == [7]
        assert responses == []
        assert len(live._command_queue) == 0

    def test_frames_after_stop_are_not_taken_for_get_current_frame(self, live, qtbot, responses, frames):
        """Frames QTM sent before it handled streamframes stop can arrive after
        streamFramesStop(). They are dropped, and the reply to a getcurrentframe
        sent right after is the frame that follows the qtmversion reply."""
        live.streamFrames(["3d"])
        self._feed_version(live)
        self._feed_frame(live, framenumber=1)

        live.streamFramesStop()
        live.getCurrentFrame(["3d"])
        self._feed_frame(live, framenumber=2)  # still on its way when QTM stopped
        assert frames == [1]
        assert responses == []

        self._feed_version(live)
        with qtbot.waitSignal(live.responseReceived) as blocker:
            self._feed_frame(live, framenumber=3)
        assert blocker.args[0] == "getcurrentframe"
        assert blocker.args[1].framenumber == 3
        assert len(live._command_queue) == 0

    def test_no_more_data_answers_get_current_frame(self, live, qtbot, responses):
        """With no measurement to read, QTM answers getcurrentframe with NoMoreData."""
        live.getCurrentFrame(["3d"])
        with qtbot.waitSignal(live.noMoreData):
            self._feed(live, QRTPacketType.PacketNoMoreData)
        assert len(live._command_queue) == 0

        live.getQtmVersion()
        self._feed_version(live)
        assert responses == [("qtmversion", self.VERSION_REPLY.decode())]


class TestQTMConnectionQuit:
    """Test quit command."""

    def test_quit_when_not_connected(self, connection):
        """Quit when not connected should just disconnect without error."""
        connection.quit()  # Should not raise

    def test_quit_when_connected_sends_quit_then_disconnects(self, connection):
        """quit() should write the 'quit' payload and then close the socket."""
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)
        connection._socket.disconnectFromHost = MagicMock()

        connection.quit()

        # The 'quit' command should have been written to the socket.
        connection._socket.write.assert_called_once()
        written_bytes = connection._socket.write.call_args[0][0]
        assert b"quit" in written_bytes
        # And the TCP socket should have been asked to disconnect.
        connection._socket.disconnectFromHost.assert_called_once()


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

    def test_disconnect_tears_down_udp_socket(self, connection):
        """UDP receive socket should be released when the TCP socket drops."""
        assert connection._setupUdpSocket(0)  # 0 = OS-assigned free port
        assert connection._udp_socket is not None
        connection._onSocketDisconnected()
        assert connection._udp_socket is None
        assert connection._udp_receiver is None


class TestQTMConnectionUdpStreaming:
    """Test UDP receive-socket lifecycle and packet routing."""

    def test_no_udp_socket_by_default(self, connection):
        assert connection._udp_socket is None
        assert connection._udp_receiver is None

    def test_setup_udp_socket_binds(self, connection):
        """_setupUdpSocket on an ephemeral port should succeed and create a receiver."""
        assert connection._setupUdpSocket(0)
        assert connection._udp_socket is not None
        assert connection._udp_receiver is not None
        # Cleanup
        connection._teardownUdpSocket()

    def test_setup_udp_socket_bind_failure_emits_error(self, connection, qtbot):
        """Binding an already-bound port should emit error and return False."""
        from PySide6.QtNetwork import QHostAddress, QUdpSocket

        # Occupy a port first
        squatter = QUdpSocket()
        assert squatter.bind(QHostAddress.AnyIPv4, 0)
        port = squatter.localPort()

        with qtbot.waitSignal(connection.error) as blocker:
            ok = connection._setupUdpSocket(port)
        assert not ok
        assert "Failed to bind UDP port" in blocker.args[0]
        assert connection._udp_socket is None
        squatter.close()

    def test_setup_udp_socket_replaces_previous(self, connection):
        """Calling _setupUdpSocket twice should tear down the first socket."""
        assert connection._setupUdpSocket(0)
        first = connection._udp_socket
        assert connection._setupUdpSocket(0)
        assert connection._udp_socket is not first
        connection._teardownUdpSocket()

    def test_teardown_is_idempotent(self, connection):
        """Tearing down with no active UDP socket should be a no-op."""
        connection._teardownUdpSocket()
        connection._teardownUdpSocket()
        assert connection._udp_socket is None

    def test_stream_frames_stop_tears_down_udp_socket(self, connection):
        """streamFramesStop (via the private teardown) should release UDP socket.

        We can't call streamFramesStop without a connected TCP socket, but we
        verify the teardown helper does its job — streamFramesStop delegates.
        """
        assert connection._setupUdpSocket(0)
        connection._teardownUdpSocket()
        assert connection._udp_socket is None

    def test_udp_address_redirect_does_not_bind_local(self, connection):
        """When udp_address points at a remote host, we must NOT bind a local
        UDP socket. The command should still forward the redirect to QTM."""
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)

        connection.streamFrames(["3d"], udp_port=22224, udp_address="10.0.0.5")

        assert connection._udp_socket is None
        assert connection._udp_receiver is None
        # The command string sent to QTM should contain the redirect.
        written = connection._socket.write.call_args_list[0][0][0]
        assert b"udp:10.0.0.5:22224" in written

    def test_stream_frames_tcp_command_order(self, connection):
        """QTM requires: streamframes <frames> <components...>"""
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)

        connection.streamFrames(["3d"])

        written = bytes(connection._socket.write.call_args_list[0][0][0])
        # The payload is an RT header + command bytes + NUL; assert the command
        # substring is intact and in the documented order.
        assert b"streamframes allframes 3d" in written

    def test_stream_frames_udp_command_order(self, connection):
        """QTM requires the frame selector *before* the UDP token:

            streamframes <frames> udp[:address]:port <components...>

        Swapping that order makes QTM reply with 'Parse Error'.
        Reference: https://docs.qualisys.com/qtm-rt-protocol/#streamframes
        """
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)

        connection.streamFrames(["2d"], udp_port=33333, udp_address="192.168.254.255")

        written = bytes(connection._socket.write.call_args_list[0][0][0])
        assert b"streamframes allframes udp:192.168.254.255:33333 2d" in written

    def test_stream_frames_udp_no_address_command_order(self, connection):
        """Same as above but without explicit udp_address — QTM sends back to
        the TCP client's source IP."""
        connection.isConnected = lambda: True
        connection._socket.write = MagicMock(return_value=0)
        # Skip the actual local UDP bind so the test doesn't collide with any
        # previously-bound ephemeral port — we only care about the outgoing
        # command string here.
        connection._setupUdpSocket = MagicMock(return_value=True)

        connection.streamFrames(["3d"], udp_port=22224)

        written = bytes(connection._socket.write.call_args_list[0][0][0])
        assert b"streamframes allframes udp:22224 3d" in written

    def test_udp_datagram_routed_to_packet_received(self, connection, qtbot):
        """A complete UDP data packet should arrive via packetReceived."""
        import struct

        from PySide6.QtNetwork import QHostAddress, QUdpSocket
        from qtm_rt.packet import QRTPacketType, RTheader

        assert connection._setupUdpSocket(0)
        connection._streaming = True
        port = connection._udp_socket.localPort()

        # Build a minimal RT data packet: RTheader + QRTPacket payload
        # (timestamp uint64, framenumber uint32, component_count uint32)
        payload = struct.pack("<QII", 12345, 42, 0)
        datagram = RTheader.pack(RTheader.size + len(payload), QRTPacketType.PacketData.value) + payload

        sender = QUdpSocket()
        with qtbot.waitSignal(connection.packetReceived, timeout=2000) as blocker:
            sender.writeDatagram(datagram, QHostAddress.LocalHost, port)

        packet = blocker.args[0]
        assert packet.framenumber == 42
        assert packet.timestamp == 12345
        sender.close()
        connection._teardownUdpSocket()


class TestQTMConnectionConnectTimeout:
    """Test the connect-timeout timer started by connectToHost."""

    def test_on_connect_timeout_aborts_and_emits_error(self, connection, qtbot):
        """When the timer fires and we're not connected, abort the socket and
        emit 'Connection timed out'."""
        connection._socket.abort = MagicMock()
        with qtbot.waitSignal(connection.error) as blocker:
            connection._onConnectTimeout()
        assert blocker.args[0] == "Connection timed out"
        connection._socket.abort.assert_called_once()

    def test_on_connect_timeout_noop_when_already_connected(self, connection, qtbot):
        """If the socket connected before the timer fired, the timeout handler
        should do nothing."""
        connection.isConnected = lambda: True
        connection._socket.abort = MagicMock()
        with qtbot.assertNotEmitted(connection.error, wait=50):
            connection._onConnectTimeout()
        connection._socket.abort.assert_not_called()

    def test_connect_timer_started_by_connect_to_host(self, connection):
        """connectToHost should arm the timer when timeout_ms > 0."""
        # Point at a documentation-only IP (RFC 5737) so we don't actually connect.
        # The timer state alone is what we assert.
        connection.connectToHost("192.0.2.1", port=22223, timeout_ms=10_000)
        assert connection._connect_timer.isActive()
        # Clean up so the timer doesn't linger into other tests.
        connection._socket.abort()
        connection._connect_timer.stop()

    def test_connect_timer_disabled_when_timeout_zero(self, connection):
        """timeout_ms=0 should skip arming the timer."""
        connection.connectToHost("192.0.2.1", port=22223, timeout_ms=0)
        assert not connection._connect_timer.isActive()
        connection._socket.abort()
