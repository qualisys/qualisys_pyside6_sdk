"""Instance tables that draw a QtmScene's published frame with Qt Quick 3D instancing.

Each type is a QQuick3DInstancing for one Model in the Qualisys.Scene layers:
set `scene` to a QtmScene and the table follows its frameChanged signal.

Two PySide6 facts these rely on:

- ``getInstanceBuffer(self)`` returns ``(QByteArray, count)``; each table entry
  is 20 little-endian floats (row0, row1, row2, color, custom data).
- Qt calls getInstanceBuffer() from the scene graph's render thread. The table
  is therefore swapped in as one tuple, built on the GUI thread. Never block the
  GUI thread in Python while the render thread may need the GIL: QTest.qWait()
  and QQuickWindow.grabWindow() called from Python deadlock against it;
  app.exec(), processEvents(), pytest-qt's qtbot.wait() and grabToImage() are
  fine (or set QSG_RENDER_LOOP=basic).
"""

import contextlib
import struct
from functools import lru_cache

from PySide6.QtCore import Property, QByteArray, QObject, Signal, Slot
from PySide6.QtGui import QColor, QQuaternion, QVector3D, QVector4D
from PySide6.QtQuick3D import QQuick3DInstancing

from ..math3d import AxisMapping, cross, length, matrix_columns, rotate, scale, sub
from ..skeleton import JOINT_COLOR, KEEL_COLOR, SIDE_COLORS, bone_width

_ENTRY = struct.Struct("<20f")  # row0, row1, row2, color, custom data
_NO_DATA = QVector4D()
_NO_ROTATION = QVector3D()
_UP = QVector3D(0, 1, 0)
_UNIT_AXES = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
AXIS_COLORS = ("#e15449", "#59b36b", "#5d82ea")  # X, Y, Z

# The built-in #Sphere and #Cylinder meshes are 100 units across (and tall)
_MESH = 100.0


@lru_cache(maxsize=512)
def _color(value) -> QColor:
    return QColor(value)


def _pack(e) -> bytes:
    r0, r1, r2, c, d = e.row0, e.row1, e.row2, e.color, e.instanceData
    return _ENTRY.pack(
        r0.x(), r0.y(), r0.z(), r0.w(), r1.x(), r1.y(), r1.z(), r1.w(),
        r2.x(), r2.y(), r2.z(), r2.w(), c.x(), c.y(), c.z(), c.w(), d.x(), d.y(), d.z(), d.w(),
    )  # fmt: skip


def _sphere(position: QVector3D, diameter: float, color: QColor):
    s = diameter / _MESH
    return QQuick3DInstancing.calculateTableEntry(position, QVector3D(s, s, s), _NO_ROTATION, color, _NO_DATA)


def _rod(start: QVector3D, direction: QVector3D, rod_length: float, thickness: float, color: QColor, rotation=None):
    """A #Cylinder from `start` along unit `direction` (scene coordinates)."""
    rotation = rotation if rotation is not None else QQuaternion.rotationTo(_UP, direction)
    s = thickness / _MESH
    return QQuick3DInstancing.calculateTableEntryFromQuaternion(
        start + direction * (rod_length / 2), QVector3D(s, rod_length / _MESH, s), rotation, color, _NO_DATA
    )


def _tripod(mapping, origin, axes, axis_length, thickness, colors):
    """Three rods along a frame's X, Y, Z axes (QTM directions), as QTM draws local axes."""
    start = mapping.vector(origin)
    for axis, color in zip(axes, colors, strict=False):
        direction = mapping.vector(axis).normalized()
        if not direction.isNull():
            yield _rod(start, direction, axis_length, thickness, color)


def _setting(type_, attribute, convert=None, *, notify, signal: str = "optionsChanged"):
    """A QML property that rebuilds the table when it changes.

    `notify` is the Signal of the class being defined and `signal` its name. It
    must be declared in that same class: PySide6 (6.12) crashes when QML compiles
    a property whose notify signal is inherited from a Python base class."""

    def getter(self):
        return getattr(self, attribute)

    def setter(self, value):
        value = convert(value) if convert is not None else value
        if value != getattr(self, attribute):
            setattr(self, attribute, value)
            getattr(self, signal).emit()
            self.refresh()

    return Property(type_, getter, setter, notify=notify)


