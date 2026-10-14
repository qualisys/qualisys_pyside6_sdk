"""QTM -> scene coordinates (qtm_rt_pyside6.scene.math3d)."""

import math

import pytest
from PySide6.QtGui import QVector3D

from qtm_rt_pyside6.scene import AXIS_UPWARDS, AxisMapping, qtm_to_scene, scene_to_qtm
from qtm_rt_pyside6.scene.math3d import quat_from_axis_angle, quat_multiply, rotate

UP = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


def det(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def test_z_up_is_x_z_minus_y():
    assert qtm_to_scene(1, 2, 3) == QVector3D(1, 3, -2)
    assert scene_to_qtm(QVector3D(1, 3, -2)) == pytest.approx((1, 2, 3))


@pytest.mark.parametrize("axis", AXIS_UPWARDS)
def test_every_mapping_is_a_proper_rotation(axis):
    m = AxisMapping(axis)
    assert det(m.matrix) == 1
    for row in m.matrix:
        assert sum(v * v for v in row) == 1


@pytest.mark.parametrize("axis", AXIS_UPWARDS)
def test_qtm_up_becomes_scene_up(axis):
    assert AxisMapping(axis).to_scene(UP[axis]) == (0, 1, 0)


@pytest.mark.parametrize("axis", AXIS_UPWARDS)
def test_round_trip(axis):
    m = AxisMapping(axis)
    p = (12.5, -340.0, 1001.0)
    assert m.from_scene(m.to_scene(p)) == pytest.approx(p)


def test_unknown_axis_falls_back_to_z_up():
    assert AxisMapping("sideways").axis_upwards == "+Z"
    assert AxisMapping(" +y ").axis_upwards == "+Y"


@pytest.mark.parametrize("axis", AXIS_UPWARDS)
def test_body_at_rest_is_at_rest(axis):
    q = AxisMapping(axis).matrix_rotation((1, 0, 0, 0, 1, 0, 0, 0, 1))
    assert abs(q.scalar()) == pytest.approx(1.0)


@pytest.mark.parametrize("axis", AXIS_UPWARDS)
def test_turn_about_qtm_up_is_a_turn_about_scene_up(axis):
    m = AxisMapping(axis)
    q = quat_from_axis_angle(UP[axis], 90)
    rotation = m.quaternion(q)
    axis_vector, angle = rotation.getAxisAndAngle()
    assert angle == pytest.approx(90, abs=1e-3)
    assert (axis_vector.x(), axis_vector.y(), axis_vector.z()) == pytest.approx((0, 1, 0), abs=1e-6)


def test_matrix_is_column_major():
    # A body turned 90 degrees about QTM Z: its X axis points along QTM +Y
    turned = (0, 1, 0, -1, 0, 0, 0, 0, 1)  # columns: X axis, Y axis, Z axis
    rotation = AxisMapping("+Z").matrix_rotation(turned)
    x_axis = rotation.rotatedVector(QVector3D(1, 0, 0))
    qtm_y = qtm_to_scene(0, 1, 0)
    assert (x_axis.x(), x_axis.y(), x_axis.z()) == pytest.approx((qtm_y.x(), qtm_y.y(), qtm_y.z()), abs=1e-6)


def test_frame_rotation_lays_local_axes_on_directions():
    m = AxisMapping("+Z")
    rotation = m.frame_rotation((0, 0, 1), (1, 0, 0), (0, 1, 0))  # local Y onto QTM +X
    y = rotation.rotatedVector(QVector3D(0, 1, 0))
    assert (y.x(), y.y(), y.z()) == pytest.approx((1, 0, 0), abs=1e-6)


def test_quaternion_helpers():
    q = quat_multiply(quat_from_axis_angle((0, 0, 1), 90), quat_from_axis_angle((1, 0, 0), 90))
    # rotate by X first, then Z: +Y -> +Z -> +Z
    assert rotate(q, (0, 1, 0)) == pytest.approx((0, 0, 1), abs=1e-9)
    assert rotate(quat_from_axis_angle((0, 0, 1), 90), (1, 0, 0)) == pytest.approx((0, 1, 0), abs=1e-9)
    assert math.isclose(sum(v * v for v in q), 1.0)
