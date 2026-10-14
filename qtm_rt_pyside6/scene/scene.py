"""QtmScene: QTM parameters plus the latest frame, ready for a 3D view.

    connection = QTMConnection()
    scene = QtmScene(connection)       # requests parameters, then streams
    connection.connectToHost("127.0.0.1")

The scene asks QTM for its 3D, 6D and skeleton parameters when connected,
starts streaming the components it needs, and asks again after QTM events
that may change them (capture started, file playback, calibration) or when
the stream no longer matches them.

Frames arrive at QTM's rate; the latest one wins and is published at 60 Hz
(``frameChanged``), which is what views redraw from. ``frameReceived`` fires
for every frame, for app logic that must not miss one (alarms, recording).

Only QtCore / QtGui are used here; the Qt Quick 3D layers that draw a scene
live in :mod:`qtm_rt_pyside6.scene.quick3d`.
"""

import contextlib
import logging
import math
import xml.etree.ElementTree as ET

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QElapsedTimer,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QVector3D
from qtm_rt.packet import QRTEvent

from .frame import SceneFrame
from .math3d import AxisMapping
from .parameters import SceneParameters, parse_parameters

LOG = logging.getLogger("qtm_rt_pyside6")

DEFAULT_COMPONENTS = ("3d", "3dnolabels", "6d", "skeleton:global")
PARAMETER_NAMES = ("3d", "6d", "skeleton")

# QTM events after which the labels, bodies or skeletons may have changed
PARAMETER_EVENTS = frozenset(
    {
        QRTEvent.EventConnected,
        QRTEvent.EventCaptureStarted,
        QRTEvent.EventRTfromFileStarted,
        QRTEvent.EventCalibrationStopped,
        QRTEvent.EventCameraSettingsChanged,
        QRTEvent.EventReprocessingStopped,
    }
)

# A frame that no longer matches the parameters asks for them again at most this often
MISMATCH_REFRESH_MS = 2000

# A pick selects the point closest in angle to the ray, if within this many degrees
DEFAULT_PICK_TOLERANCE = 1.2