def _colors(values) -> list[QColor]:
    return [_color(v) if isinstance(v, str) else QColor(v) for v in values or ()]


class SceneInstancing(QQuick3DInstancing):
    """Base: follows a QtmScene and rebuilds its table from the published frame.

    `active: false` (bind it to the Model's visibility) skips the work and draws nothing."""

    sceneChanged = Signal()
    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = None
        self._active = True
        self._table = (QByteArray(), 0)

    def _get_scene(self):
        return self._scene

    def _set_scene(self, scene):
        if scene is self._scene:
            return
        if self._scene is not None:
            for signal in (self._scene.frameChanged, self._scene.parametersChanged):
                with contextlib.suppress(RuntimeError, TypeError):
                    signal.disconnect(self.refresh)
        self._scene = scene
        if scene is not None:
            scene.frameChanged.connect(self.refresh)
            scene.parametersChanged.connect(self.refresh)
        self.sceneChanged.emit()
        self.refresh()

    scene = Property(QObject, _get_scene, _set_scene, notify=sceneChanged)

    active = _setting(bool, "_active", bool, notify=settingsChanged, signal="settingsChanged")

    @Property(int, notify=settingsChanged)
    def count(self):
        """Instances in the current table."""
        return self._table[1]

    @Slot()
    def refresh(self):
        frame = self._scene.frame if self._scene is not None and self._active else None
        entries = list(self.entries(frame)) if frame is not None else []
        old_count = self._table[1]
        if not entries and not old_count:
            return  # still empty: nothing for the render thread to pick up
        self._table = (QByteArray(b"".join(_pack(e) for e in entries)), len(entries))
        self.markDirty()
        if len(entries) != old_count:
            self.settingsChanged.emit()

    def entries(self, frame):
        """Table entries (QQuick3DInstancing.InstanceTableEntry) for a SceneFrame."""
        return ()

    def getInstanceBuffer(self):
        # C++ getInstanceBuffer(int *instanceCount): PySide6 returns (buffer, count).
        # Called from the render thread; the tuple is replaced whole on the GUI thread.
        return self._table


class MarkerInstancing(SceneInstancing):
    """Markers as spheres (use with source: "#Sphere").

    kind: "labeled" (QTM label colors) or "unlabeled" (`color`). Highlighted and
    hovered markers grow by `highlightScale`."""

    optionsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "labeled"
        self._size = 24.0
        self._highlight_scale = 1.5
        self._marker_color = _color("#767676")

    kind = _setting(str, "_kind", str, notify=optionsChanged)
    size = _setting(float, "_size", float, notify=optionsChanged)
    highlightScale = _setting(float, "_highlight_scale", float, notify=optionsChanged)
    color = _setting(QColor, "_marker_color", QColor, notify=optionsChanged)

    def entries(self, frame):
        mapping, size = frame.mapping, self._size
        highlighted = self._scene.highlight_set()
        if self._kind == "unlabeled":
            for marker_id, x, y, z in frame.unlabeled:
                if x == x:  # not NaN
                    big = f"Unlabeled #{marker_id}" in highlighted
                    yield _sphere(
                        mapping.vector((x, y, z)), size * (self._highlight_scale if big else 1), self._marker_color
                    )
            return
        colors = frame.parameters.colors
        for i, (name, p) in enumerate(zip(frame.labels, frame.labeled, strict=True)):
            if p[0] == p[0]:
                color = _color(colors[i]) if i < len(colors) else self._marker_color
                big = name in highlighted
                yield _sphere(mapping.vector(p), size * (self._highlight_scale if big else 1), color)


class BoneInstancing(SceneInstancing):
    """QTM's bones between labeled markers as thin capsules, in the bones' QTM colors.

    part: "shaft" (use with "#Cylinder") or "caps" (with "#Sphere"): the rounded
    ends, so the pair draws exact capsules `thickness` mm across."""

    optionsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._part = "shaft"
        self._thickness = 6.0

    part = _setting(str, "_part", str, notify=optionsChanged)
    thickness = _setting(float, "_thickness", float, notify=optionsChanged)

    def entries(self, frame):
        mapping, t = frame.mapping, self._thickness
        for start, end, color in frame.user_bones:
            if start[0] != start[0] or end[0] != end[0]:
                continue
            c = _color(color)
            if self._part == "caps":
                yield _sphere(mapping.vector(start), t, c)
                yield _sphere(mapping.vector(end), t, c)
                continue
            a, b = mapping.vector(start), mapping.vector(end)
            d = b - a
            n = d.length()
            if n > 1e-3:
                yield _rod(a, d / n, n, t, c)


