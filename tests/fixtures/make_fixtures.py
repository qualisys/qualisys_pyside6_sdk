"""Write the synthetic QTM parameter fixtures: params_3d.xml and params_skeleton.xml.

    python tests/fixtures/make_fixtures.py

The files have the layout QTM's RT server sends for getParameters(["3d"]) and
getParameters(["skeleton"]) (protocol 1.25), filled with invented values: plain
marker names, round body dimensions and a neutral calibration date. They are
not from any capture.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent

# QTM colors are 0x00BBGGRR integers (red in the low byte)
CENTER, LEFT, RIGHT, WAND = 0x800080, 0xFF0000, 0x0000FF, 0x00FF00
BONE_COLOR = -1380851536  # QTM's default bone color, with an alpha byte on top

LABELS = [
    ("HeadTop", CENTER),
    ("HeadFront", CENTER),
    ("HeadLeft", CENTER),
    ("HeadRight", CENTER),
    ("Sacrum", CENTER),
    ("L_Shoulder", LEFT),
    ("L_Elbow", LEFT),
    ("L_Wrist", LEFT),
    ("R_Shoulder", RIGHT),
    ("R_Elbow", RIGHT),
    ("R_Wrist", RIGHT),
    ("L_Hip", LEFT),
    ("L_Knee", LEFT),
    ("L_Ankle", LEFT),
    ("L_Toe", LEFT),
    ("R_Hip", RIGHT),
    ("R_Knee", RIGHT),
    ("R_Ankle", RIGHT),
    ("R_Toe", RIGHT),
    ("Wand_1", WAND),
    ("Wand_2", WAND),
    ("Wand_3", WAND),
]
BONES = [
    ("HeadTop", "HeadFront"),
    ("HeadLeft", "HeadRight"),
    ("L_Shoulder", "L_Elbow"),
    ("L_Elbow", "L_Wrist"),
    ("R_Shoulder", "R_Elbow"),
    ("R_Elbow", "R_Wrist"),
    ("L_Hip", "L_Knee"),
    ("L_Knee", "L_Ankle"),
    ("L_Ankle", "L_Toe"),
    ("R_Hip", "R_Knee"),
    ("R_Knee", "R_Ankle"),
    ("R_Ankle", "R_Toe"),
    ("Wand_1", "Wand_2"),
    ("Wand_2", "Wand_3"),
]

# (id, name, parent id, offset in parent, end point or None, markers as (name, offset)).
# Segment axes as in QTM: X right, Y forward, Z up.
SEGMENTS = [
    (1, "Hips", None, (0, 0, 950), None, [("Sacrum", (0, -110, 30))]),
    (2, "Spine", 1, (0, -10, 110), None, []),
    (3, "Spine1", 2, (0, 0, 190), None, []),
    (4, "Neck", 3, (0, 0, 190), None, []),
    (5, "Head", 4, (0, 15, 100), (0, 0, 170), [("HeadTop", (0, 0, 185)), ("HeadFront", (0, 95, 105))]),
    (6, "LeftShoulder", 3, (-35, 0, 150), None, []),
    (7, "LeftArm", 6, (-145, 0, 0), None, [("L_Shoulder", (-25, 0, 35))]),
    (8, "LeftForeArm", 7, (0, 0, -285), None, [("L_Elbow", (-35, 0, 0))]),
    (9, "LeftHand", 8, (0, 0, -255), (0, 0, -90), [("L_Wrist", (-30, 0, 0))]),
    (10, "RightShoulder", 3, (35, 0, 150), None, []),
    (11, "RightArm", 10, (145, 0, 0), None, [("R_Shoulder", (25, 0, 35))]),
    (12, "RightForeArm", 11, (0, 0, -285), None, [("R_Elbow", (35, 0, 0))]),
    (13, "RightHand", 12, (0, 0, -255), (0, 0, -90), [("R_Wrist", (30, 0, 0))]),
    (14, "LeftUpLeg", 1, (-95, 0, -55), None, [("L_Hip", (-60, 0, 0))]),
    (15, "LeftLeg", 14, (0, 0, -430), None, [("L_Knee", (-50, 0, 0))]),
    (16, "LeftFoot", 15, (0, 0, -410), None, [("L_Ankle", (-40, 0, 0))]),
    (17, "LeftToeBase", 16, (0, 125, -65), (0, 60, 0), [("L_Toe", (0, 45, 0))]),
    (18, "RightUpLeg", 1, (95, 0, -55), None, [("R_Hip", (60, 0, 0))]),
    (19, "RightLeg", 18, (0, 0, -430), None, [("R_Knee", (50, 0, 0))]),
    (20, "RightFoot", 19, (0, 0, -410), None, [("R_Ankle", (40, 0, 0))]),
    (21, "RightToeBase", 20, (0, 125, -65), (0, 60, 0), [("R_Toe", (0, 45, 0))]),
]


def xyz(tag: str, p, indent: str) -> str:
    return f'{indent}<{tag} X="{p[0]:.6f}" Y="{p[1]:.6f}" Z="{p[2]:.6f}"/>\n'


def params_3d() -> str:
    out = "<QTM_Parameters_Ver_1.25>\n    <The_3D>\n"
    out += "        <AxisUpwards>+Z</AxisUpwards>\n"
    out += "        <CalibrationTime>2000-01-01 00:00:00</CalibrationTime>\n"
    out += f"        <Labels>{len(LABELS)}</Labels>\n"
    for name, color in LABELS:
        out += "        <Label>\n"
        out += f"            <Name>{name}</Name>\n"
        out += f"            <RGBColor>{color}</RGBColor>\n"
        out += "            <Trajectory_Type>Measured</Trajectory_Type>\n"
        out += "        </Label>\n"
    out += "        <Bones>\n"
    for a, b in BONES:
        out += f'            <Bone From="{a}" To="{b}" Color="{BONE_COLOR}"/>\n'
    out += "        </Bones>\n    </The_3D>\n</QTM_Parameters_Ver_1.25>\n"
    return out


def params_skeleton() -> str:
    children: dict[int | None, list] = {}
    for segment in SEGMENTS:
        children.setdefault(segment[2], []).append(segment)

    def segment_xml(segment, depth: int) -> str:
        sid, name, parent, offset, end, markers = segment
        i = " " * (16 + 4 * depth)
        out = f'{i}<Segment Name="{name}" ID="{sid}">\n'
        if parent is None:
            out += f"{i}    <Solver>Global Optimization</Solver>\n"
        for tag in ("Transform", "DefaultTransform"):
            out += f"{i}    <{tag}>\n" + xyz("Position", offset, i + "        ")
            out += f'{i}        <Rotation X="0.000000" Y="0.000000" Z="0.000000" W="1.000000"/>\n'
            out += f"{i}    </{tag}>\n"
        out += f"{i}    <DegreesOfFreedom>\n"
        dofs = ("RotationX", "RotationY", "RotationZ") + (
            ("TranslationX", "TranslationY", "TranslationZ") if parent is None else ()
        )
        out += "".join(f"{i}        <{dof}/>\n" for dof in dofs)
        out += f"{i}    </DegreesOfFreedom>\n"
        out += xyz("Endpoint", end, i + "    ") if end is not None else f"{i}    <Endpoint/>\n"
        out += f"{i}    <Markers>\n"
        for marker, position in markers:
            out += f'{i}        <Marker Name="{marker}">\n' + xyz("Position", position, i + "            ")
            out += f"{i}            <Weight>1.000000</Weight>\n{i}        </Marker>\n"
        out += f"{i}    </Markers>\n{i}    <RigidBodies/>\n"
        out += "".join(segment_xml(child, depth + 1) for child in children.get(sid, []))
        return out + f"{i}</Segment>\n"

    out = '<QTM_Parameters_Ver_1.25>\n    <Skeletons>\n        <Skeleton Name="Subject">\n'
    out += "            <Scale>1.000000</Scale>\n            <Segments>\n"
    out += "".join(segment_xml(root, 0) for root in children[None])
    out += "            </Segments>\n        </Skeleton>\n    </Skeletons>\n</QTM_Parameters_Ver_1.25>\n"
    return out


if __name__ == "__main__":
    (HERE / "params_3d.xml").write_text(params_3d(), encoding="utf-8", newline="\n")
    (HERE / "params_skeleton.xml").write_text(params_skeleton(), encoding="utf-8", newline="\n")
    print("wrote", HERE / "params_3d.xml", "and", HERE / "params_skeleton.xml")
