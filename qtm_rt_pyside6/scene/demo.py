"""DemoSource: simulated QTM data for a QtmScene, for trying views without QTM.

A small skeleton walks on the spot at 100 Hz: its arms and legs swing, the
forearms twist (watch the bones' ridges turn) and the head looks around.
Labeled markers ride on the segments, QTM-style bones join some of them, a
rigid body circles the subject and two unlabeled markers drift about.

    scene = QtmScene()
    demo = DemoSource(scene)
    demo.start()
"""

import math
import random

from PySide6.QtCore import Property, QElapsedTimer, QObject, Qt, QTimer, Signal, Slot

from .frame import SceneFrame
from .math3d import add, quat_from_axis_angle, quat_multiply, rotate
from .parameters import RigidBodyDef, SceneParameters, SkeletonDef

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)

# (id, name, parent id, offset in parent in mm, end point or None).
# QTM segment axes: X right, Y forward, Z up. Left is -X.
_SEGMENTS = [
    (1, "Hips", None, (0.0, 0.0, 950.0), None),
    (2, "Spine", 1, (0.0, -10.0, 110.0), None),
    (3, "Spine1", 2, (0.0, 0.0, 190.0), None),
    (4, "Neck", 3, (0.0, 0.0, 190.0), None),
    (5, "Head", 4, (0.0, 15.0, 100.0), (0.0, 0.0, 170.0)),
    (6, "LeftShoulder", 3, (-35.0, 0.0, 150.0), None),
    (7, "LeftArm", 6, (-145.0, 0.0, 0.0), None),
    (8, "LeftForeArm", 7, (0.0, 0.0, -285.0), None),
    (9, "LeftHand", 8, (0.0, 0.0, -255.0), (0.0, 0.0, -90.0)),
    (10, "RightShoulder", 3, (35.0, 0.0, 150.0), None),
    (11, "RightArm", 10, (145.0, 0.0, 0.0), None),
    (12, "RightForeArm", 11, (0.0, 0.0, -285.0), None),
    (13, "RightHand", 12, (0.0, 0.0, -255.0), (0.0, 0.0, -90.0)),
    (14, "LeftUpLeg", 1, (-95.0, 0.0, -55.0), None),
    (15, "LeftLeg", 14, (0.0, 0.0, -430.0), None),
    (16, "LeftFoot", 15, (0.0, 0.0, -410.0), None),
    (17, "LeftToeBase", 16, (0.0, 125.0, -65.0), (0.0, 60.0, 0.0)),
    (18, "RightUpLeg", 1, (95.0, 0.0, -55.0), None),
    (19, "RightLeg", 18, (0.0, 0.0, -430.0), None),
    (20, "RightFoot", 19, (0.0, 0.0, -410.0), None),
    (21, "RightToeBase", 20, (0.0, 125.0, -65.0), (0.0, 60.0, 0.0)),
]

# Labeled markers: (label, segment name, offset in the segment, color)
_LEFT, _RIGHT, _CENTER = "#8fb0ff", "#ffe08a", "#d0a8ff"
_MARKERS = [
    ("HeadTop", "Head", (0.0, 0.0, 185.0), _CENTER),
    ("HeadFront", "Head", (0.0, 95.0, 105.0), _CENTER),
    ("Sacrum", "Hips", (0.0, -115.0, 35.0), _CENTER),
    ("L_Shoulder", "LeftArm", (-25.0, 0.0, 35.0), _LEFT),
    ("L_Elbow", "LeftForeArm", (-35.0, 0.0, 0.0), _LEFT),
    ("L_Wrist", "LeftHand", (-30.0, 0.0, 0.0), _LEFT),
    ("R_Shoulder", "RightArm", (25.0, 0.0, 35.0), _RIGHT),
    ("R_Elbow", "RightForeArm", (35.0, 0.0, 0.0), _RIGHT),
    ("R_Wrist", "RightHand", (30.0, 0.0, 0.0), _RIGHT),
    ("L_Knee", "LeftLeg", (-50.0, 0.0, 0.0), _LEFT),
    ("L_Ankle", "LeftFoot", (-40.0, 0.0, 0.0), _LEFT),
    ("L_Toe", "LeftToeBase", (0.0, 45.0, 0.0), _LEFT),
    ("R_Knee", "RightLeg", (50.0, 0.0, 0.0), _RIGHT),
    ("R_Ankle", "RightFoot", (40.0, 0.0, 0.0), _RIGHT),
    ("R_Toe", "RightToeBase", (0.0, 45.0, 0.0), _RIGHT),
]
_BONE_COLOR = "#b4b4b4"
_BONES = [
    ("HeadTop", "HeadFront"),
    ("L_Shoulder", "L_Elbow"),
    ("L_Elbow", "L_Wrist"),
    ("R_Shoulder", "R_Elbow"),
    ("R_Elbow", "R_Wrist"),
    ("L_Knee", "L_Ankle"),
    ("L_Ankle", "L_Toe"),
    ("R_Knee", "R_Ankle"),
    ("R_Ankle", "R_Toe"),
]
_BODY = RigidBodyDef(
    "Wand", color="#0baccd", points=[(0.0, 0.0, 0.0), (90.0, 0.0, 0.0), (0.0, 60.0, 0.0), (0.0, 0.0, 45.0)]
)


def demo_parameters() -> SceneParameters:
    """Labels, colors, bones, the rigid body and the skeleton of the demo data."""
    skeleton = SkeletonDef("Demo")
    for sid, name, parent, offset, end in _SEGMENTS:
        skeleton.segment_ids.append(sid)
        skeleton.names[sid] = name
        skeleton.offsets[sid] = offset
        if parent is not None:
            skeleton.parents[sid] = parent
        if end is not None:
            skeleton.endpoints[sid] = end
    return SceneParameters(
        labels=[m[0] for m in _MARKERS],
        colors=[m[3] for m in _MARKERS],
        bones=[(a, b, _BONE_COLOR) for a, b in _BONES],
        axis_upwards="+Z",
        bodies=[RigidBodyDef(_BODY.name, _BODY.color, True, list(_BODY.points))],
        skeletons=[skeleton],
    )