class SkeletonInstancing(SceneInstancing):
    """Solved skeletons: bones in side colors, their ridges, joints and local axes.

    part:
      "bones"  - one per bone. With style "keeled" / "octahedral" use it with a
                 KeelBoneGeometry; with "capsule" / "stick" with "#Cylinder".
      "keels"  - the light ridge stripe (style "keeled" only), with
                 KeelBoneGeometry { part: "keel" }: same transforms as "bones".
      "caps"   - rounded ends for style "capsule" ("#Sphere").
      "joints" - white spheres ("#Sphere").
      "axes"   - local X / Y / Z tripods ("#Cylinder"), per `axesMode`:
                 "none", "selected" (highlighted or hovered joints, or every joint
                 of a highlighted skeleton) or "all".

    Bone width (ring radius) is clamp(0.11 x length, 14, 40) mm."""

    optionsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._part = "bones"
        self._style = "keeled"
        self._axes_mode = "none"
        self._joint_size = 22.0
        self._stick_width = 8.0
        self._axis_length = 90.0
        self._axis_thickness = 5.0
        self._highlight_scale = 1.5
        self._left = _color(SIDE_COLORS["left"])
        self._right = _color(SIDE_COLORS["right"])
        self._center = _color(SIDE_COLORS["center"])
        self._keel = _color(KEEL_COLOR)
        self._joint = _color(JOINT_COLOR)
        self._axis_colors = _colors(AXIS_COLORS)

    _n = optionsChanged
    part = _setting(str, "_part", str, notify=_n)
    style = _setting(str, "_style", str, notify=_n)
    axesMode = _setting(str, "_axes_mode", str, notify=_n)
    jointSize = _setting(float, "_joint_size", float, notify=_n)
    stickWidth = _setting(float, "_stick_width", float, notify=_n)
    axisLength = _setting(float, "_axis_length", float, notify=_n)
    axisThickness = _setting(float, "_axis_thickness", float, notify=_n)
    highlightScale = _setting(float, "_highlight_scale", float, notify=_n)
    leftColor = _setting(QColor, "_left", QColor, notify=_n)
    rightColor = _setting(QColor, "_right", QColor, notify=_n)
    centerColor = _setting(QColor, "_center", QColor, notify=_n)
    keelColor = _setting(QColor, "_keel", QColor, notify=_n)
    jointColor = _setting(QColor, "_joint", QColor, notify=_n)
    axisColors = _setting(list, "_axis_colors", _colors, notify=_n)
    del _n

    def _side_color(self, side: str) -> QColor:
        return self._left if side == "left" else self._right if side == "right" else self._center

    def entries(self, frame):
        part = self._part
        if part == "joints":
            yield from self._joints(frame)
        elif part == "axes":
            yield from self._axes(frame)
        elif part in ("bones", "keels", "caps"):
            yield from self._bones(frame)

    def _bones(self, frame):
        part, style, mapping = self._part, self._style, frame.mapping
        keel_shape = style in ("keeled", "octahedral")
        if (part == "keels" and style != "keeled") or (part == "caps" and style != "capsule"):
            return
        for start, end, keel, side in frame.skeleton_bones:
            direction = sub(end, start)
            n = length(direction)
            if n < 1.0:
                continue
            y_axis = scale(direction, 1 / n)
            w = bone_width(n)
            if keel_shape:
                rotation = mapping.frame_rotation(cross(y_axis, keel), y_axis, keel)
                color = self._keel if part == "keels" else self._side_color(side)
                yield QQuick3DInstancing.calculateTableEntryFromQuaternion(
                    mapping.vector(start), QVector3D(w, n, w), rotation, color, _NO_DATA
                )
                continue
            thickness = 0.9 * w if style == "capsule" else self._stick_width
            color = self._side_color(side)
            if part == "caps":
                yield _sphere(mapping.vector(start), thickness, color)
                yield _sphere(mapping.vector(end), thickness, color)
            else:
                rotation = mapping.frame_rotation(cross(y_axis, keel), y_axis, keel)
                yield _rod(mapping.vector(start), mapping.vector(y_axis), n, thickness, color, rotation)

    def _joints(self, frame):
        mapping, highlighted = frame.mapping, self._scene.highlight_set()
        for name, p, _q in frame.joints:
            if p[0] == p[0]:
                big = self._scene.is_highlighted(name, highlighted)
                yield _sphere(mapping.vector(p), self._joint_size * (self._highlight_scale if big else 1), self._joint)

    def _axes(self, frame):
        if self._axes_mode not in ("all", "selected"):
            return
        mapping, highlighted = frame.mapping, self._scene.highlight_set()
        for name, p, q in frame.joints:
            if q is None or p[0] != p[0]:
                continue
            if self._axes_mode == "selected" and not self._scene.is_highlighted(name, highlighted):
                continue
            axes = [rotate(q, axis) for axis in _UNIT_AXES]
            yield from _tripod(mapping, p, axes, self._axis_length, self._axis_thickness, self._axis_colors)


