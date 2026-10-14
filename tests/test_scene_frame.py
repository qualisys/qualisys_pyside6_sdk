"""Decoding QTM frames (qtm_rt_pyside6.scene.frame)."""

import math

import pytest

from qtm_rt_pyside6.scene import SceneFrame, demo_frame, demo_parameters, parse_parameters
from tests.scene_packets import IDENTITY_MATRIX, IDENTITY_QUAT, PARAMETERS_XML, build_packet

NAN3 = (math.nan, math.nan, math.nan)


@pytest.fixture
def params():
    return parse_parameters(PARAMETERS_XML)


@pytest.fixture
def packet():
    return build_packet(
        42,
        1234,
        labeled=[(100.0, 0.0, 1400.0), NAN3, (300.0, 0.0, 900.0)],
        unlabeled=[(5.0, 6.0, 7.0, 17)],
        bodies=[((500.0, 500.0, 1000.0), IDENTITY_MATRIX)],
        skeletons=[
            [
                (1, (0.0, 0.0, 950.0), IDENTITY_QUAT),
                (2, (-90.0, 0.0, 900.0), IDENTITY_QUAT),
                (3, NAN3, (math.nan,) * 4),
            ]
        ],
    )


def test_labeled_markers_in_label_order(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    assert (frame.frame_number, frame.timestamp) == (42, 1234)
    assert frame.labels == ["Shoulder", "Elbow", "Wrist"]
    assert frame.labeled[0] == (100.0, 0.0, 1400.0)
    assert math.isnan(frame.labeled[1][0])
    assert frame.position("Wrist") == (300.0, 0.0, 900.0)
    assert math.isnan(frame.position("Elbow")[0])
    assert math.isnan(frame.position("no such marker")[0])


def test_unlabeled_markers(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    assert frame.unlabeled == [(17, 5.0, 6.0, 7.0)]
    assert frame.position("Unlabeled #17") == (5.0, 6.0, 7.0)
    assert frame.marker_count == 3  # two labeled (one is missing) + one unlabeled


def test_rigid_bodies(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    ((name, position, matrix),) = frame.rigid_bodies
    assert (name, position, matrix) == ("Wand", (500.0, 500.0, 1000.0), IDENTITY_MATRIX)


def test_untracked_rigid_body_is_nan(params):
    frame = SceneFrame.from_packet(build_packet(bodies=[(NAN3, (math.nan,) * 9)]), params)
    _name, position, matrix = frame.rigid_bodies[0]
    assert math.isnan(position[0]) and math.isnan(matrix[0])
    assert frame.points() == []


def test_joints_are_named_skeleton_colon_segment(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    assert [j[0] for j in frame.joints] == ["S:Hips", "S:LeftUpLeg", "S:LeftLeg"]
    assert frame.joints[0][1:] == ((0.0, 0.0, 950.0), IDENTITY_QUAT)
    assert math.isnan(frame.joints[2][1][0]) and frame.joints[2][2] is None
    assert frame.position("S:LeftUpLeg") == (-90.0, 0.0, 900.0)


def test_skeleton_bones_skip_unsolved_segments(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    # Hips -> LeftUpLeg only: LeftLeg (and its end point) is not solved
    ((start, end, keel, side),) = frame.skeleton_bones
    assert (start, end, side) == ((0.0, 0.0, 950.0), (-90.0, 0.0, 900.0), "center")
    assert keel == pytest.approx((0.0, 1.0, 0.0))


def test_user_bones_need_known_labels(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    bones = frame.user_bones
    assert [b[2] for b in bones] == ["#b0e0b1", "#a0a0a0"]  # Elbow -> Nowhere is dropped
    assert bones[0][0] == (100.0, 0.0, 1400.0)


def test_points_for_picking(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    kinds = {(name, kind) for name, kind, _p in frame.points()}
    assert kinds == {
        ("Shoulder", "marker"),
        ("Wrist", "marker"),
        ("Unlabeled #17", "unlabeled"),
        ("S:Hips", "joint"),
        ("S:LeftUpLeg", "joint"),
        ("Wand", "body"),
    }


def test_counts_come_from_component_headers(params, packet):
    frame = SceneFrame.from_packet(packet, params)
    assert (frame.count("3d"), frame.count("3dnolabels"), frame.count("6d"), frame.count("skeleton")) == (3, 1, 1, 1)
    assert frame.has("3d") and not SceneFrame.from_packet(build_packet(labeled=[]), params).has("6d")
    assert not frame.mismatched()


def test_mismatch_when_qtm_streams_something_else(params):
    assert SceneFrame.from_packet(build_packet(labeled=[(0.0, 0.0, 0.0)]), params).mismatched()
    assert SceneFrame.from_packet(build_packet(skeletons=[]), params).mismatched()
    assert not SceneFrame.from_packet(build_packet(), params).mismatched()  # nothing to compare


def test_more_markers_than_labels(params):
    frame = SceneFrame.from_packet(build_packet(labeled=[(1.0, 2.0, 3.0)] * 4), params)
    assert frame.labels[-1] == "Marker 4"


def test_mapping_follows_axis_upwards(params, packet):
    params.axis_upwards = "+Y"
    frame = SceneFrame.from_packet(packet, params)
    assert frame.mapping.to_scene((1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)


def test_with_parameters_rereads_the_packet(params, packet):
    frame = SceneFrame.from_packet(packet, demo_parameters())
    assert frame.labels[0] == "HeadTop"
    assert frame.with_parameters(params).labels[0] == "Shoulder"


def test_simulated_frame():
    frame = demo_frame(1.0)
    p = frame.parameters
    assert len(frame.labeled) == len(p.labels)
    assert len(frame.joints) == len(p.joint_names())
    assert len(frame.skeleton_bones) == len(p.skeletons[0].parents) + len(p.skeletons[0].endpoints)
    assert not frame.mismatched()
    assert {kind for _n, kind, _p in frame.points()} == {"marker", "unlabeled", "joint", "body"}
