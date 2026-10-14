"""Solved skeletons -> joints and "keeled" bones.

A keeled bone is an octahedral bone (as in Blender) whose ring has three
chamfered corners and one sharp, raised corner. That ridge, drawn as a light
stripe, marks the owning segment's forward axis, so each bone's roll / twist
is visible at a glance; Blender's symmetric octahedron cannot tell a quarter
turn apart.

QTM skeleton segments use X = right, Y = forward, Z = up, and most bones run
along +-Z. The ridge marks local +Y (forward), or +Z when the bone itself runs
along Y (toes).
"""

import math

from .math3d import MISSING, cross, dot, rotate, sub, unit
from .parameters import SkeletonDef

# Skeleton bone colors: left / right like QTM's usual marker coloring (left blue, right gold)
SIDE_COLORS = {"left": "#456ce2", "right": "#f0c844", "center": "#a0a0a0"}
KEEL_COLOR = "#f2f2f2"
JOINT_COLOR = "#ffffff"

# Bone width (the ring radius) as a fraction of its length, clamped to this range in mm
BONE_WIDTH_FACTOR = 0.11
BONE_WIDTH_RANGE = (14.0, 40.0)


def bone_width(length: float) -> float:
    """Ring radius of a keeled bone: clamp(0.11 x length, 14, 40) mm."""
    lo, hi = BONE_WIDTH_RANGE
    return max(lo, min(hi, BONE_WIDTH_FACTOR * length))


def keel_axis(bone_local) -> tuple[float, float, float]:
    """The local axis a bone's ridge marks: forward (+Y), or up (+Z) when the bone itself runs along Y (toes).

    QTM skeleton segments use X = right, Y = forward, Z = up; most bones run along +-Z."""
    d = unit(bone_local) or (0.0, 0.0, 1.0)
    return (0.0, 1.0, 0.0) if abs(d[1]) < 0.7 else (0.0, 0.0, 1.0)


def side_of(segment_name: str) -> str:
    """The side of a segment from QTM's naming (LeftArm, RightUpLeg, Spine): "left", "right" or "center"."""
    if segment_name.startswith("Left"):
        return "left"
    if segment_name.startswith("Right"):
        return "right"
    return "center"


def skeleton_poses(definitions: list[SkeletonDef], solved) -> list[dict]:
    """Per skeleton: segment id -> (position, rotation) for the segments solved in this frame.

    solved: from packet.get_skeletons() (global coordinates), one list of
    (segment id, position, rotation) per skeleton in the order of `definitions`,
    or the same shape with plain tuples. Unsolved segments (NaN) are left out."""
    poses = []
    for _skeleton, segments in zip(definitions, solved, strict=False):
        pose = {}
        for sid, pos, rot in segments:
            p = (pos[0], pos[1], pos[2])
            if not math.isnan(p[0]):
                pose[sid] = (p, (rot[0], rot[1], rot[2], rot[3]))
        poses.append(pose)
    return poses


def skeleton_joints(definitions: list[SkeletonDef], poses: list[dict]) -> list[tuple]:
    """Joints as (name, position, rotation): one per segment in definition order; position
    NaN and rotation None when not solved."""
    joints = []
    for skeleton, pose in zip(definitions, poses, strict=False):
        for sid, name in zip(skeleton.segment_ids, skeleton.joint_names(), strict=True):
            p, q = pose.get(sid, (MISSING, None))
            joints.append((name, p, q))
    return joints


def skeleton_bones(definitions: list[SkeletonDef], poses: list[dict]) -> list[tuple]:
    """Bones as (start, end, keel, side) in QTM coordinates.

    One bone per parent -> child, plus each end segment -> its end point (head
    top, hands, toes). `keel` is a unit vector perpendicular to the bone along
    the owning segment's forward axis; `side` is "left", "right" or "center"."""
    bones = []
    for skeleton, pose in zip(definitions, poses, strict=False):

        def add_bone(owner, start, end, bone_local, skeleton=skeleton, pose=pose):
            direction = unit(sub(end, start))
            if direction is None:
                return
            keel = rotate(pose[owner][1], keel_axis(bone_local))
            keel = unit(sub(keel, tuple(direction[k] * dot(keel, direction) for k in range(3))))
            if keel is None:  # forward axis along the bone: any perpendicular will do
                keel = unit(cross(direction, (1.0, 0.0, 0.0))) or unit(cross(direction, (0.0, 1.0, 0.0)))
            bones.append((start, end, keel, side_of(skeleton.names[owner])))

        for child, parent in skeleton.parents.items():
            if child in pose and parent in pose:
                add_bone(parent, pose[parent][0], pose[child][0], skeleton.offsets.get(child, (0.0, 0.0, 1.0)))
        for sid, offset in skeleton.endpoints.items():
            if sid in pose:
                p, q = pose[sid]
                r = rotate(q, offset)
                add_bone(sid, p, (p[0] + r[0], p[1] + r[1], p[2] + r[2]), offset)
    return bones


def skeleton_frame(definitions: list[SkeletonDef], solved) -> tuple[list[tuple], list[tuple]]:
    """Joints and bones of the solved skeletons in one frame.

    Returns joints as (name, x, y, z), one per segment in definition order (NaN
    when not solved), and bones as (start, end, keel, side), see skeleton_bones()."""
    poses = skeleton_poses(definitions, solved)
    joints = [(name, *p) for name, p, _q in skeleton_joints(definitions, poses)]
    return joints, skeleton_bones(definitions, poses)