class RigidBodyInstancing(SceneInstancing):
    """Rigid bodies (6D): part "axes" draws each body's local X / Y / Z ("#Cylinder"),
    part "origin" a sphere in the body's QTM color ("#Sphere")."""

    optionsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._part = "axes"
        self._axis_length = 120.0
        self._axis_thickness = 6.0
        self._origin_size = 22.0
        self._highlight_scale = 1.5
        self._axis_colors = _colors(AXIS_COLORS)

    _n = optionsChanged
    part = _setting(str, "_part", str, notify=_n)
    axisLength = _setting(float, "_axis_length", float, notify=_n)
    axisThickness = _setting(float, "_axis_thickness", float, notify=_n)
    originSize = _setting(float, "_origin_size", float, notify=_n)
    highlightScale = _setting(float, "_highlight_scale", float, notify=_n)
    axisColors = _setting(list, "_axis_colors", _colors, notify=_n)
    del _n

    def entries(self, frame):
        mapping, highlighted = frame.mapping, self._scene.highlight_set()
        colors = [b.color for b in frame.parameters.bodies]
        for i, (name, p, matrix) in enumerate(frame.rigid_bodies):
            if p[0] != p[0]:
                continue
            k = self._highlight_scale if name in highlighted else 1.0
            if self._part == "origin":
                color = _color(colors[i]) if i < len(colors) else _color("#e0e0e0")
                yield _sphere(mapping.vector(p), self._origin_size * k, color)
            else:
                axes = matrix_columns(matrix)
                yield from _tripod(mapping, p, axes, self._axis_length * k, self._axis_thickness, self._axis_colors)


class AxesInstancing(SceneInstancing):
    """QTM's global X / Y / Z axes at the origin ("#Cylinder"), honouring AxisUpwards."""

    optionsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._axis_length = 500.0
        self._axis_thickness = 8.0
        self._axis_colors = _colors(AXIS_COLORS)
        self._key = None  # what the current table was built for

    _n = optionsChanged
    axisLength = _setting(float, "_axis_length", float, notify=_n)
    axisThickness = _setting(float, "_axis_thickness", float, notify=_n)
    axisColors = _setting(list, "_axis_colors", _colors, notify=_n)
    del _n

    @Slot()
    def refresh(self):
        # Drawn with or without a frame, and only rebuilt when AxisUpwards or a setting changes
        mapping = self._scene.mapping if self._scene is not None else AxisMapping("+Z")
        colors = tuple(c.name() for c in self._axis_colors)
        key = (self._active, mapping.axis_upwards, self._axis_length, self._axis_thickness, colors)
        if key == self._key:
            return
        self._key = key
        entries = []
        if self._active:
            origin = (0.0, 0.0, 0.0)
            entries = list(
                _tripod(mapping, origin, _UNIT_AXES, self._axis_length, self._axis_thickness, self._axis_colors)
            )
        self._table = (QByteArray(b"".join(_pack(e) for e in entries)), len(entries))
        self.markDirty()


__all__ = [
    "AXIS_COLORS",
    "AxesInstancing",
    "BoneInstancing",
    "MarkerInstancing",
    "RigidBodyInstancing",
    "SceneInstancing",
    "SkeletonInstancing",
]
