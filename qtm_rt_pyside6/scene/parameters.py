"""QTM parameter XML -> scene definitions.

Reads what a 3D view needs from ``getParameters(["3d", "6d", "skeleton"])``:

- 3D: label names and colors, user bones (``The_3D/Bones/Bone From/To/Color``)
  and ``AxisUpwards``
- 6D: rigid body names, colors and points
- skeletons: the segment hierarchy (``Segment`` elements nest inside their
  parent), each segment's ``ID``, its default position in its parent
  (``DefaultTransform/Position``) and the leaf end points (``Endpoint``)

QTM stores colors as ``0x00BBGGRR`` integers: red in the low byte.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

DEFAULT_MARKER_COLOR = "#e0e0e0"
DEFAULT_BONE_COLOR = "#a0a0a0"
DEFAULT_BODY_COLOR = "#e0e0e0"


def qtm_color(value) -> str:
    """QTM color integer (0x00BBGGRR, red in the low byte) -> "#rrggbb".

    Bone colors add an alpha byte on top and may arrive as negative numbers."""
    v = int(value) & 0xFFFFFFFF
    return f"#{v & 0xFF:02x}{(v >> 8) & 0xFF:02x}{(v >> 16) & 0xFF:02x}"


@dataclass
class Settings3D:
    labels: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)  # one per label
    bones: list[tuple[str, str, str]] = field(default_factory=list)  # (from label, to label, color)
    axis_upwards: str = "+Z"


@dataclass
class RigidBodyDef:
    name: str
    color: str = DEFAULT_BODY_COLOR
    enabled: bool = True
    points: list[tuple[float, float, float]] = field(default_factory=list)  # body-local marker points


@dataclass
class SkeletonDef:
    """A skeleton's segment hierarchy. Joint names are "<skeleton>:<segment>"."""

    name: str
    segment_ids: list[int] = field(default_factory=list)  # depth-first, as in the XML
    names: dict[int, str] = field(default_factory=dict)
    parents: dict[int, int] = field(default_factory=dict)  # child id -> parent id
    offsets: dict[int, tuple[float, float, float]] = field(default_factory=dict)  # default position in parent
    endpoints: dict[int, tuple[float, float, float]] = field(default_factory=dict)  # leaf id -> local end offset

    def joint_names(self) -> list[str]:
        return [f"{self.name}:{self.names[i]}" for i in self.segment_ids]


@dataclass
class SceneParameters:
    """Everything a 3D view needs from QTM's 3D, 6D and skeleton parameters."""

    labels: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    bones: list[tuple[str, str, str]] = field(default_factory=list)
    axis_upwards: str = "+Z"
    bodies: list[RigidBodyDef] = field(default_factory=list)
    skeletons: list[SkeletonDef] = field(default_factory=list)

    def joint_names(self) -> list[str]:
        return [name for skeleton in self.skeletons for name in skeleton.joint_names()]

    def body_names(self) -> list[str]:
        return [body.name for body in self.bodies]

    def is_empty(self) -> bool:
        return not (self.labels or self.bodies or self.skeletons)


# ---------------------------------------------------------------------------- 3D


def _root(xml) -> ET.Element:
    return xml if isinstance(xml, ET.Element) else ET.fromstring(xml)


def parse_3d(root) -> Settings3D:
    """Labels, label colors, user bones and the up axis from <The_3D>."""
    root = _root(root)
    settings = Settings3D()
    settings.axis_upwards = (root.findtext("./The_3D/AxisUpwards") or "+Z").strip() or "+Z"
    for label in root.findall("./The_3D/Label"):
        settings.labels.append(label.findtext("Name") or "")
        rgb = label.findtext("RGBColor")
        settings.colors.append(qtm_color(rgb) if rgb else DEFAULT_MARKER_COLOR)
    for bone in root.findall("./The_3D/Bones/Bone"):
        color = bone.get("Color")
        settings.bones.append(
            (bone.get("From", ""), bone.get("To", ""), qtm_color(color) if color else DEFAULT_BONE_COLOR)
        )
    return settings


