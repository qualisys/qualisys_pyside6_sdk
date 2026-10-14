"""Skeleton joints and keeled bones (qtm_rt_pyside6.scene.skeleton)."""

import math

import pytest

from qtm_rt_pyside6.scene import (
    SIDE_COLORS,
    SkeletonDef,
    bone_width,
    keel_axis,
    side_of,
    skeleton_bones,
    skeleton_frame,
    skeleton_poses,
)
from qtm_rt_pyside6.scene.math3d import add, dot, length, quat_from_axis_angle, quat_multiply, rotate

IDENTITY = (0.0, 0.0, 0.0, 1.0)


def arm() -> SkeletonDef:
    """Shoulder -> elbow along -Z, plus a hand end point and a toe-like bone along +Y."""
    s = SkeletonDef("A")
    for sid, name, parent, offset in (
        (1, "Spine", None, (0.0, 0.0, 1000.0)),
        (2, "LeftArm", 1, (-150.0, 0.0, 400.0)),
        (3, "LeftForeArm", 2, (0.0, 0.0, -300.0)),
        (4, "RightFoot", 1, (100.0, 0.0, -900.0)),
        (5, "RightToeBase", 4, (0.0, 120.0, -60.0)),
    ):
        s.segment_ids.append(sid)
        s.names[sid] = name
        s.offsets[sid] = offset
        if parent is not None:
            s.parents[sid] = parent
    s.endpoints[3] = (0.0, 0.0, -250.0)
    return s


def solve(skeleton: SkeletonDef, rotations=None):
    """Global poses by forward kinematics from the default offsets."""
    rotations = rotations or {}
    pose = {}
    for sid in skeleton.segment_ids:
        q_local = rotations.get(sid, IDENTITY)
        parent = skeleton.parents.get(sid)
        if parent is None:
            pose[sid] = (skeleton.offsets[sid], q_local)
        else:
            pp, pq = pose[parent]
            pose[sid] = (add(pp, rotate(pq, skeleton.offsets[sid])), quat_multiply(pq, q_local))
    return [[(sid, p, q) for sid, (p, q) in pose.items()]]


class TestKeelAxis:
    def test_forward_for_bones_along_z(self):
        assert keel_axis((0.0, 0.0, -300.0)) == (0.0, 1.0, 0.0)
        assert keel_axis((-150.0, 0.0, 30.0)) == (0.0, 1.0, 0.0)

    def test_up_for_bones_along_y(self):
        assert keel_axis((0.0, 120.0, -60.0)) == (0.0, 0.0, 1.0)

    def test_zero_length_bone(self):
        assert keel_axis((0.0, 0.0, 0.0)) == (0.0, 1.0, 0.0)


class TestSides:
    @pytest.mark.parametrize(
        ("name", "side"),
        [("LeftForeArm", "left"), ("RightUpLeg", "right"), ("Spine", "center"), ("Head", "center")],
    )
    def test_side_of(self, name, side):
        assert side_of(name) == side

    def test_side_colors(self):
        assert SIDE_COLORS == {"left": "#456ce2", "right": "#f0c844", "center": "#a0a0a0"}


def test_bone_width_is_clamped():
    assert bone_width(50) == 14.0
    assert bone_width(200) == pytest.approx(22.0)
    assert bone_width(1000) == 40.0


class TestSkeletonBones:
    def test_bones_and_end_points(self):
        s = arm()
        joints, bones = skeleton_frame([s], solve(s))
        assert [j[0] for j in joints] == ["A:Spine", "A:LeftArm", "A:LeftForeArm", "A:RightFoot", "A:RightToeBase"]
        assert len(bones) == len(s.parents) + len(s.endpoints)
        hand = bones[-1]  # end point: forearm -> hand, 250 mm down
        assert hand[1][2] == pytest.approx(hand[0][2] - 250)
        assert hand[3] == "left"

    def test_keel_is_a_unit_vector_across_the_bone(self):
        s = arm()
        for start, end, keel, _side in skeleton_frame([s], solve(s))[1]:
            direction = tuple(e - b for b, e in zip(start, end, strict=True))
            assert length(keel) == pytest.approx(1.0)
            assert dot(keel, direction) == pytest.approx(0.0, abs=1e-6)

    def test_keel_follows_the_owner_segments_twist(self):
        s = arm()
        forearm = lambda bones: next(b for b in bones if b[3] == "left" and b[1][2] < b[0][2] - 200)  # noqa: E731
        _j, bones = skeleton_frame([s], solve(s))
        assert forearm(bones)[2] == pytest.approx((0.0, 1.0, 0.0))  # forward
        # Twist the upper arm 90 degrees about its own axis (Z): the elbow bone's ridge turns with it
        _j, bones = skeleton_frame([s], solve(s, {2: quat_from_axis_angle((0, 0, 1), 90)}))
        assert forearm(bones)[2] == pytest.approx((-1.0, 0.0, 0.0), abs=1e-9)

    def test_toe_ridge_marks_up(self):
        s = arm()
        _j, bones = skeleton_frame([s], solve(s))
        toe = next(b for b in bones if b[1][1] > b[0][1] + 100)  # the bone running forward
        # local +Z, made perpendicular to the (slightly downward) bone
        assert toe[2] == pytest.approx((0.0, 1 / math.sqrt(5), 2 / math.sqrt(5)), abs=1e-6)
        assert toe[3] == "right"

    def test_unsolved_segments_are_missing(self):
        s = arm()
        solved = solve(s)
        solved[0][2] = (3, (math.nan,) * 3, (math.nan,) * 4)  # forearm not solved
        joints, bones = skeleton_frame([s], solved)
        assert math.isnan(joints[2][1])
        poses = skeleton_poses([s], solved)
        assert 3 not in poses[0]
        # spine -> arm, spine -> foot and foot -> toe; arm -> forearm and the hand end point are gone
        assert len(skeleton_bones([s], poses)) == len(bones) == 3

    def test_fewer_skeletons_in_the_frame(self):
        s = arm()
        joints, bones = skeleton_frame([s, s], solve(s))
        assert len(joints) == len(s.segment_ids)
