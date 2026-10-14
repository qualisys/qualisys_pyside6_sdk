"""Build binary QTM data packets (QRTPacket) for the scene tests."""

import struct

from qtm_rt.packet import QRTComponentType, QRTPacket


def _component(component_type: QRTComponentType, body: bytes) -> bytes:
    # Component size includes its own 8-byte (size, type) header
    return struct.pack("<II", len(body) + 8, component_type.value) + body


def build_packet(
    frame_number: int = 1,
    timestamp: int = 0,
    *,
    labeled=None,
    unlabeled=None,
    bodies=None,
    skeletons=None,
) -> QRTPacket:
    """A data packet with the given components (None leaves a component out).

    labeled: [(x, y, z)]; unlabeled: [(x, y, z, id)]; bodies: [((x, y, z), 9-float matrix)];
    skeletons: [[(segment id, (x, y, z), (qx, qy, qz, qw))]] per skeleton."""
    components = []
    if labeled is not None:
        body = struct.pack("<Ihh", len(labeled), 0, 0) + b"".join(struct.pack("<3f", *p) for p in labeled)
        components.append(_component(QRTComponentType.Component3d, body))
    if unlabeled is not None:
        body = struct.pack("<Ihh", len(unlabeled), 0, 0)
        body += b"".join(struct.pack("<3fi", x, y, z, marker_id) for x, y, z, marker_id in unlabeled)
        components.append(_component(QRTComponentType.Component3dNoLabels, body))
    if bodies is not None:
        body = struct.pack("<ihh", len(bodies), 0, 0)
        body += b"".join(struct.pack("<3f", *p) + struct.pack("<9f", *m) for p, m in bodies)
        components.append(_component(QRTComponentType.Component6d, body))
    if skeletons is not None:
        body = struct.pack("<i", len(skeletons))
        for segments in skeletons:
            body += struct.pack("<i", len(segments))
            for sid, p, q in segments:
                body += struct.pack("<i", sid) + struct.pack("<3f", *p) + struct.pack("<4f", *q)
        components.append(_component(QRTComponentType.ComponentSkeleton, body))
    header = struct.pack("<qII", timestamp, frame_number, len(components))
    return QRTPacket(header + b"".join(components))


IDENTITY_MATRIX = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)

PARAMETERS_XML = """<QTM_Parameters_Ver_1.25>
    <The_3D>
        <AxisUpwards>+Z</AxisUpwards>
        <Labels>3</Labels>
        <Label><Name>Shoulder</Name><RGBColor>255</RGBColor></Label>
        <Label><Name>Elbow</Name><RGBColor>65280</RGBColor></Label>
        <Label><Name>Wrist</Name><RGBColor>16711680</RGBColor></Label>
        <Bones>
            <Bone From="Shoulder" To="Elbow" Color="-1380851536"/>
            <Bone From="Elbow" To="Wrist"/>
            <Bone From="Elbow" To="Nowhere"/>
        </Bones>
    </The_3D>
    <The_6D>
        <Body>
            <Name>Wand</Name>
            <Enabled>true</Enabled>
            <Color R="11" G="172" B="205"/>
            <Points>
                <Point X="0" Y="0" Z="0" Virtual="0" PhysicalId="0" Name="a"/>
                <Point X="90" Y="0" Z="0" Virtual="0" PhysicalId="0" Name="b"/>
            </Points>
        </Body>
    </The_6D>
    <Skeletons>
        <Skeleton Name="S">
            <Segments>
                <Segment Name="Hips" ID="1">
                    <DefaultTransform><Position X="0" Y="0" Z="950"/></DefaultTransform>
                    <Endpoint/>
                    <Segment Name="LeftUpLeg" ID="2">
                        <DefaultTransform><Position X="-90" Y="0" Z="-50"/></DefaultTransform>
                        <Endpoint/>
                        <Segment Name="LeftLeg" ID="3">
                            <DefaultTransform><Position X="0" Y="0" Z="-430"/></DefaultTransform>
                            <Endpoint X="0" Y="0" Z="-420"/>
                        </Segment>
                    </Segment>
                </Segment>
            </Segments>
        </Skeleton>
    </Skeletons>
</QTM_Parameters_Ver_1.25>
"""
