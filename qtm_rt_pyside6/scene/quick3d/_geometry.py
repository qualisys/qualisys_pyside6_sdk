"""Procedural geometry: the keeled / octahedral skeleton bone and the floor grid."""

import struct

from PySide6.QtCore import Property, QByteArray, Signal
from PySide6.QtGui import QVector3D
from PySide6.QtQuick3D import QQuick3DGeometry

from ..math3d import cross, dot, sub, unit

BONE_STYLES = ("keeled", "octahedral")

# Keeled bone shape, as a fraction of the bone length (height) and the ring radius
RING_HEIGHT = 0.12  # the ring sits at 12% of the bone's length
CHAMFER = 0.34  # how far the three blunt corners are cut back toward their neighbours
KEEL_OUT = 1.55  # the sharp corner (the ridge) sticks out to 1.55x the ring radius
STRIPE = 0.22  # the light stripe spans 22% of the way to the ridge's neighbours


def keel_bone_triangles(style: str = "keeled"):
    """Triangles of a unit bone from (0,0,0) to (0,1,0), tagged "body" or "keel".

    The ring (radius 1 at y=0.12) has corners on +-X and +-Z. "keeled": +Z is the
    sharp, raised ridge and the other three are chamfered; two extra points close
    to the ridge make the "keel" faces a narrow stripe. "octahedral": a plain
    four-cornered ring (Blender's bone), all "body"."""
    corners = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]  # (x, z); index 1 = +Z = ridge
    ring, sharp = [], None
    if style == "octahedral":
        ring = list(corners)
    else:
        for i, (px, pz) in enumerate(corners):
            if i == 1:
                sharp = len(ring)
                ring.append((px * KEEL_OUT, pz * KEEL_OUT))
                continue
            (ax, az), (bx, bz) = corners[i - 1], corners[(i + 1) % 4]
            ring.append((px + CHAMFER * (ax - px), pz + CHAMFER * (az - pz)))
            ring.append((px + CHAMFER * (bx - px), pz + CHAMFER * (bz - pz)))
        (kx, kz), (ax, az), (bx, bz) = ring[sharp], ring[sharp - 1], ring[sharp + 1]
        ring[sharp : sharp + 1] = [
            (kx + STRIPE * (ax - kx), kz + STRIPE * (az - kz)),
            (kx, kz),
            (kx + STRIPE * (bx - kx), kz + STRIPE * (bz - kz)),
        ]
        sharp += 1

    head, tail = (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    triangles = []
    for i in range(len(ring)):
        j = (i + 1) % len(ring)
        a, b = (ring[i][0], RING_HEIGHT, ring[i][1]), (ring[j][0], RING_HEIGHT, ring[j][1])
        part = "keel" if sharp is not None and sharp in (i, j) else "body"
        triangles.append((head, a, b, part))
        triangles.append((tail, b, a, part))
    return triangles


class KeelBoneGeometry(QQuick3DGeometry):
    """Flat-shaded unit skeleton bone from (0,0,0) to (0,1,0), ring radius 1.

    `style` is "keeled" or "octahedral"; `part` selects the "body" or the light
    "keel" (ridge) faces. Draw both parts with the same instance transforms."""

    styleChanged = Signal()
    partChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._style = "keeled"
        self._part = "body"
        self._build()

    def _get_style(self):
        return self._style

    def _set_style(self, style):
        style = style if style in BONE_STYLES else "keeled"
        if style != self._style:
            self._style = style
            self._build()
            self.styleChanged.emit()

    style = Property(str, _get_style, _set_style, notify=styleChanged)

    def _get_part(self):
        return self._part

    def _set_part(self, part):
        if part != self._part:
            self._part = part
            self._build()
            self.partChanged.emit()

    part = Property(str, _get_part, _set_part, notify=partChanged)

    def _build(self):
        data = bytearray()
        for a, b, c, part in keel_bone_triangles(self._style):
            if part != self._part:
                continue
            normal = unit(cross(sub(b, a), sub(c, a)))
            centroid = tuple((a[k] + b[k] + c[k]) / 3 for k in range(3))
            if dot(normal, (centroid[0], 0.0, centroid[2])) < 0:  # face away from the bone axis
                b, c, normal = c, b, (-normal[0], -normal[1], -normal[2])
            for p in (a, b, c):
                data += struct.pack("<6f", *p, *normal)
        attribute = QQuick3DGeometry.Attribute
        self.clear()
        self.setVertexData(QByteArray(bytes(data)))
        self.setStride(24)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(attribute.Semantic.PositionSemantic, 0, attribute.ComponentType.F32Type)
        self.addAttribute(attribute.Semantic.NormalSemantic, 12, attribute.ComponentType.F32Type)
        extent = KEEL_OUT + 0.05
        self.setBounds(QVector3D(-extent, 0, -extent), QVector3D(extent, 1, extent))
        self.update()


class GridGeometry(QQuick3DGeometry):
    """Lines of a square floor grid in the scene's XZ plane (y = 0), centred on the origin.

    `size` and `spacing` are in scene units (mm). Lines whose index is a multiple
    of `skipEvery` are left out, so a second, coarser grid can draw them instead."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._size = 10000.0
        self._spacing = 500.0
        self._skip_every = 0
        self._build()

    def _update(self, name, value):
        if value != getattr(self, name):
            setattr(self, name, value)
            self._build()
            self.changed.emit()

    def _get_size(self):
        return self._size

    def _set_size(self, value):
        self._update("_size", float(value))

    size = Property(float, _get_size, _set_size, notify=changed)

    def _get_spacing(self):
        return self._spacing

    def _set_spacing(self, value):
        self._update("_spacing", float(value))

    spacing = Property(float, _get_spacing, _set_spacing, notify=changed)

    def _get_skip_every(self):
        return self._skip_every

    def _set_skip_every(self, value):
        self._update("_skip_every", int(value))

    skipEvery = Property(int, _get_skip_every, _set_skip_every, notify=changed)

    def _build(self):
        half = self._size / 2
        n = int(half // self._spacing) if self._spacing > 0 else 0
        data = bytearray()
        for i in range(-n, n + 1):
            if self._skip_every and i % self._skip_every == 0:
                continue
            v = i * self._spacing
            data += struct.pack("<6f", v, 0.0, -half, v, 0.0, half)
            data += struct.pack("<6f", -half, 0.0, v, half, 0.0, v)
        attribute = QQuick3DGeometry.Attribute
        self.clear()
        self.setVertexData(QByteArray(bytes(data)))
        self.setStride(12)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Lines)
        self.addAttribute(attribute.Semantic.PositionSemantic, 0, attribute.ComponentType.F32Type)
        self.setBounds(QVector3D(-half, -1, -half), QVector3D(half, 1, half))
        self.update()