def _local_rotations(t: float) -> dict[str, tuple]:
    """Each segment's rotation in its parent at time t (seconds): walking on the spot."""
    w = 2 * math.pi * 0.8  # step frequency
    s, c = math.sin(w * t), math.cos(w * t)

    def turn(*parts):
        q = IDENTITY
        for axis, degrees in parts:
            q = quat_multiply(q, quat_from_axis_angle(axis, degrees))
        return q

    return {
        "Hips": turn((Z, 25 * math.sin(0.25 * t)), (Y, 3 * s)),
        "Spine": turn((X, 4 + 2 * c), (Z, -6 * s)),
        "Spine1": turn((Z, -4 * s)),
        "Head": turn((Z, 35 * math.sin(0.45 * t)), (X, -8 * math.sin(0.3 * t))),
        "LeftArm": turn((Y, -10), (X, 32 * s)),
        "LeftForeArm": turn((X, 35 + 20 * s), (Z, 70 * math.sin(0.7 * t))),
        "RightArm": turn((Y, 10), (X, -32 * s)),
        "RightForeArm": turn((X, 35 - 20 * s), (Z, -70 * math.sin(0.7 * t + 1.0))),
        "LeftUpLeg": turn((X, -28 * s)),
        "LeftLeg": turn((X, -25 * (1 - c))),
        "LeftFoot": turn((X, 10 * c)),
        "RightUpLeg": turn((X, 28 * s)),
        "RightLeg": turn((X, -25 * (1 + c))),
        "RightFoot": turn((X, -10 * c)),
    }


def _pose(t: float) -> dict[str, tuple]:
    """Global (position, rotation) per segment name, by forward kinematics."""
    local = _local_rotations(t)
    pose = {}
    for _sid, name, parent, offset, _end in _SEGMENTS:
        q_local = local.get(name, IDENTITY)
        if parent is None:
            p = add(offset, (0.0, 0.0, 12 * math.sin(4 * math.pi * 0.8 * t)))
            pose[name] = (p, q_local)
            continue
        parent_name = next(n for i, n, *_ in _SEGMENTS if i == parent)
        pp, pq = pose[parent_name]
        pose[name] = (add(pp, rotate(pq, offset)), quat_multiply(pq, q_local))
    return pose


def demo_frame(t: float, frame_number: int = 0, parameters: SceneParameters | None = None, rng=None) -> SceneFrame:
    """The demo scene at time t (seconds). Pass a random.Random for marker noise."""
    parameters = parameters or demo_parameters()
    pose = _pose(t)

    def noise(p):
        return tuple(v + rng.gauss(0, 0.4) for v in p) if rng is not None else p

    labeled = []
    for _label, segment, offset, _color in _MARKERS:
        p, q = pose[segment]
        labeled.append(noise(add(p, rotate(q, offset))))
    # The right wrist marker hides for half a second every seven, like a real occlusion
    if t % 7.0 > 6.5:
        labeled[[m[0] for m in _MARKERS].index("R_Wrist")] = (math.nan,) * 3

    a = 0.35 * t
    body_q = quat_multiply(
        quat_from_axis_angle(Z, math.degrees(a) + 90), quat_from_axis_angle(X, 20 * math.sin(1.3 * t))
    )
    body_p = (1300 * math.cos(a), 1300 * math.sin(a), 1000 + 180 * math.sin(0.9 * t))
    matrix = (*rotate(body_q, X), *rotate(body_q, Y), *rotate(body_q, Z))  # column-major, as QTM streams it

    unlabeled = [
        (1, -900 + 60 * math.sin(0.6 * t), 700.0, 30.0),
        (2, 800.0, -650 + 80 * math.cos(0.4 * t), 1500 + 50 * math.sin(t)),
    ]
    order = {name: sid for sid, name, *_ in _SEGMENTS}
    solved = [[(order[name], p, q) for name, (p, q) in pose.items()]]
    return SceneFrame(
        parameters,
        frame_number,
        int(t * 1e6),
        labeled=labeled,
        unlabeled=unlabeled,
        bodies=[(body_p, matrix)],
        skeletons=solved,
    )


class DemoSource(QObject):
    """Feeds a QtmScene with simulated data at `rate` Hz while running."""

    runningChanged = Signal()

    def __init__(self, scene=None, parent: QObject | None = None, rate: int = 100):
        super().__init__(parent)
        self.scene = scene
        self._parameters = demo_parameters()
        self._frame_number = 0
        self._rng = random.Random(7)
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(max(1, round(1000 / rate)))
        self._timer.timeout.connect(self._tick)

    def _get_running(self):
        return self._timer.isActive()

    def _set_running(self, on: bool):
        if on:
            self.start()
        else:
            self.stop()

    running = Property(bool, _get_running, _set_running, notify=runningChanged)

    @Slot()
    def start(self):
        if self._timer.isActive() or self.scene is None:
            return
        self.scene.setParameters(self._parameters)
        self._clock.start()
        self._timer.start()
        self._tick()
        self.runningChanged.emit()

    @Slot()
    def stop(self):
        if not self._timer.isActive():
            return
        self._timer.stop()
        if self.scene is not None:
            self.scene.clear()
        self.runningChanged.emit()

    def _tick(self):
        self._frame_number += 1
        t = self._clock.elapsed() / 1000.0
        self.scene.pushFrame(demo_frame(t, self._frame_number, self._parameters, self._rng))
