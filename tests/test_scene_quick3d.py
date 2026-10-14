"""Keeled bone geometry and instance tables (qtm_rt_pyside6.scene.quick3d). Needs PySide6-Addons."""

import struct

import pytest

pytest.importorskip("PySide6.QtQuick3D", reason='needs PySide6-Addons: pip install "qtm-rt-pyside6[scene]"')

from PySide6.QtGui import QColor  # noqa: E402

from qtm_rt_pyside6.scene import KEEL_COLOR, SIDE_COLORS, QtmScene, bone_width, demo_frame  # noqa: E402
from qtm_rt_pyside6.scene.math3d import length, sub  # noqa: E402
from qtm_rt_pyside6.scene.quick3d import (  # noqa: E402
    BoneInstancing,
    GridGeometry,
    KeelBoneGeometry,
    MarkerInstancing,
    RigidBodyInstancing,
    SkeletonInstancing,
    keel_bone_triangles,
)
from qtm_rt_pyside6.scene.quick3d._geometry import CHAMFER, KEEL_OUT, RING_HEIGHT  # noqa: E402

ENTRY = struct.Struct("<20f")


def entries(instancing):
    """The instance table as a list of 20-float tuples, checking the (QByteArray, count) contract."""
    buffer, count = instancing.getInstanceBuffer()
    data = bytes(buffer.data())
    assert len(data) == count * ENTRY.size
    return [ENTRY.unpack_from(data, i * ENTRY.size) for i in range(count)]


def color_of(entry):
    return entry[12:16]


