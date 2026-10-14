"""Parameter XML -> scene definitions (qtm_rt_pyside6.scene.parameters)."""

from pathlib import Path

import pytest

from qtm_rt_pyside6.scene import (
    SceneParameters,
    parse_3d,
    parse_6d,
    parse_parameters,
    parse_skeletons,
    qtm_color,
)
from tests.scene_packets import PARAMETERS_XML

# Synthetic files in QTM's layout, written by fixtures/make_fixtures.py
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def xml_3d() -> str:
    return (FIXTURES / "params_3d.xml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def xml_skeleton() -> str:
    return (FIXTURES / "params_skeleton.xml").read_text(encoding="utf-8")


class TestQtmColor:
    def test_red_is_the_low_byte(self):
        assert qtm_color(0x0000FF) == "#ff0000"
        assert qtm_color(0x00FF00) == "#00ff00"
        assert qtm_color(0xFF0000) == "#0000ff"

    def test_alpha_and_negative_values(self):
        # Bone colors carry an alpha byte on top and arrive as signed ints
        assert qtm_color(-1380851536) == "#b0e0b1"
        assert qtm_color("8388736") == "#800080"


class TestParse3D:
    def test_labels_and_colors(self, xml_3d):
        settings = parse_3d(xml_3d)
        assert len(settings.labels) == 22
        assert len(settings.colors) == 22
        assert settings.labels[0] == "HeadTop"
        assert settings.colors[0] == "#800080"  # RGBColor 8388736
        assert settings.labels[5] == "L_Shoulder"
        assert settings.colors[5] == "#0000ff"  # RGBColor 0xFF0000: blue, as red is the low byte
        assert settings.labels[-1] == "Wand_3"
        assert settings.colors[-1] == "#00ff00"  # RGBColor 65280
        assert settings.axis_upwards == "+Z"

    def test_user_bones(self, xml_3d):
        bones = parse_3d(xml_3d).bones
        assert len(bones) == 14
        assert bones[0] == ("HeadTop", "HeadFront", "#b0e0b1")

    def test_bone_without_color_gets_default(self):
        bones = parse_3d(PARAMETERS_XML).bones
        assert bones[1] == ("Elbow", "Wrist", "#a0a0a0")

    @pytest.mark.parametrize("axis", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
    def test_axis_upwards(self, axis):
        xml = f"<QTM_Parameters_Ver_1.25><The_3D><AxisUpwards>{axis}</AxisUpwards></The_3D></QTM_Parameters_Ver_1.25>"
        assert parse_3d(xml).axis_upwards == axis


class TestParseSkeletons:
    def test_hierarchy(self, xml_skeleton):
        skeletons = parse_skeletons(xml_skeleton)
        assert [s.name for s in skeletons] == ["Subject"]
        q = skeletons[0]
        assert len(q.segment_ids) == 21
        assert q.names[1] == "Hips"
        assert 1 not in q.parents  # the root
        assert q.names[q.parents[2]] == "Hips"  # Spine nests inside Hips
        assert q.names[q.parents[17]] == "LeftFoot"  # four levels down
        assert q.joint_names()[:2] == ["Subject:Hips", "Subject:Spine"]

    def test_default_offsets_are_in_the_parent(self, xml_skeleton):
        q = parse_skeletons(xml_skeleton)[0]
        assert q.offsets[1] == pytest.approx((0.0, 0.0, 950.0))
        assert q.offsets[2] == pytest.approx((0.0, -10.0, 110.0))
        assert q.offsets[7] == pytest.approx((-145.0, 0.0, 0.0))  # left arm, out to -X

    def test_end_points_only_on_leaves_with_coordinates(self, xml_skeleton):
        q = parse_skeletons(xml_skeleton)[0]
        assert len(q.endpoints) == 5  # head top, two hands, two toes
        head = next(sid for sid, name in q.names.items() if name == "Head")
        assert q.endpoints[head] == pytest.approx((0.0, 0.0, 170.0))
        assert 1 not in q.endpoints  # <Endpoint/> without coordinates


class TestParse6D:
    def test_current_format(self):
        (body,) = parse_6d(PARAMETERS_XML)
        assert body.name == "Wand"
        assert body.color == "#0baccd"  # <Color R="11" G="172" B="205"/>
        assert body.enabled
        assert body.points == [(0.0, 0.0, 0.0), (90.0, 0.0, 0.0)]

    def test_legacy_format(self):
        xml = """<QTM_Parameters_Ver_1.20><The_6D><Bodies>1</Bodies><Body>
            <Name>Old</Name><Enabled>false</Enabled><RGBColor>255</RGBColor>
            <Point><X>1</X><Y>2</Y><Z>3</Z><Virtual>0</Virtual><PhysicalId>0</PhysicalId></Point>
            </Body></The_6D></QTM_Parameters_Ver_1.20>"""
        (body,) = parse_6d(xml)
        assert (body.name, body.color, body.enabled, body.points) == ("Old", "#ff0000", False, [(1.0, 2.0, 3.0)])

    def test_no_bodies(self, xml_3d):
        assert parse_6d(xml_3d) == []


class TestParseParameters:
    def test_all_sections(self):
        p = parse_parameters(PARAMETERS_XML)
        assert p.labels == ["Shoulder", "Elbow", "Wrist"]
        assert p.colors == ["#ff0000", "#00ff00", "#0000ff"]
        assert [b.name for b in p.bodies] == ["Wand"]
        assert p.joint_names() == ["S:Hips", "S:LeftUpLeg", "S:LeftLeg"]
        assert not p.is_empty()

    def test_missing_sections_are_kept(self, xml_3d, xml_skeleton):
        p = parse_parameters(xml_skeleton)
        assert p.labels == [] and len(p.skeletons) == 1
        p = parse_parameters(xml_3d, p)  # a 3D-only reply keeps the skeletons
        assert len(p.labels) == 22 and len(p.skeletons) == 1

    def test_empty_section_clears(self):
        p = parse_parameters(PARAMETERS_XML)
        p = parse_parameters("<QTM_Parameters_Ver_1.25><The_6D/><Skeletons/></QTM_Parameters_Ver_1.25>", p)
        assert p.bodies == [] and p.skeletons == []
        assert p.labels == ["Shoulder", "Elbow", "Wrist"]

    def test_previous_is_not_modified(self):
        previous = SceneParameters(labels=["A"])
        parse_parameters(PARAMETERS_XML, previous)
        assert previous.labels == ["A"]