# ---------------------------------------------------------------------------- 6D


def _xyz(element) -> tuple[float, float, float] | None:
    if element is None or element.get("X") is None:
        return None
    return float(element.get("X")), float(element.get("Y")), float(element.get("Z"))


def _body_color(body: ET.Element) -> str:
    color = body.find("Color")  # protocol 1.21 and later: <Color R="" G="" B=""/>
    if color is not None and color.get("R") is not None:
        rgb = (int(float(color.get(c, "0"))) & 0xFF for c in "RGB")
        return "#{:02x}{:02x}{:02x}".format(*rgb)
    legacy = body.findtext("RGBColor")  # older protocols: a 0x00BBGGRR integer
    return qtm_color(legacy) if legacy else DEFAULT_BODY_COLOR


def _body_points(body: ET.Element) -> list[tuple[float, float, float]]:
    points = []
    for point in body.findall("./Points/Point"):  # 1.21 and later: attributes
        p = _xyz(point)
        if p is not None:
            points.append(p)
    for point in body.findall("./Point"):  # older protocols: <Point><X>..</X>..</Point>
        try:
            points.append(tuple(float(point.findtext(c) or "nan") for c in "XYZ"))
        except ValueError:
            continue
    return points


def parse_6d(root) -> list[RigidBodyDef]:
    """Rigid bodies from <The_6D>, in the order QTM streams them."""
    root = _root(root)
    bodies = []
    for body in root.findall("./The_6D/Body"):
        enabled = (body.findtext("Enabled") or "true").strip().lower() != "false"
        bodies.append(
            RigidBodyDef(
                name=body.findtext("Name") or f"Body {len(bodies) + 1}",
                color=_body_color(body),
                enabled=enabled,
                points=_body_points(body),
            )
        )
    return bodies


# ---------------------------------------------------------------------------- skeletons


def parse_skeletons(root) -> list[SkeletonDef]:
    """Skeleton definitions from <Skeletons>, in the order QTM streams them."""
    root = _root(root)
    skeletons = []
    for element in root.findall("./Skeletons/Skeleton"):
        skeleton = SkeletonDef(element.get("Name") or f"Skeleton {len(skeletons) + 1}")

        def walk(parent_element, parent_id, skeleton=skeleton):
            # Child segments are nested inside their parent's <Segment> element
            for segment in parent_element.findall("Segment"):
                sid = int(segment.get("ID", "0"))
                skeleton.segment_ids.append(sid)
                skeleton.names[sid] = segment.get("Name") or f"Segment {sid}"
                if parent_id is not None:
                    skeleton.parents[sid] = parent_id
                offset = _xyz(segment.find("DefaultTransform/Position"))
                if offset is not None:
                    skeleton.offsets[sid] = offset
                end = _xyz(segment.find("Endpoint"))
                if end is not None:
                    skeleton.endpoints[sid] = end
                walk(segment, sid)

        segments = element.find("Segments")
        if segments is not None:
            walk(segments, None)
        skeletons.append(skeleton)
    return skeletons


# ---------------------------------------------------------------------------- all together


def parse_parameters(xml, previous: SceneParameters | None = None) -> SceneParameters:
    """Parse a getParameters() reply into SceneParameters.

    Sections missing from `xml` (e.g. a reply to getParameters(["3d"]) has no
    <Skeletons>) are kept from `previous`. Raises xml.etree.ElementTree.ParseError
    on malformed XML."""
    root = _root(xml)
    result = SceneParameters() if previous is None else SceneParameters(**vars(previous))
    if root.find("The_3D") is not None:
        settings = parse_3d(root)
        result.labels, result.colors, result.bones = settings.labels, settings.colors, settings.bones
        result.axis_upwards = settings.axis_upwards
    if root.find("The_6D") is not None:
        result.bodies = parse_6d(root)
    if root.find("Skeletons") is not None:
        result.skeletons = parse_skeletons(root)
    return result
