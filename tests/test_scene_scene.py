"""QtmScene: parameters, streaming, publishing, picking (qtm_rt_pyside6.scene.scene)."""

import math

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QVector3D

from qtm_rt_pyside6 import QRTEvent
from qtm_rt_pyside6.scene import DEFAULT_COMPONENTS, DemoSource, QtmScene
from tests.scene_packets import IDENTITY_MATRIX, IDENTITY_QUAT, PARAMETERS_XML, build_packet


class FakeConnection(QObject):
    """The QTMConnection signals and calls QtmScene uses."""

    connected = Signal()
    disconnected = Signal()
    packetReceived = Signal(object)
    eventReceived = Signal(object)
    responseReceived = Signal(str, object)

    def __init__(self, is_connected=False):
        super().__init__()
        self.is_connected = is_connected
        self.requests: list[list[str]] = []
        self.streams: list[list[str]] = []

    def isConnected(self):
        return self.is_connected

    def getParameters(self, parameters):
        self.requests.append(list(parameters))

    def streamFrames(self, components):
        self.streams.append(list(components))

    def connect_(self):
        self.is_connected = True
        self.connected.emit()


def frame_packet(n=1, labeled=None):
    return build_packet(
        n,
        labeled=labeled if labeled is not None else [(0.0, 0.0, 1000.0), (100.0, 0.0, 1000.0), (200.0, 0.0, 1000.0)],
        unlabeled=[(0.0, 500.0, 0.0, 3)],
        bodies=[((500.0, 0.0, 1000.0), IDENTITY_MATRIX)],
        skeletons=[[(1, (0.0, 0.0, 950.0), IDENTITY_QUAT), (2, (-90.0, 0.0, 900.0), IDENTITY_QUAT)]],
    )


@pytest.fixture
def conn():
    return FakeConnection()


@pytest.fixture
def scene(qtbot, conn):
    s = QtmScene(conn)
    yield s
    s.detach()


def streaming_scene(qtbot, scene, conn):
    conn.connect_()
    with qtbot.waitSignal(scene.parametersChanged):
        conn.responseReceived.emit("getparameters", PARAMETERS_XML)
    return scene


