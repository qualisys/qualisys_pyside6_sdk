"""One frame of QTM data, ready for a 3D view or for app logic.

A :class:`SceneFrame` wraps a QRTPacket (or simulated data) together with the
:class:`SceneParameters` it belongs to, and decodes on first use: labeled and
unlabeled markers, rigid bodies (6D, rotation as a 3x3 matrix) and skeletons
(``skeleton:global`` quaternions). Joints are named "<skeleton>:<segment>".

All positions are QTM coordinates in mm; ``frame.mapping`` turns them into
Qt Quick 3D scene coordinates.
"""

import math
from functools import cached_property

from qtm_rt.packet import (
    QRTComponentType,
    RT3DComponent,
    RT6DComponent,
    RTSkeletonComponent,
)

from .math3d import MISSING, AxisMapping
from .parameters import SceneParameters
from .skeleton import skeleton_bones, skeleton_joints, skeleton_poses

UNLABELED_PREFIX = "Unlabeled #"

_NAN9 = (math.nan,) * 9


def unlabeled_name(marker_id: int) -> str:
    return f"{UNLABELED_PREFIX}{marker_id}"


class SceneFrame:
    """Markers, rigid bodies and skeletons of one frame, decoded lazily.

    Build one from a packet with :meth:`from_packet`, or pass the data directly
    (simulations, tests):

    - labeled: [(x, y, z)] in label order, NaN when not tracked
    - unlabeled: [(id, x, y, z)]
    - bodies: [((x, y, z), matrix)] in 6D body order; matrix is QTM's 9-float
      column-major rotation matrix
    - skeletons: as packet.get_skeletons(): per skeleton [(segment id, (x, y, z), (qx, qy, qz, qw))]

    A component that is None was not in the frame at all; [] means present but empty.
    """

    def __init__(
        self,
        parameters: SceneParameters | None = None,
        frame_number: int = 0,
        timestamp: int = 0,
        *,
        labeled=None,
        unlabeled=None,
        bodies=None,
        skeletons=None,
    ):
        self.parameters = parameters if parameters is not None else SceneParameters()
        self.frame_number = frame_number
        self.timestamp = timestamp
        self._packet = None
        self._given = {"labeled": labeled, "unlabeled": unlabeled, "bodies": bodies, "skeletons": skeletons}

    @classmethod
    def from_packet(cls, packet, parameters: SceneParameters | None = None) -> "SceneFrame":
        frame = cls(parameters, packet.framenumber, packet.timestamp)
        frame._packet = packet
        return frame

    def __repr__(self):
        return f"<SceneFrame {self.frame_number}>"

    def with_parameters(self, parameters: SceneParameters) -> "SceneFrame":
        """The same data read with other parameters (labels, skeleton definitions)."""
        frame = SceneFrame(parameters, self.frame_number, self.timestamp, **self._given)
        frame._packet = self._packet
        return frame

    # ------------------------------------------------------------------ raw components

    def _from_packet(self, getter):
        result = getattr(self._packet, getter)() if self._packet is not None else None
        return None if result is None else result[1]

    # component name -> (packet component type, header type, count field, constructor argument)
    _COMPONENTS = {
        "3d": (QRTComponentType.Component3d, RT3DComponent, "marker_count", "labeled"),
        "3dnolabels": (QRTComponentType.Component3dNoLabels, RT3DComponent, "marker_count", "unlabeled"),
        "6d": (QRTComponentType.Component6d, RT6DComponent, "body_count", "bodies"),
        "skeleton": (QRTComponentType.ComponentSkeleton, RTSkeletonComponent, "skeleton_count", "skeletons"),
    }

    def has(self, component: str) -> bool:
        """Whether the frame carries a component: "3d", "3dnolabels", "6d" or "skeleton"."""
        return self.count(component) is not None

    def count(self, component: str) -> int | None:
        """Item count of a component ("3d", "3dnolabels", "6d", "skeleton") read from its
        header without decoding the items; None when the frame does not carry it."""
        component_type, header, field, argument = self._COMPONENTS[component]
        if self._packet is None:
            given = self._given[argument]
            return None if given is None else len(given)
        position = self._packet.components.get(component_type)
        if position is None:
            return None
        return getattr(header._make(header.format.unpack_from(self._packet.data, position)), field)

    def mismatched(self) -> bool:
        """True when the frame's marker, body or skeleton count differs from the
        parameters, e.g. after QTM switched to another file: time to refresh them."""
        p = self.parameters
        expected = {"3d": len(p.labels), "6d": len(p.bodies), "skeleton": len(p.skeletons)}
        for component, n in expected.items():
            count = self.count(component)
            if count is not None and count != n:
                return True
        return False

    @cached_property
    def labeled(self) -> list[tuple[float, float, float]]:
        """Labeled marker positions in label order (NaN when not tracked)."""
        if self._packet is None:
            return [tuple(p) for p in self._given["labeled"] or ()]
        return [(m.x, m.y, m.z) for m in self._from_packet("get_3d_markers") or ()]

    @cached_property
    def unlabeled(self) -> list[tuple[int, float, float, float]]:
        """Unlabeled markers as (id, x, y, z)."""
        if self._packet is None:
            return [tuple(m) for m in self._given["unlabeled"] or ()]
        return [(m.id, m.x, m.y, m.z) for m in self._from_packet("get_3d_markers_no_label") or ()]

    @cached_property
    def bodies(self) -> list[tuple[tuple[float, float, float], tuple]]:
        """Rigid bodies as ((x, y, z), 9-float column-major rotation matrix), in 6D body order."""
        if self._packet is None:
            return [(tuple(p), tuple(m)) for p, m in self._given["bodies"] or ()]
        return [((p.x, p.y, p.z), tuple(r.matrix)) for p, r in self._from_packet("get_6d") or ()]

    @cached_property
    def solved_skeletons(self) -> list:
        """Skeleton segments as from packet.get_skeletons(): per skeleton [(id, position, rotation)]."""
        if self._packet is None:
            return list(self._given["skeletons"] or ())
        return self._from_packet("get_skeletons") or []

    # ------------------------------------------------------------------ derived

    @cached_property
    def mapping(self) -> AxisMapping:
        """QTM -> scene coordinates for this frame's AxisUpwards."""
        return AxisMapping(self.parameters.axis_upwards)

    @cached_property
    def labels(self) -> list[str]:
        """A name per labeled marker; "Marker <n>" past the end of the label list."""
        names = self.parameters.labels
        return [names[i] if i < len(names) else f"Marker {i + 1}" for i in range(len(self.labeled))]

    @cached_property
    def skeleton_poses(self) -> list[dict]:
        """Per skeleton definition: segment id -> (position, rotation); {} when not in the frame."""
        definitions = self.parameters.skeletons
        poses = skeleton_poses(definitions, self.solved_skeletons)
        return poses + [{} for _ in range(len(definitions) - len(poses))]

    @cached_property
    def joints(self) -> list[tuple]:
        """Skeleton joints as (name, (x, y, z), (qx, qy, qz, qw) or None), one per segment in
        definition order. Rotations are global (skeleton:global)."""
        return skeleton_joints(self.parameters.skeletons, self.skeleton_poses)

    @cached_property
    def skeleton_bones(self) -> list[tuple]:
        """Skeleton bones as (start, end, keel, side), see skeleton.skeleton_bones()."""
        return skeleton_bones(self.parameters.skeletons, self.skeleton_poses)

    @cached_property
    def rigid_bodies(self) -> list[tuple]:
        """Rigid bodies as (name, (x, y, z), matrix); NaN position and matrix when not tracked."""
        names = self.parameters.body_names()
        result = []
        for i, (p, m) in enumerate(self.bodies):
            name = names[i] if i < len(names) else f"Body {i + 1}"
            if math.isnan(p[0]) or any(math.isnan(v) for v in m):
                p, m = MISSING, _NAN9
            result.append((name, p, m))
        return result

    @cached_property
    def user_bones(self) -> list[tuple]:
        """QTM's bones between labeled markers as (start, end, color), skipping unknown labels."""
        index = {name: i for i, name in enumerate(self.parameters.labels)}
        labeled = self.labeled
        bones = []
        for a, b, color in self.parameters.bones:
            i, j = index.get(a), index.get(b)
            if i is None or j is None or i >= len(labeled) or j >= len(labeled):
                continue
            bones.append((labeled[i], labeled[j], color))
        return bones

    @cached_property
    def _positions(self) -> dict[str, tuple[float, float, float]]:
        positions = {}
        for name, p in zip(self.labels, self.labeled, strict=True):
            positions.setdefault(name, p)
        for name, p, _q in self.joints:
            positions.setdefault(name, p)
        for name, p, _m in self.rigid_bodies:
            positions.setdefault(name, p)
        for marker_id, x, y, z in self.unlabeled:
            positions.setdefault(unlabeled_name(marker_id), (x, y, z))
        return positions

    def position(self, name: str) -> tuple[float, float, float]:
        """Latest QTM position of a labeled marker, joint ("<skeleton>:<segment>"), rigid body
        or unlabeled marker ("Unlabeled #<id>"); NaN when missing or unknown."""
        return self._positions.get(name, MISSING)

    def points(self) -> list[tuple[str, str, tuple[float, float, float]]]:
        """Every tracked point as (name, kind, position); kind is "marker", "unlabeled",
        "joint" or "body". Used for picking and bounds."""
        points = [(n, "marker", p) for n, p in zip(self.labels, self.labeled, strict=True) if not math.isnan(p[0])]
        points += [(unlabeled_name(i), "unlabeled", (x, y, z)) for i, x, y, z in self.unlabeled if not math.isnan(x)]
        points += [(n, "joint", p) for n, p, _q in self.joints if not math.isnan(p[0])]
        points += [(n, "body", p) for n, p, _m in self.rigid_bodies if not math.isnan(p[0])]
        return points

    @cached_property
    def marker_count(self) -> int:
        """Labeled + unlabeled markers tracked in this frame."""
        labeled = sum(1 for p in self.labeled if not math.isnan(p[0]))
        return labeled + sum(1 for m in self.unlabeled if not math.isnan(m[1]))