class PointModel(QAbstractListModel):
    """Named points of the published frame for 2D overlays (labels): labeled markers,
    skeleton joints and rigid bodies, in that order. Positions are scene coordinates."""

    NameRole = Qt.UserRole + 1
    KindRole = Qt.UserRole + 2
    PositionRole = Qt.UserRole + 3
    ValidRole = Qt.UserRole + 4
    ColorRole = Qt.UserRole + 5
    HighlightedRole = Qt.UserRole + 6
    _ROLES = {
        NameRole: b"name",
        KindRole: b"kind",
        PositionRole: b"position",
        ValidRole: b"valid",
        ColorRole: b"color",
        HighlightedRole: b"highlighted",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        column = role - self.NameRole
        row = self._rows[index.row()]
        return row[column] if 0 <= column < len(row) else None

    def roleNames(self):
        return {role: QByteArray(name) for role, name in self._ROLES.items()}

    def set_rows(self, rows: list[tuple]):
        # Reset only when the points themselves change; otherwise update in place
        if [r[:2] for r in rows] != [r[:2] for r in self._rows]:
            self.beginResetModel()
            self._rows = rows
            self.endResetModel()
        elif rows:
            self._rows = rows
            self.dataChanged.emit(self.index(0), self.index(len(rows) - 1), list(self._ROLES)[2:])


class QtmScene(QObject):
    """QTM parameters and the latest frame, for 3D views and app logic.

    Args:
        connection: a QTMConnection to attach to, or None (attach later, or feed
            the scene yourself with setParameters() / pushFrame(), e.g. from DemoSource).
        components: what to stream once the parameters are in.
        publish_rate: how often (Hz) the latest frame is published to views.
        auto_stream: start streaming when the parameters arrive. Pass False when
            the app calls connection.streamFrames() itself; include "3d",
            "3dnolabels", "6d" and/or "skeleton:global" for the scene to show them.
    """

    parametersChanged = Signal()
    frameChanged = Signal()  # the published frame changed (at most publish_rate times a second)
    frameReceived = Signal(object)  # every frame as a SceneFrame, for app logic
    highlightChanged = Signal()
    hoveredChanged = Signal()
    connectedChanged = Signal()
    statsChanged = Signal()  # fps, frameNumber, markerCount, hasData
    firstData = Signal()  # first published frame with any tracked point since the scene was cleared
    pickToleranceChanged = Signal()

    def __init__(
        self,
        connection=None,
        parent: QObject | None = None,
        *,
        components=DEFAULT_COMPONENTS,
        publish_rate: int = 60,
        auto_stream: bool = True,
    ):
        super().__init__(parent)
        self._components = list(components)
        self._auto_stream = auto_stream
        self._connection = None
        self._connected = False
        self._streaming = False

        self._parameters = SceneParameters()
        self._mapping = AxisMapping(self._parameters.axis_upwards)
        self._latest: SceneFrame | None = None
        self._frame: SceneFrame | None = None
        self._dirty = False
        self._awaiting_data = True

        self._highlighted: list[str] = []
        self._highlight_set: frozenset[str] = frozenset()
        self._hovered = ""
        self._pick_tolerance = DEFAULT_PICK_TOLERANCE

        self._fps = 0
        self._frames_this_second = 0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_request_ms = -1e12

        self._points = PointModel(self)

        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(max(1, round(1000 / max(1, publish_rate))))
        self._publish_timer.timeout.connect(self._publish)
        self._publish_timer.start()

        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start()

        if connection is not None:
            self.attach(connection)

    # =====================================================================
    # Python API
    # =====================================================================

    @property
    def connection(self):
        return self._connection

    @property
    def parameters(self) -> SceneParameters:
        return self._parameters

    @property
    def mapping(self) -> AxisMapping:
        """QTM -> scene coordinates for the current AxisUpwards."""
        return self._mapping

    @property
    def frame(self) -> SceneFrame | None:
        """The published frame: what views show right now."""
        return self._frame

    @property
    def latest_frame(self) -> SceneFrame | None:
        """The most recently received frame (may be newer than `frame`)."""
        return self._latest

    def highlight_set(self) -> frozenset[str]:
        """Highlighted names plus the hovered one."""
        return self._highlight_set | {self._hovered} if self._hovered else self._highlight_set

    def is_highlighted(self, name: str, highlighted: frozenset[str] | None = None) -> bool:
        """A name is highlighted when it or, for a joint, its skeleton is."""
        names = self.highlight_set() if highlighted is None else highlighted
        return name in names or (":" in name and name.split(":", 1)[0] in names)

    def attach(self, connection):
        """Follow a QTMConnection: parameters on connect and on QTM events, frames while streaming."""
        self.detach()
        self._connection = connection
        connection.connected.connect(self._on_connected)
        connection.disconnected.connect(self._on_disconnected)
        connection.packetReceived.connect(self._on_packet)
        connection.eventReceived.connect(self._on_event)
        connection.responseReceived.connect(self._on_response)
        if connection.isConnected():
            self._on_connected()

    def detach(self):
        connection, self._connection = self._connection, None
        if connection is None:
            return
        for signal, slot in (
            (connection.connected, self._on_connected),
            (connection.disconnected, self._on_disconnected),
            (connection.packetReceived, self._on_packet),
            (connection.eventReceived, self._on_event),
            (connection.responseReceived, self._on_response),
        ):
            with contextlib.suppress(RuntimeError, TypeError):
                signal.disconnect(slot)
        self._set_connected(False)
        self._streaming = False

    def setParameters(self, parameters):
        """Use these definitions (SceneParameters, or parameter XML as a string)."""
        if isinstance(parameters, (str, bytes)):
            parameters = parse_parameters(parameters, self._parameters)
        self._parameters = parameters
        self._mapping = AxisMapping(parameters.axis_upwards)
        if self._latest is not None:  # redraw the last frame with the new names and colors
            self._latest = self._latest.with_parameters(parameters)
        self._dirty = True
        self.parametersChanged.emit()

    def pushFrame(self, frame: SceneFrame):
        """Feed a frame (from a packet, a simulation or a file). It is published on the next tick."""
        self._latest = frame
        self._dirty = True
        self._frames_this_second += 1
        self.frameReceived.emit(frame)

    # =====================================================================
    # QML API
    # =====================================================================

    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._connected

    @Property(bool, notify=connectedChanged)
    def streaming(self):
        return self._streaming

    @Property(int, notify=statsChanged)
    def fps(self):
        return self._fps

    @Property(int, notify=statsChanged)
    def frameNumber(self):
        return self._frame.frame_number if self._frame is not None else 0

    @Property(int, notify=statsChanged)
    def markerCount(self):
        return self._frame.marker_count if self._frame is not None else 0

    @Property(bool, notify=statsChanged)
    def hasData(self):
        return self._frame is not None and bool(self._frame.points())

    @Property(list, notify=parametersChanged)
    def labels(self):
        return list(self._parameters.labels)

    @Property(list, notify=parametersChanged)
    def jointNames(self):
        return self._parameters.joint_names()

    @Property(list, notify=parametersChanged)
    def bodyNames(self):
        return self._parameters.body_names()

    @Property(list, notify=parametersChanged)
    def skeletonNames(self):
        return [s.name for s in self._parameters.skeletons]

    @Property(int, notify=parametersChanged)
    def boneCount(self):
        return len(self._parameters.bones)

    @Property(str, notify=parametersChanged)
    def axisUpwards(self):
        return self._mapping.axis_upwards

    @Property(QObject, constant=True)
    def pointModel(self):
        return self._points

    def _get_highlighted(self):
        return list(self._highlighted)

    def _set_highlighted(self, names):
        names = [str(n) for n in (names or []) if n]
        if names != self._highlighted:
            self._highlighted = names
            self._highlight_set = frozenset(names)
            self._dirty = True
            self.highlightChanged.emit()

    highlighted = Property(list, _get_highlighted, _set_highlighted, notify=highlightChanged)

    def _get_hovered(self):
        return self._hovered

    def _set_hovered(self, name):
        name = name or ""
        if name != self._hovered:
            self._hovered = name
            self._dirty = True
            self.hoveredChanged.emit()

    hovered = Property(str, _get_hovered, _set_hovered, notify=hoveredChanged)

    def _get_pick_tolerance(self):
        return self._pick_tolerance

    def _set_pick_tolerance(self, degrees):
        if degrees != self._pick_tolerance:
            self._pick_tolerance = float(degrees)
            self.pickToleranceChanged.emit()

    pickTolerance = Property(float, _get_pick_tolerance, _set_pick_tolerance, notify=pickToleranceChanged)

    @Slot(list)
    def highlight(self, names):
        """Highlight markers, joints, skeletons (all their joints) or rigid bodies by name."""
        self._set_highlighted(names)

    @Slot()
    def clearHighlight(self):
        self._set_highlighted([])

    @Slot(QVector3D, QVector3D, result=str)
    @Slot(QVector3D, QVector3D, list, result=str)
    def pick(self, origin: QVector3D, direction: QVector3D, kinds=None) -> str:
        """The point closest in angle to a ray (scene coordinates, e.g. from View3D.mapTo3DScene),
        within pickTolerance degrees: a label, joint, rigid body or "Unlabeled #<id>"; "" for none.

        `kinds` limits the candidates to "marker", "unlabeled", "joint" and "body" points,
        e.g. {"marker", "joint"} from Python or ["marker", "joint"] from QML."""
        frame = self._frame
        if frame is None or direction.isNull():
            return ""
        o = self._mapping.from_scene((origin.x(), origin.y(), origin.z()))
        d = direction.normalized()
        dx, dy, dz = self._mapping.from_scene((d.x(), d.y(), d.z()))
        best, best_angle = "", math.radians(self._pick_tolerance)
        for name, kind, (x, y, z) in frame.points():
            if kinds is not None and kind not in kinds:
                continue
            wx, wy, wz = x - o[0], y - o[1], z - o[2]
            along = wx * dx + wy * dy + wz * dz
            if along <= 0:
                continue
            perp = math.sqrt(max(0.0, wx * wx + wy * wy + wz * wz - along * along))
            angle = math.atan2(perp, along)
            if angle < best_angle:
                best, best_angle = name, angle
        return best

    @Slot(str, result=str)
    def kindOf(self, name: str) -> str:
        """What a name refers to: "marker", "unlabeled", "joint", "body", "skeleton", or "" when unknown."""
        p = self._parameters
        if name in p.labels:
            return "marker"
        if name in p.body_names():
            return "body"
        if name in (s.name for s in p.skeletons):
            return "skeleton"
        if name in p.joint_names():
            return "joint"
        if name.startswith("Unlabeled #"):
            return "unlabeled"
        return ""

    @Slot(result=list)
    def bounds(self) -> list:
        """[x, y, z, radius] of the tracked points in scene coordinates, or [] when there are none."""
        frame = self._frame
        points = [p for _n, _k, p in frame.points()] if frame is not None else []
        if not points:
            return []
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        center = self._mapping.to_scene(tuple((a + b) / 2 for a, b in zip(lo, hi, strict=True)))
        return [center[0], center[1], center[2], math.dist(lo, hi) / 2]

    @Slot(str, result=list)
    def scenePosition(self, name: str) -> list:
        """[x, y, z] scene position of a named point in the published frame, or [] when missing."""
        if self._frame is None or not name:
            return []
        p = self._frame.position(name)
        return [] if math.isnan(p[0]) else list(self._mapping.to_scene(p))

    @Slot(float, float, float, result=QVector3D)
    def toScene(self, x: float, y: float, z: float) -> QVector3D:
        """QTM position or direction -> scene coordinates."""
        return self._mapping.vector((x, y, z))

    @Slot()
    def refreshParameters(self):
        """Ask QTM for the 3D, 6D and skeleton parameters again."""
        if self._connection is not None and self._connection.isConnected():
            self._last_request_ms = self._clock.elapsed()
            self._connection.getParameters(list(PARAMETER_NAMES))

    @Slot()
    def clear(self):
        """Forget the parameters and frames (e.g. on disconnect)."""
        self._latest = None
        self.setParameters(SceneParameters())
        self._awaiting_data = True
        self._publish()  # views go empty now, not on the next tick

    # =====================================================================
    # Connection
    # =====================================================================

    def _set_connected(self, on: bool):
        if on != self._connected:
            self._connected = on
            self.connectedChanged.emit()

    def _on_connected(self):
        self._streaming = False
        self._set_connected(True)
        self.refreshParameters()

    def _on_disconnected(self):
        self._streaming = False
        self._set_connected(False)
        self.clear()

    def _on_response(self, _command: str, data):
        # Match parameter XML by content rather than by command name: replies can
        # be attributed to an earlier queued command while streaming.
        if not (isinstance(data, str) and "<QTM_Parameters" in data):
            return
        try:
            self.setParameters(parse_parameters(data, self._parameters))
        except ET.ParseError as e:
            LOG.warning("Could not parse QTM parameters: %s", e)
            return
        if self._auto_stream and not self._streaming and self._connection is not None:
            self._streaming = True
            self._connection.streamFrames(list(self._components))
            self.connectedChanged.emit()

    def _on_event(self, event):
        if event in PARAMETER_EVENTS:
            self.refreshParameters()

    def _on_packet(self, packet):
        self.pushFrame(SceneFrame.from_packet(packet, self._parameters))

    # =====================================================================
    # Publishing
    # =====================================================================

    def _publish(self):
        if not self._dirty:
            return
        self._dirty = False
        frame = self._frame = self._latest
        if (
            frame is not None
            and frame.mismatched()
            and self._clock.elapsed() - self._last_request_ms > MISMATCH_REFRESH_MS
        ):
            self.refreshParameters()
        self._update_points()
        self.frameChanged.emit()
        self.statsChanged.emit()
        if self._awaiting_data and frame is not None and frame.points():
            self._awaiting_data = False
            self.firstData.emit()

    def _update_points(self):
        frame = self._frame
        if frame is None:
            self._points.set_rows([])
            return
        to_scene, highlighted = self._mapping.to_scene, self.highlight_set()
        p = self._parameters
        colors = p.colors
        rows = []

        def add(name, kind, pos, color):
            valid = not math.isnan(pos[0])
            rows.append(
                (
                    name,
                    kind,
                    QVector3D(*to_scene(pos)) if valid else QVector3D(),
                    valid,
                    color,
                    self.is_highlighted(name, highlighted),
                )
            )

        for i, (name, pos) in enumerate(zip(frame.labels, frame.labeled, strict=True)):
            add(name, "marker", pos, colors[i] if i < len(colors) else "#e0e0e0")
        for name, pos, _q in frame.joints:
            add(name, "joint", pos, "#ffffff")
        body_colors = [b.color for b in p.bodies]
        for i, (name, pos, _m) in enumerate(frame.rigid_bodies):
            add(name, "body", pos, body_colors[i] if i < len(body_colors) else "#e0e0e0")
        self._points.set_rows(rows)

    def _update_fps(self):
        if self._fps != self._frames_this_second:
            self._fps = self._frames_this_second
            self.statsChanged.emit()
        self._frames_this_second = 0