class TestConnection:
    def test_requests_parameters_when_connected(self, scene, conn):
        conn.connect_()
        assert conn.requests == [["3d", "6d", "skeleton"]]
        assert scene.connected

    def test_attach_to_a_connected_connection(self, qtbot):
        conn = FakeConnection(is_connected=True)
        QtmScene(conn)
        assert conn.requests == [["3d", "6d", "skeleton"]]

    def test_streams_once_parameters_arrive(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        assert conn.streams == [list(DEFAULT_COMPONENTS)]
        assert scene.labels == ["Shoulder", "Elbow", "Wrist"]
        assert scene.streaming
        conn.responseReceived.emit("getparameters", PARAMETERS_XML)  # a refresh does not restart streaming
        assert len(conn.streams) == 1

    def test_parameters_matched_by_content_not_command(self, qtbot, scene, conn):
        conn.connect_()
        with qtbot.waitSignal(scene.parametersChanged):
            conn.responseReceived.emit("streamframes", PARAMETERS_XML)  # misattributed reply
        assert scene.bodyNames == ["Wand"]

    def test_malformed_xml_is_ignored(self, qtbot, scene, conn):
        conn.connect_()
        conn.responseReceived.emit("getparameters", "<QTM_Parameters_Ver_1.25><The_3D>")
        assert conn.streams == [] and scene.labels == []

    def test_no_auto_stream(self, qtbot):
        conn = FakeConnection()
        s = QtmScene(conn, auto_stream=False)
        conn.connect_()
        conn.responseReceived.emit("getparameters", PARAMETERS_XML)
        assert conn.streams == [] and s.labels == ["Shoulder", "Elbow", "Wrist"]

    @pytest.mark.parametrize("event", [QRTEvent.EventCaptureStarted, QRTEvent.EventRTfromFileStarted])
    def test_parameter_events_refresh(self, qtbot, scene, conn, event):
        streaming_scene(qtbot, scene, conn)
        conn.eventReceived.emit(event)
        assert len(conn.requests) == 2

    def test_other_events_do_not_refresh(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        conn.eventReceived.emit(QRTEvent.EventTrigger)
        assert len(conn.requests) == 1

    def test_disconnect_clears(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        conn.packetReceived.emit(frame_packet())
        qtbot.waitSignal(scene.frameChanged).wait()
        conn.is_connected = False
        conn.disconnected.emit()
        assert not scene.connected
        assert scene.frame is None and scene.labels == [] and scene.pointModel.rowCount() == 0


class TestFrames:
    def test_every_frame_signal_and_latest_wins(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        received = []
        scene.frameReceived.connect(received.append)
        with qtbot.waitSignal(scene.frameChanged):
            for n in (1, 2, 3):
                conn.packetReceived.emit(frame_packet(n))
        assert [f.frame_number for f in received] == [1, 2, 3]
        assert scene.frame.frame_number == 3 and scene.frameNumber == 3
        assert scene.markerCount == 4

    def test_first_data(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        with qtbot.waitSignal(scene.firstData):
            conn.packetReceived.emit(frame_packet())

    def test_mismatch_refreshes_parameters(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        scene._last_request_ms = -1e12  # as if the last request was long ago
        with qtbot.waitSignal(scene.frameChanged):
            conn.packetReceived.emit(frame_packet(labeled=[(0.0, 0.0, 0.0)] * 5))
        assert len(conn.requests) == 2
        with qtbot.waitSignal(scene.frameChanged):  # rate limited
            conn.packetReceived.emit(frame_packet(2, labeled=[(0.0, 0.0, 0.0)] * 5))
        assert len(conn.requests) == 2

    def test_point_model(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        with qtbot.waitSignal(scene.frameChanged):
            conn.packetReceived.emit(frame_packet())
        model = scene.pointModel
        names = [model.data(model.index(i), model.NameRole) for i in range(model.rowCount())]
        assert names == ["Shoulder", "Elbow", "Wrist", "S:Hips", "S:LeftUpLeg", "S:LeftLeg", "Wand"]
        assert model.data(model.index(0), model.PositionRole) == QVector3D(0, 1000, 0)  # (x, z, -y)
        assert model.data(model.index(5), model.ValidRole) is False


class TestQueries:
    @pytest.fixture
    def live(self, qtbot, scene, conn):
        streaming_scene(qtbot, scene, conn)
        with qtbot.waitSignal(scene.frameChanged):
            conn.packetReceived.emit(frame_packet())
        return scene

    def ray_to(self, target, origin=(0.0, -5000.0, 1000.0)):
        o = QVector3D(origin[0], origin[2], -origin[1])  # QTM -> scene, Z up
        t = QVector3D(target[0], target[2], -target[1])
        return o, t - o

    def test_pick_nearest_to_ray(self, live):
        assert live.pick(*self.ray_to((100.0, 0.0, 1000.0))) == "Elbow"
        assert live.pick(*self.ray_to((500.0, 0.0, 1000.0))) == "Wand"
        assert live.pick(*self.ray_to((0.0, 500.0, 0.0))) == "Unlabeled #3"

    def test_pick_tolerance(self, live):
        assert live.pick(*self.ray_to((100.0, 0.0, 1300.0))) == ""  # ~3.4 degrees off
        live.pickTolerance = 5
        assert live.pick(*self.ray_to((100.0, 0.0, 1300.0))) == "Elbow"

    def test_pick_behind_the_camera(self, live):
        o, d = self.ray_to((100.0, 0.0, 1000.0))
        assert live.pick(o, -d) == ""

    def test_pick_kinds(self, live):
        o, d = self.ray_to((0.0, 0.0, 975.0), origin=(0.0, -5000.0, 975.0))
        assert live.pick(o, d, kinds={"joint"}) == "S:Hips"

    def test_bounds(self, live):
        x, y, z, r = live.bounds()
        # QTM x -90..500, y 0..500, z 0..1000 -> centre (205, 250, 500) -> scene (205, 500, -250)
        assert (x, y, z) == pytest.approx((205.0, 500.0, -250.0))
        assert r == pytest.approx(math.dist((-90, 0, 0), (500, 500, 1000)) / 2)

    def test_scene_position(self, live):
        assert live.scenePosition("Wrist") == pytest.approx([200.0, 1000.0, 0.0])
        assert live.scenePosition("nothing") == []

    def test_highlight(self, qtbot, live):
        with qtbot.waitSignal(live.highlightChanged):
            live.highlight(["Elbow", "S"])
        assert live.highlighted == ["Elbow", "S"]
        assert live.is_highlighted("Elbow") and live.is_highlighted("S:Hips") and not live.is_highlighted("Wrist")
        live.hovered = "Wrist"
        assert live.is_highlighted("Wrist")
        live.clearHighlight()
        assert live.highlighted == []

    def test_kind_of(self, live):
        kinds = [live.kindOf(n) for n in ("Elbow", "Wand", "S", "S:Hips", "Unlabeled #3", "?")]
        assert kinds == ["marker", "body", "skeleton", "joint", "unlabeled", ""]

    def test_to_scene_honours_axis_upwards(self, live):
        assert live.toScene(1, 2, 3) == QVector3D(1, 3, -2)
        params = live.parameters
        params.axis_upwards = "+Y"
        live.setParameters(params)
        assert live.toScene(1, 2, 3) == QVector3D(1, 2, 3) and live.axisUpwards == "+Y"


class TestDemoSource:
    def test_feeds_and_clears(self, qtbot):
        scene = QtmScene()
        demo = DemoSource(scene)
        with qtbot.waitSignal(scene.firstData, timeout=2000):
            demo.start()
        assert demo.running
        assert scene.skeletonNames == ["Demo"] and scene.hasData
        with qtbot.waitSignal(scene.frameChanged, timeout=1000):
            pass
        assert scene.fps >= 0
        demo.stop()
        assert not demo.running and scene.frame is None and scene.labels == []