def rgba(name):
    """A color as the instance table stores it: linear, as QQuick3DInstancing converts sRGB colors."""

    def linear(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    c = QColor(name)
    return pytest.approx((linear(c.redF()), linear(c.greenF()), linear(c.blueF()), c.alphaF()), abs=2e-3)


def column(entry, j):
    """Column j of the instance's 3x3 transform (rows are row0, row1, row2)."""
    return (entry[j], entry[4 + j], entry[8 + j])


@pytest.fixture
def scene(qtbot):
    s = QtmScene()
    frame = demo_frame(0.7)
    s.setParameters(frame.parameters)
    s.pushFrame(frame)
    s._publish()
    return s


class TestKeelGeometry:
    def test_keeled_ring(self):
        triangles = keel_bone_triangles("keeled")
        ring = {p for t in triangles for p in t[:3] if p[1] == RING_HEIGHT}
        # 3 chamfered corners (2 points each) + the ridge and its 2 stripe points
        assert len(ring) == 9
        assert len(triangles) == 18
        assert max(p[2] for p in ring) == pytest.approx(KEEL_OUT)  # the ridge on +Z at 1.55x
        assert max(p[0] for p in ring) == pytest.approx(1 - CHAMFER)  # chamfered corners stay inside

    def test_keel_part_is_a_narrow_stripe_around_the_ridge(self):
        keel = [t for t in keel_bone_triangles("keeled") if t[3] == "keel"]
        assert len(keel) == 4
        for tri in keel:
            assert any(p[2] == pytest.approx(KEEL_OUT) for p in tri[:3])

    def test_octahedral(self):
        triangles = keel_bone_triangles("octahedral")
        assert len(triangles) == 8 and {t[3] for t in triangles} == {"body"}

    def test_bone_runs_from_origin_to_unit_y(self):
        points = {p for t in keel_bone_triangles() for p in t[:3]}
        assert (0.0, 0.0, 0.0) in points and (0.0, 1.0, 0.0) in points

    @pytest.mark.parametrize(
        ("style", "part", "triangles"), [("keeled", "body", 14), ("keeled", "keel", 4), ("octahedral", "body", 8)]
    )
    def test_geometry_parts(self, qtbot, style, part, triangles):
        g = KeelBoneGeometry()
        g.style, g.part = style, part
        assert g.vertexData().size() == triangles * 3 * 24
        # flat normals point away from the bone axis
        data = bytes(g.vertexData().data())
        for i in range(0, len(data), 24):
            x, _y, z, nx, _ny, nz = struct.unpack_from("<6f", data, i)
            if abs(x) + abs(z) > 0.5:
                assert nx * x + nz * z > 0

    def test_grid(self, qtbot):
        g = GridGeometry()
        g.size, g.spacing = 2000, 500  # lines at -1000..1000: 5 per direction
        assert g.vertexData().size() == 5 * 2 * 2 * 12
        g.skipEvery = 2  # leave out -1000, 0, 1000
        assert g.vertexData().size() == 2 * 2 * 2 * 12


class TestSkeletonInstancing:
    def make(self, scene, part, style="keeled"):
        inst = SkeletonInstancing()
        inst.part, inst.style = part, style
        inst.scene = scene
        return inst

    def test_one_instance_per_bone(self, scene):
        assert len(entries(self.make(scene, "bones"))) == len(scene.frame.skeleton_bones)

    def test_side_colors(self, scene):
        bones = scene.frame.skeleton_bones
        for entry, (_s, _e, _k, side) in zip(entries(self.make(scene, "bones")), bones, strict=True):
            assert color_of(entry) == rgba(SIDE_COLORS[side])
        assert {b[3] for b in bones} == {"left", "right", "center"}

    def test_keels_are_light_and_share_the_bone_transforms(self, scene):
        bodies, keels = entries(self.make(scene, "bones")), entries(self.make(scene, "keels"))
        assert len(keels) == len(bodies)
        for body, keel in zip(bodies, keels, strict=True):
            assert color_of(keel) == rgba(KEEL_COLOR)
            assert body[:12] == pytest.approx(keel[:12])

    def test_transform_lays_the_bone_and_ridge(self, scene):
        mapping = scene.mapping
        for entry, (start, end, keel, _side) in zip(
            entries(self.make(scene, "bones")), scene.frame.skeleton_bones, strict=True
        ):
            n = length(sub(end, start))
            w = bone_width(n)
            assert (entry[3], entry[7], entry[11]) == pytest.approx(mapping.to_scene(start), abs=1e-3)
            assert column(entry, 1) == pytest.approx(mapping.to_scene(sub(end, start)), abs=1e-2)  # local +Y: the bone
            ridge = mapping.to_scene(keel)
            assert column(entry, 2) == pytest.approx(tuple(v * w for v in ridge), abs=1e-3)  # local +Z: the ridge

    def test_styles_without_ridges(self, scene):
        assert entries(self.make(scene, "keels", "octahedral")) == []
        assert entries(self.make(scene, "keels", "capsule")) == []
        assert len(entries(self.make(scene, "caps", "capsule"))) == 2 * len(scene.frame.skeleton_bones)
        assert entries(self.make(scene, "caps", "stick")) == []
        assert len(entries(self.make(scene, "bones", "stick"))) == len(scene.frame.skeleton_bones)

    def test_white_joints_grow_when_highlighted(self, scene):
        joints = self.make(scene, "joints")
        before = entries(joints)
        assert len(before) == len(scene.frame.joints)
        assert all(color_of(e) == rgba("#ffffff") for e in before)
        scene.highlight(["Demo:Head"])
        scene._publish()
        head = [j[0] for j in scene.frame.joints].index("Demo:Head")
        assert entries(joints)[head][0] == pytest.approx(before[head][0] * 1.5)

    def test_axes_modes(self, scene):
        axes = self.make(scene, "axes")
        assert entries(axes) == []
        axes.axesMode = "all"
        assert len(entries(axes)) == 3 * len(scene.frame.joints)
        axes.axesMode = "selected"
        assert entries(axes) == []
        scene.highlight(["Demo"])  # a skeleton name selects all its joints
        scene._publish()
        assert len(entries(axes)) == 3 * len(scene.frame.joints)

    def test_inactive_draws_nothing(self, scene):
        inst = self.make(scene, "bones")
        inst.active = False
        assert entries(inst) == []

    def test_colors_can_be_themed(self, scene):
        inst = self.make(scene, "bones")
        inst.leftColor = QColor("#00ff00")
        left = [i for i, b in enumerate(scene.frame.skeleton_bones) if b[3] == "left"]
        assert color_of(entries(inst)[left[0]]) == rgba("#00ff00")


class TestOtherInstancing:
    def test_markers_in_label_colors(self, scene):
        inst = MarkerInstancing()
        inst.scene = scene
        table = entries(inst)
        tracked = [
            (n, c)
            for n, p, c in zip(scene.frame.labels, scene.frame.labeled, scene.parameters.colors, strict=True)
            if p[0] == p[0]
        ]
        assert len(table) == len(tracked)
        assert color_of(table[0]) == rgba(tracked[0][1])
        assert table[0][0] == pytest.approx(0.24)  # 24 mm on the 100-unit #Sphere

    def test_unlabeled_markers(self, scene):
        inst = MarkerInstancing()
        inst.kind = "unlabeled"
        inst.scene = scene
        assert len(entries(inst)) == len(scene.frame.unlabeled)

    def test_user_bones_as_capsules(self, scene):
        shaft, caps = BoneInstancing(), BoneInstancing()
        caps.part = "caps"
        shaft.scene = caps.scene = scene
        assert len(entries(shaft)) == len(scene.frame.user_bones)
        assert len(entries(caps)) == 2 * len(scene.frame.user_bones)

    def test_rigid_body_tripod(self, scene):
        axes = RigidBodyInstancing()
        axes.scene = scene
        assert len(entries(axes)) == 3
        assert [color_of(e) for e in entries(axes)] == [rgba("#e15449"), rgba("#59b36b"), rgba("#5d82ea")]
