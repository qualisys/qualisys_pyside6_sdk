"""Small vector and rotation helpers, and the QTM -> Qt Quick 3D coordinate mapping.

Vectors are plain ``(x, y, z)`` tuples and quaternions ``(x, y, z, w)`` tuples,
as QTM streams them, so the data layer needs no numpy. Only the final hand-over
to Qt builds ``QVector3D`` / ``QQuaternion``.

QTM can be calibrated with any axis pointing up (the ``AxisUpwards`` 3D
parameter: ``+Z`` by default). Qt Quick 3D is Y-up. :class:`AxisMapping`
turns QTM coordinates into scene coordinates with a *proper rotation*
(determinant +1), so directions, cross products and handedness carry over
unchanged and the floor is always the scene's XZ plane. For the usual ``+Z``
up it is ``(x, y, z) -> (x, z, -y)``.
"""

import math

from PySide6.QtGui import QQuaternion, QVector3D

NAN = math.nan
MISSING = (NAN, NAN, NAN)

# Rows are the scene X, Y, Z axes in QTM coordinates: scene = M @ qtm.
# Each is a proper rotation that takes QTM's up axis to scene +Y.
_UP_MATRICES = {
    "+Z": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    "-Z": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "+Y": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "-Y": ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
    "+X": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "-X": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
}
AXIS_UPWARDS = tuple(_UP_MATRICES)


# ---------------------------------------------------------------------------- vectors


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a) -> float:
    return math.sqrt(dot(a, a))


def unit(a):
    """``a`` scaled to length 1, or None when it is (nearly) zero."""
    n = length(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else None


def is_valid(p) -> bool:
    """False for QTM's "not tracked in this frame" (NaN) positions."""
    return not math.isnan(p[0])


# ---------------------------------------------------------------------------- quaternions (x, y, z, w)


def rotate(q, v):
    """Rotate vector v by unit quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (
        v[0] + w * tx + y * tz - z * ty,
        v[1] + w * ty + z * tx - x * tz,
        v[2] + w * tz + x * ty - y * tx,
    )


def quat_multiply(a, b):
    """Hamilton product a * b: rotate by b first, then by a."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_from_axis_angle(axis, degrees: float):
    """Unit quaternion (x, y, z, w) for a turn of `degrees` about `axis`."""
    ux, uy, uz = unit(axis) or (0.0, 0.0, 1.0)
    half = math.radians(degrees) / 2
    s = math.sin(half)
    return (ux * s, uy * s, uz * s, math.cos(half))


def matrix_columns(matrix):
    """The three columns (body X, Y, Z axes) of QTM's 6DOF rotation matrix.

    QTM streams the 3x3 matrix as 9 floats in column-major order, so each group
    of three is one of the body's local axes in QTM (world) coordinates."""
    m = tuple(matrix)
    return m[0:3], m[3:6], m[6:9]


# ---------------------------------------------------------------------------- QTM -> scene


class AxisMapping:
    """QTM coordinates -> Qt Quick 3D scene coordinates (Y-up), honouring AxisUpwards.

    Positions keep their units (mm), so scene units are millimetres."""

    def __init__(self, axis_upwards: str = "+Z"):
        axis_upwards = (axis_upwards or "+Z").strip().upper()
        if axis_upwards not in _UP_MATRICES:
            axis_upwards = "+Z"
        self.axis_upwards = axis_upwards
        self.matrix = _UP_MATRICES[axis_upwards]

    def __repr__(self):
        return f"AxisMapping({self.axis_upwards!r})"

    def to_scene(self, p):
        """QTM (x, y, z) -> scene (x, y, z) tuple."""
        r0, r1, r2 = self.matrix
        return (dot(r0, p), dot(r1, p), dot(r2, p))

    def from_scene(self, p):
        """Scene (x, y, z) -> QTM (x, y, z) tuple (the transpose: M is orthonormal)."""
        r0, r1, r2 = self.matrix
        return tuple(r0[i] * p[0] + r1[i] * p[1] + r2[i] * p[2] for i in range(3))

    def vector(self, p) -> QVector3D:
        """QTM (x, y, z) -> scene QVector3D."""
        return QVector3D(*self.to_scene(p))

    def frame_rotation(self, x_axis, y_axis, z_axis) -> QQuaternion:
        """Rotation that lays a model's local X, Y, Z axes onto three QTM directions.

        For geometry built in its own frame, e.g. a bone along local +Y: pass the
        bone's side, direction and ridge axes in QTM coordinates (R_scene = M R)."""
        return QQuaternion.fromAxes(self.vector(x_axis), self.vector(y_axis), self.vector(z_axis))

    def body_rotation(self, x_axis, y_axis, z_axis) -> QQuaternion:
        """Scene rotation of a QTM body whose local X, Y, Z axes are given in QTM coordinates.

        The body's own axes are mapped like the world's, R_scene = M R M^T, so a
        QTM body at rest is at rest in the scene and a turn about QTM up is a
        turn about scene +Y. Use this for models authored in QTM's convention."""
        r0, r1, r2 = self.matrix

        def column(row):  # R @ row
            return add(add(scale(x_axis, row[0]), scale(y_axis, row[1])), scale(z_axis, row[2]))

        return self.frame_rotation(column(r0), column(r1), column(r2))

    def quaternion(self, q) -> QQuaternion:
        """QTM rotation quaternion (x, y, z, w) -> scene QQuaternion (see body_rotation)."""
        return self.body_rotation(rotate(q, (1.0, 0.0, 0.0)), rotate(q, (0.0, 1.0, 0.0)), rotate(q, (0.0, 0.0, 1.0)))

    def matrix_rotation(self, matrix) -> QQuaternion:
        """QTM 6DOF rotation matrix (9 floats, column-major) -> scene QQuaternion (see body_rotation)."""
        return self.body_rotation(*matrix_columns(matrix))


_DEFAULT_MAPPING = AxisMapping("+Z")


def qtm_to_scene(x: float, y: float, z: float, axis_upwards: str = "+Z") -> QVector3D:
    """QTM position (mm) -> Qt Quick 3D scene position. For +Z up: (x, z, -y)."""
    mapping = _DEFAULT_MAPPING if axis_upwards == "+Z" else AxisMapping(axis_upwards)
    return mapping.vector((x, y, z))


def scene_to_qtm(v: QVector3D, axis_upwards: str = "+Z") -> tuple[float, float, float]:
    """Scene position -> QTM (x, y, z). The inverse of qtm_to_scene()."""
    mapping = _DEFAULT_MAPPING if axis_upwards == "+Z" else AxisMapping(axis_upwards)
    return mapping.from_scene((v.x(), v.y(), v.z()))
