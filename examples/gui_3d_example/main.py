"""
Qt Quick 3D Example - Visualize QTM markers and skeletons in 3D

Shows motion capture markers as spheres and skeleton bones as cones.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtCore import Property, QAbstractListModel, QByteArray, QModelIndex, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QQuaternion, QVector3D
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from qtm_rt_pyside6 import QRTPacket, QTMConnection, QTMDiscovery


def qtm_to_qt3d_position(x, y, z):
    """Convert QTM coordinates (Z-up) to Qt3D coordinates (Y-up)"""
    return QVector3D(x, z, -y)


def qtm_to_qt3d_quaternion(x, y, z, w):
    """Convert QTM quaternion (Z-up) to Qt3D quaternion (Y-up)"""
    # Rotate the quaternion to account for coordinate system change
    # QTM: X-right, Y-forward, Z-up
    # Qt3D: X-right, Y-up, Z-backward
    return QQuaternion(w, x, z, -y)


class MarkerModel(QAbstractListModel):
    """Model providing marker positions to QML"""

    PositionRole = Qt.UserRole + 1
    IndexRole = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._positions = []  # Pre-converted QVector3D list

    def rowCount(self, parent=QModelIndex()):
        return len(self._positions)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._positions):
            return None

        if role == self.PositionRole:
            return self._positions[index.row()]
        elif role == self.IndexRole:
            return index.row()

        return None

    def roleNames(self):
        return {
            self.PositionRole: QByteArray(b"position"),
            self.IndexRole: QByteArray(b"markerIndex"),
        }

    @Slot(list)
    def updateMarkers(self, markers):
        """Update markers - markers is list of (x, y, z) tuples"""
        old_count = len(self._positions)
        new_count = len(markers)

        # Pre-convert all positions
        new_positions = [qtm_to_qt3d_position(m[0], m[1], m[2]) for m in markers]

        # Only do row changes if count changed
        if new_count != old_count:
            self.beginResetModel()
            self._positions = new_positions
            self.endResetModel()
        else:
            self._positions = new_positions
            if new_count > 0:
                self.dataChanged.emit(self.index(0), self.index(new_count - 1), [self.PositionRole])


class BoneModel(QAbstractListModel):
    """Model providing bone data (start, end positions) to QML"""

    StartPosRole = Qt.UserRole + 1
    EndPosRole = Qt.UserRole + 2
    IndexRole = Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bones = []  # List of (start_pos, end_pos) tuples

    def rowCount(self, parent=QModelIndex()):
        return len(self._bones)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._bones):
            return None

        bone = self._bones[index.row()]

        if role == self.StartPosRole:
            return bone[0]  # Already QVector3D
        elif role == self.EndPosRole:
            return bone[1]  # Already QVector3D
        elif role == self.IndexRole:
            return index.row()

        return None

    def roleNames(self):
        return {
            self.StartPosRole: QByteArray(b"startPos"),
            self.EndPosRole: QByteArray(b"endPos"),
            self.IndexRole: QByteArray(b"boneIndex"),
        }

    def updateBones(self, bones):
        old_count = len(self._bones)
        new_count = len(bones)

        # Only reset model if count changed
        if new_count != old_count:
            self.beginResetModel()
            self._bones = bones
            self.endResetModel()
        else:
            self._bones = bones
            if new_count > 0:
                self.dataChanged.emit(self.index(0), self.index(new_count - 1), [self.StartPosRole, self.EndPosRole])


class RigidBodyModel(QAbstractListModel):
    """Model providing rigid body position and rotation to QML"""

    PositionRole = Qt.UserRole + 1
    RotationRole = Qt.UserRole + 2
    NameRole = Qt.UserRole + 3
    IndexRole = Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bodies = []  # List of (position, rotation, name) tuples
        self._names = []  # Body names from parameters

    def rowCount(self, parent=QModelIndex()):
        return len(self._bodies)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._bodies):
            return None

        body = self._bodies[index.row()]

        if role == self.PositionRole:
            return body[0]  # QVector3D
        elif role == self.RotationRole:
            return body[1]  # QQuaternion
        elif role == self.NameRole:
            return body[2]  # str
        elif role == self.IndexRole:
            return index.row()

        return None

    def roleNames(self):
        return {
            self.PositionRole: QByteArray(b"position"),
            self.RotationRole: QByteArray(b"rotation"),
            self.NameRole: QByteArray(b"name"),
            self.IndexRole: QByteArray(b"bodyIndex"),
        }

    def setNames(self, names: list[str]):
        self._names = names

    def updateBodies(self, bodies):
        old_count = len(self._bodies)
        new_count = len(bodies)

        # Only reset model if count changed
        if new_count != old_count:
            self.beginResetModel()
            self._bodies = bodies
            self.endResetModel()
        else:
            self._bodies = bodies
            if new_count > 0:
                self.dataChanged.emit(self.index(0), self.index(new_count - 1), [self.PositionRole, self.RotationRole])


class SceneTreeModel(QAbstractListModel):
    """Model for scene tree display"""

    NameRole = Qt.UserRole + 1
    TypeRole = Qt.UserRole + 2
    IndentRole = Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []  # List of (name, type, indent) tuples

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None

        item = self._items[index.row()]

        if role == self.NameRole:
            return item[0]
        elif role == self.TypeRole:
            return item[1]
        elif role == self.IndentRole:
            return item[2]

        return None

    def roleNames(self):
        return {
            self.NameRole: QByteArray(b"name"),
            self.TypeRole: QByteArray(b"itemType"),
            self.IndentRole: QByteArray(b"indent"),
        }

    def updateTree(self, marker_names, skeleton_names, rigid_body_names):
        self.beginResetModel()
        self._items = []

        # Markers - group by prefix if name contains underscore
        self._items.append((f"Markers ({len(marker_names)})", "header", 0))

        # Group markers by prefix
        groups = {}
        ungrouped = []
        for name in marker_names:
            if "_" in name:
                prefix = name.rsplit("_", 1)[0]
                if prefix not in groups:
                    groups[prefix] = []
                groups[prefix].append(name.rsplit("_", 1)[1])
            else:
                ungrouped.append(name)

        # Add grouped markers
        for prefix in sorted(groups.keys()):
            markers = groups[prefix]
            self._items.append((f"{prefix} ({len(markers)})", "markerGroup", 1))
            for marker in markers:
                self._items.append((marker, "marker", 2))

        # Add ungrouped markers
        for name in ungrouped:
            self._items.append((name, "marker", 1))

        # Skeletons
        self._items.append((f"Skeletons ({len(skeleton_names)})", "header", 0))
        for name in skeleton_names:
            self._items.append((name, "skeleton", 1))

        # Rigid Bodies
        self._items.append((f"Rigid Bodies ({len(rigid_body_names)})", "header", 0))
        for name in rigid_body_names:
            self._items.append((name, "rigidBody", 1))

        self.endResetModel()


class SkeletonDefinition:
    """Holds skeleton hierarchy parsed from QTM parameters"""

    def __init__(self):
        self.segments: dict[int, str] = {}  # id -> name
        self.parent_map: dict[int, int] = {}  # child_id -> parent_id

    def parse_xml(self, xml_str: str):
        """Parse skeleton parameters XML"""
        self.segments.clear()
        self.parent_map.clear()

        try:
            root = ET.fromstring(xml_str)

            for skeleton in root.findall(".//Skeleton"):
                # Segments are inside <Segments> container
                segments_container = skeleton.find("Segments")
                if segments_container is not None:
                    self._parse_segments(segments_container, parent_id=None)

        except ET.ParseError as e:
            print(f"Failed to parse skeleton XML: {e}")

    def _parse_segments(self, element, parent_id: int | None):
        """Recursively parse segment hierarchy"""
        # Find direct Segment children
        segments = element.findall("Segment")
        for segment in segments:
            seg_id = int(segment.get("ID", 0))
            seg_name = segment.get("Name", f"Segment_{seg_id}")

            self.segments[seg_id] = seg_name

            if parent_id is not None:
                self.parent_map[seg_id] = parent_id

            # Recurse into nested segments (children are nested inside parent)
            self._parse_segments(segment, parent_id=seg_id)

    def get_bone_connections(self) -> list[tuple[int, int]]:
        """Get list of (parent_id, child_id) for all bones"""
        return [(parent, child) for child, parent in self.parent_map.items()]


class Backend(QObject):
    """Backend for QML - handles QTM connection and data"""

    connectedChanged = Signal()
    streamingChanged = Signal()
    statusChanged = Signal()
    fpsChanged = Signal()
    frameNumberChanged = Signal()
    markerCountChanged = Signal()
    skeletonCountChanged = Signal()
    rigidBodyCountChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._connected = False
        self._streaming = False
        self._status = "Ready"
        self._fps = 0
        self._frame_number = 0
        self._marker_count = 0
        self._skeleton_count = 0
        self._rigid_body_count = 0
        self._frame_count = 0

        # Models for QML
        self._marker_model = MarkerModel(self)
        self._bone_model = BoneModel(self)
        self._rigid_body_model = RigidBodyModel(self)
        self._scene_tree_model = SceneTreeModel(self)

        # Skeleton definition (hierarchy)
        self._skeleton_def = SkeletonDefinition()
        self._skeleton_names: list[str] = []
        self._bone_connections: list[tuple[int, int]] = []

        # Rigid body names
        self._rigid_body_names: list[str] = []

        # Marker names
        self._marker_names: list[str] = []

        # QTM connection
        self._connection = QTMConnection(self)
        self._connection.connected.connect(self._on_connected)
        self._connection.disconnected.connect(self._on_disconnected)
        self._connection.error.connect(self._on_error)
        self._connection.packetReceived.connect(self._on_packet)
        self._connection.responseReceived.connect(self._on_response)

        # Discovery
        self._discovery = QTMDiscovery(self, timeout_ms=2000)

        # FPS timer
        from PySide6.QtCore import QTimer

        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.setInterval(1000)

        # Render timer - processes latest packet at 60 Hz (drops intermediate packets)
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._process_latest_packet)
        self._render_timer.setInterval(1000 // 60)  # ~16ms
        self._latest_packet = None

    # Properties
    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._connected

    @Property(bool, notify=streamingChanged)
    def streaming(self):
        return self._streaming

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(int, notify=fpsChanged)
    def fps(self):
        return self._fps

    @Property(int, notify=frameNumberChanged)
    def frameNumber(self):
        return self._frame_number

    @Property(int, notify=markerCountChanged)
    def markerCount(self):
        return self._marker_count

    @Property(int, notify=skeletonCountChanged)
    def skeletonCount(self):
        return self._skeleton_count

    @Property(int, notify=rigidBodyCountChanged)
    def rigidBodyCount(self):
        return self._rigid_body_count

    @Property(QObject, constant=True)
    def markerModel(self):
        return self._marker_model

    @Property(QObject, constant=True)
    def boneModel(self):
        return self._bone_model

    @Property(QObject, constant=True)
    def rigidBodyModel(self):
        return self._rigid_body_model

    @Property(QObject, constant=True)
    def sceneTreeModel(self):
        return self._scene_tree_model

    # Slots
    @Slot(str, int)
    def connect(self, host: str, port: int = 22223):
        self._status = f"Connecting to {host}..."
        self.statusChanged.emit()
        self._connection.connectToHost(host, port)

    @Slot()
    def disconnect(self):
        if self._streaming:
            self.stopStream()
        self._connection.disconnectFromHost()

    @Slot()
    def startStream(self):
        if self._connected and not self._streaming:
            # Stream 3D markers, skeleton data, and 6DOF rigid bodies
            self._connection.streamFrames(["3d", "skeleton:global", "6d"])
            self._streaming = True
            self._frame_count = 0
            self._latest_packet = None
            self._fps_timer.start()
            self._render_timer.start()
            self.streamingChanged.emit()
            self._status = "Streaming..."
            self.statusChanged.emit()

    @Slot()
    def stopStream(self):
        if self._streaming:
            self._connection.streamFramesStop()
            self._streaming = False
            self._fps_timer.stop()
            self._render_timer.stop()
            self._latest_packet = None
            self._fps = 0
            self.streamingChanged.emit()
            self.fpsChanged.emit()
            self._status = "Connected"
            self.statusChanged.emit()

    # Internal handlers
    def _on_connected(self):
        self._connected = True
        self._status = "Getting parameters..."
        self.connectedChanged.emit()
        self.statusChanged.emit()

        # Request 3d, skeleton and 6d parameters
        self._connection.getParameters(["3d", "skeleton", "6d"])

    def _on_response(self, command: str, data):
        if command == "getparameters":
            # Parse marker names from 3D parameters
            self._marker_names = self._parse_marker_names(data)

            # Parse skeleton hierarchy and names from XML
            self._skeleton_def.parse_xml(data)
            self._bone_connections = self._skeleton_def.get_bone_connections()

            # Parse skeleton names
            self._skeleton_names = self._parse_skeleton_names(data)

            # Parse 6D body names
            self._rigid_body_names = self._parse_6d_body_names(data)
            self._rigid_body_model.setNames(self._rigid_body_names)

            print(
                f"Parsed {len(self._marker_names)} markers, {len(self._skeleton_def.segments)} segments, {len(self._bone_connections)} bones, {len(self._rigid_body_names)} rigid bodies"
            )

            # Update scene tree
            self._scene_tree_model.updateTree(self._marker_names, self._skeleton_names, self._rigid_body_names)

            self._status = "Connected"
            self.statusChanged.emit()

    def _parse_skeleton_names(self, xml_str: str) -> list[str]:
        """Parse skeleton names from XML"""
        names = []
        try:
            root = ET.fromstring(xml_str)
            for skeleton in root.findall(".//Skeleton"):
                name = skeleton.get("Name", "Unknown")
                names.append(name)
        except ET.ParseError:
            pass
        return names

    def _parse_6d_body_names(self, xml_str: str) -> list[str]:
        """Parse 6D rigid body names from XML"""
        names = []
        try:
            root = ET.fromstring(xml_str)
            for body in root.findall(".//Body"):
                name = body.find("Name")
                if name is not None and name.text:
                    names.append(name.text)
        except ET.ParseError:
            pass
        return names

    def _parse_marker_names(self, xml_str: str) -> list[str]:
        """Parse 3D marker names from XML"""
        names = []
        try:
            root = ET.fromstring(xml_str)
            # Look for Label elements in The_3D section
            for label in root.findall(".//The_3D//Label"):
                name = label.find("Name")
                if name is not None and name.text:
                    names.append(name.text)
        except ET.ParseError:
            pass
        return names

    def _on_disconnected(self):
        self._connected = False
        self._streaming = False
        self._status = "Disconnected"
        self._fps_timer.stop()
        self._render_timer.stop()
        self._skeleton_def = SkeletonDefinition()
        self._skeleton_names = []
        self._bone_connections = []
        self._rigid_body_names = []
        self._marker_names = []
        self.connectedChanged.emit()
        self.streamingChanged.emit()
        self.statusChanged.emit()

    def _on_error(self, error: str):
        self._status = f"Error: {error}"
        self.statusChanged.emit()

    def _on_packet(self, packet: QRTPacket):
        """Store latest packet - will be processed by render timer"""
        self._frame_count += 1
        self._latest_packet = packet

    def _process_latest_packet(self):
        """Process the latest packet (called by render timer at 60Hz)"""
        packet = self._latest_packet
        if packet is None:
            return

        self._frame_number = packet.framenumber
        self.frameNumberChanged.emit()

        # Update markers
        marker_result = packet.get_3d_markers()
        if marker_result is not None:
            header, markers = marker_result
            self._marker_count = header.marker_count
            self.markerCountChanged.emit()

            positions = [(m.x, m.y, m.z) for m in markers]
            self._marker_model.updateMarkers(positions)

        # Update skeletons
        skeleton_result = packet.get_skeletons()
        if skeleton_result is not None:
            header, skeletons = skeleton_result
            self._skeleton_count = header.skeleton_count
            self.skeletonCountChanged.emit()

            # Build bones from all skeletons
            all_bones = []
            for skeleton_segments in skeletons:
                # Create dict of segment_id -> position
                segment_positions: dict[int, QVector3D] = {}
                for seg_id, position, _rotation in skeleton_segments:
                    pos = qtm_to_qt3d_position(position.x, position.y, position.z)
                    segment_positions[seg_id] = pos

                # Create bones based on hierarchy
                for parent_id, child_id in self._bone_connections:
                    if parent_id in segment_positions and child_id in segment_positions:
                        start = segment_positions[parent_id]
                        end = segment_positions[child_id]
                        all_bones.append((start, end))

            self._bone_model.updateBones(all_bones)

        # Update rigid bodies (6DOF)
        rigid_body_result = packet.get_6d()
        if rigid_body_result is not None:
            header, bodies = rigid_body_result
            self._rigid_body_count = header.body_count
            self.rigidBodyCountChanged.emit()

            body_data = []
            for i, (position, rotation) in enumerate(bodies):
                pos = qtm_to_qt3d_position(position.x, position.y, position.z)
                rot = qtm_to_qt3d_quaternion(rotation.x, rotation.y, rotation.z, rotation.w)
                name = self._rigid_body_names[i] if i < len(self._rigid_body_names) else f"Body {i}"
                body_data.append((pos, rot, name))

            self._rigid_body_model.updateBodies(body_data)

    def _update_fps(self):
        self._fps = self._frame_count
        self._frame_count = 0
        self.fpsChanged.emit()


def main():
    app = QGuiApplication(sys.argv)

    qmlRegisterType(Backend, "QTM", 1, 0, "Backend")

    engine = QQmlApplicationEngine()

    qml_file = Path(__file__).parent / "main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print("Failed to load QML")
        return -1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
