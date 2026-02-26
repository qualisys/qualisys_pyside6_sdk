import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick3D
import QTM 1.0

ApplicationWindow {
    id: window
    width: 1280
    height: 720
    visible: true
    title: "QTM 3D Viewer"
    color: "#1a1a2e"

    Backend {
        id: backend
    }

    // Custom styled button component
    component StyledButton: Button {
        id: styledBtn
        contentItem: Text {
            text: styledBtn.text
            color: styledBtn.enabled ? "#ffffff" : "#666"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            implicitWidth: 80
            implicitHeight: 30
            color: {
                if (!styledBtn.enabled) return "#2a2a4a"
                if (styledBtn.pressed) return "#3a8a7a"
                if (styledBtn.hovered) return "#5eccb3"
                return "#4ecca3"
            }
            radius: 4
        }
    }

    // Camera orbit state (all distances in mm)
    QtObject {
        id: cameraState
        property real distance: 5000.0  // 5 meters in mm
        property real azimuth: 45.0     // Horizontal angle
        property real elevation: 25.0   // Vertical angle
        property vector3d target: Qt.vector3d(0, 1000, 0)  // 1m up

        function updateCamera() {
            var azimuthRad = azimuth * Math.PI / 180
            var elevationRad = elevation * Math.PI / 180

            var x = target.x + distance * Math.cos(elevationRad) * Math.sin(azimuthRad)
            var y = target.y + distance * Math.sin(elevationRad)
            var z = target.z + distance * Math.cos(elevationRad) * Math.cos(azimuthRad)

            camera.position = Qt.vector3d(x, y, z)
            camera.lookAt(target)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: "#16213e"

            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 12

                Label {
                    text: "Host:"
                    color: "white"
                }

                TextField {
                    id: hostField
                    text: "127.0.0.1"
                    Layout.preferredWidth: 150
                    selectByMouse: true
                }

                StyledButton {
                    id: connectBtn
                    text: backend.connected ? "Disconnect" : "Connect"
                    onClicked: {
                        if (backend.connected) {
                            backend.disconnect()
                        } else {
                            backend.connect(hostField.text, 22223)
                        }
                    }
                }

                Rectangle { width: 1; height: 30; color: "#444" }

                StyledButton {
                    id: streamBtn
                    text: backend.streaming ? "Stop" : "Stream"
                    enabled: backend.connected
                    onClicked: {
                        if (backend.streaming) {
                            backend.stopStream()
                        } else {
                            backend.startStream()
                        }
                    }
                }

                Rectangle { width: 1; height: 30; color: "#444" }

                Label {
                    text: "FPS: " + backend.fps
                    color: "#4ecca3"
                    font.family: "monospace"
                }

                Label {
                    text: "Frame: " + backend.frameNumber
                    color: "#4ecca3"
                    font.family: "monospace"
                }

                Label {
                    text: "Markers: " + backend.markerCount
                    color: "#4ecca3"
                    font.family: "monospace"
                }

                Label {
                    text: "Skeletons: " + backend.skeletonCount
                    color: "#4ecca3"
                    font.family: "monospace"
                }

                Item { Layout.fillWidth: true }

                StyledButton {
                    text: "Reset View"
                    onClicked: {
                        cameraState.distance = 5000.0
                        cameraState.azimuth = 45.0
                        cameraState.elevation = 25.0
                        cameraState.target = Qt.vector3d(0, 1000, 0)
                        cameraState.updateCamera()
                    }
                }

                Label {
                    text: backend.status
                    color: "#888"
                }
            }
        }

        // Main content area
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Scene Tree Panel
            Rectangle {
                Layout.preferredWidth: 200
                Layout.fillHeight: true
                color: "#12122a"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 4

                    Label {
                        text: "Scene Graph"
                        color: "#4ecca3"
                        font.bold: true
                        font.pixelSize: 14
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: "#333"
                    }

                    ListView {
                        id: sceneTreeView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: backend.sceneTreeModel

                        delegate: Item {
                            width: sceneTreeView.width
                            height: 24

                            Row {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 4
                                leftPadding: model.indent * 16 + 4

                                Rectangle {
                                    width: 8
                                    height: 8
                                    radius: model.itemType === "header" || model.itemType === "markerGroup" ? 0 : 4
                                    color: {
                                        if (model.itemType === "header") return "#4ecca3"
                                        if (model.itemType === "markerGroup") return "#66aaff"
                                        if (model.itemType === "marker") return "#4488dd"
                                        if (model.itemType === "skeleton") return "#e0e0e0"
                                        if (model.itemType === "rigidBody") return "#ff9944"
                                        return "#888"
                                    }
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Label {
                                    text: model.name
                                    color: {
                                        if (model.itemType === "header") return "#4ecca3"
                                        if (model.itemType === "markerGroup") return "#66aaff"
                                        return "#aaa"
                                    }
                                    font.bold: model.itemType === "header" || model.itemType === "markerGroup"
                                    font.pixelSize: model.itemType === "header" ? 12 : 11
                                }
                            }
                        }
                    }
                }
            }

            // 3D View
            View3D {
                id: view3d
                Layout.fillWidth: true
                Layout.fillHeight: true

            environment: SceneEnvironment {
                clearColor: "#1a1a2e"
                backgroundMode: SceneEnvironment.Color
                antialiasingMode: SceneEnvironment.MSAA
                antialiasingQuality: SceneEnvironment.High
            }

            // Camera (distances in mm)
            PerspectiveCamera {
                id: camera
                clipNear: 10      // 1cm
                clipFar: 100000   // 100m

                Component.onCompleted: cameraState.updateCamera()
            }

            // Lights
            DirectionalLight {
                eulerRotation.x: -45
                eulerRotation.y: 45
                brightness: 1.0
            }

            DirectionalLight {
                eulerRotation.x: -45
                eulerRotation.y: -135
                brightness: 0.5
            }

            DirectionalLight {
                eulerRotation.x: 90
                brightness: 0.3
            }

            // Ground plane (10m x 10m) - #Rectangle is 100x100, so scale by 100 for 10000mm
            Model {
                source: "#Rectangle"
                scale: Qt.vector3d(100, 100, 1)  // 100 * 100 = 10000mm = 10m
                eulerRotation.x: -90
                position: Qt.vector3d(0, 0, 0)
                materials: [
                    PrincipledMaterial {
                        baseColor: "#2a2a4a"
                        roughness: 0.8
                    }
                ]
            }

            // Grid lines X (every 500mm = 0.5m, 21 lines = 10m span)
            // #Cube is 100x100x100, so scale accordingly
            Repeater3D {
                model: 21

                Model {
                    source: "#Cube"
                    position: Qt.vector3d((index - 10) * 500, 2, 0)
                    scale: Qt.vector3d(0.05, 0.02, 50)  // 5mm wide, 2mm tall, 5000mm long
                    materials: PrincipledMaterial {
                        baseColor: "#3a3a5a"
                        roughness: 1.0
                    }
                }
            }

            // Grid lines Z
            Repeater3D {
                model: 21

                Model {
                    source: "#Cube"
                    position: Qt.vector3d(0, 2, (index - 10) * 500)
                    scale: Qt.vector3d(50, 0.02, 0.05)  // 5000mm long, 2mm tall, 5mm wide
                    materials: PrincipledMaterial {
                        baseColor: "#3a3a5a"
                        roughness: 1.0
                    }
                }
            }

            // Coordinate axes (QTM right-handed Z-up system)
            // #Cylinder is height 100, diameter 100
            // X axis (red) - 500mm long, 10mm diameter
            Model {
                source: "#Cylinder"
                position: Qt.vector3d(250, 5, 0)
                eulerRotation.z: 90
                scale: Qt.vector3d(0.1, 5, 0.1)  // diameter 10mm, length 500mm
                materials: PrincipledMaterial {
                    baseColor: "#ff4444"
                    roughness: 0.5
                }
            }

            // Y axis (green) - points forward (QTM Y = Qt3D -Z)
            Model {
                source: "#Cylinder"
                position: Qt.vector3d(0, 5, -250)
                eulerRotation.x: 90
                scale: Qt.vector3d(0.1, 5, 0.1)  // diameter 10mm, length 500mm
                materials: PrincipledMaterial {
                    baseColor: "#44ff44"
                    roughness: 0.5
                }
            }

            // Z axis (blue) - points up (QTM Z = Qt3D Y)
            Model {
                source: "#Cylinder"
                position: Qt.vector3d(0, 250, 0)
                scale: Qt.vector3d(0.1, 5, 0.1)  // diameter 10mm, length 500mm
                materials: PrincipledMaterial {
                    baseColor: "#4444ff"
                    roughness: 0.5
                }
            }

            // Markers - #Sphere diameter is 100, so scale 0.15 = 15mm diameter
            Repeater3D {
                id: markerRepeater
                model: backend.markerModel

                delegate: Model {
                    source: "#Sphere"
                    position: model.position
                    scale: Qt.vector3d(0.15, 0.15, 0.15)  // 15mm diameter

                    materials: [
                        PrincipledMaterial {
                            baseColor: Qt.hsla((model.markerIndex * 0.05) % 1.0, 0.7, 0.55, 1.0)
                            roughness: 0.3
                            metalness: 0.1
                        }
                    ]
                }
            }

            // Skeleton bones - single cone from start to end
            Repeater3D {
                id: boneRepeater
                model: backend.boneModel

                delegate: Node {
                    id: boneNode

                    property vector3d startPos: model.startPos
                    property vector3d endPos: model.endPos
                    property vector3d direction: Qt.vector3d(
                        endPos.x - startPos.x,
                        endPos.y - startPos.y,
                        endPos.z - startPos.z
                    )
                    property real boneLength: Math.sqrt(
                        direction.x * direction.x +
                        direction.y * direction.y +
                        direction.z * direction.z
                    )

                    // Position at start of bone
                    position: startPos

                    // Rotate to align +Y with bone direction
                    rotation: {
                        if (boneLength < 0.001) return Qt.quaternion(1, 0, 0, 0)

                        var dx = direction.x / boneLength
                        var dy = direction.y / boneLength
                        var dz = direction.z / boneLength

                        var dot = dy
                        if (dot < -0.9999) return Qt.quaternion(0, 1, 0, 0)

                        var qw = 1 + dot
                        var qx = dz
                        var qy = 0
                        var qz = -dx

                        var len = Math.sqrt(qw*qw + qx*qx + qy*qy + qz*qz)
                        return Qt.quaternion(qw/len, qx/len, qy/len, qz/len)
                    }

                    // Bone width: 8% of length, max 30mm (0.3 scale)
                    property real boneWidth: Math.min(0.3, boneLength * 0.0008)

                    // Main cone: base at 20%, tip at end
                    Model {
                        source: "#Cone"
                        position: Qt.vector3d(0, boneLength * 0.2, 0)
                        scale: Qt.vector3d(boneWidth, boneLength * 0.8 / 100, boneWidth)

                        materials: PrincipledMaterial {
                            baseColor: "#e0e0e0"
                            roughness: 0.4
                        }
                    }

                    // Inverted cone: base at 20%, tip at start
                    Model {
                        source: "#Cone"
                        position: Qt.vector3d(0, boneLength * 0.2, 0)
                        eulerRotation: Qt.vector3d(180, 0, 0)
                        scale: Qt.vector3d(boneWidth, boneLength * 0.2 / 100, boneWidth)

                        materials: PrincipledMaterial {
                            baseColor: "#e0e0e0"
                            roughness: 0.4
                        }
                    }
                }
            }

            // Rigid bodies - displayed as 100mm XYZ axes
            Repeater3D {
                id: rigidBodyRepeater
                model: backend.rigidBodyModel

                delegate: Node {
                    position: model.position
                    rotation: model.rotation

                    // X axis (red) - 100mm
                    Model {
                        source: "#Cylinder"
                        position: Qt.vector3d(50, 0, 0)
                        eulerRotation: Qt.vector3d(0, 0, 90)
                        scale: Qt.vector3d(0.03, 1, 0.03)
                        materials: PrincipledMaterial { baseColor: "#ff4444" }
                    }

                    // Y axis (green) - 100mm (Qt3D Y = QTM Z)
                    Model {
                        source: "#Cylinder"
                        position: Qt.vector3d(0, 50, 0)
                        scale: Qt.vector3d(0.03, 1, 0.03)
                        materials: PrincipledMaterial { baseColor: "#44ff44" }
                    }

                    // Z axis (blue) - 100mm (Qt3D Z = QTM -Y)
                    Model {
                        source: "#Cylinder"
                        position: Qt.vector3d(0, 0, 50)
                        eulerRotation: Qt.vector3d(90, 0, 0)
                        scale: Qt.vector3d(0.03, 1, 0.03)
                        materials: PrincipledMaterial { baseColor: "#4444ff" }
                    }
                }
            }

            // Mouse handling for camera control
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

                property point lastPos

                onPressed: (mouse) => {
                    lastPos = Qt.point(mouse.x, mouse.y)
                }

                onPositionChanged: (mouse) => {
                    var dx = mouse.x - lastPos.x
                    var dy = mouse.y - lastPos.y

                    if (mouse.buttons & Qt.LeftButton) {
                        // Rotate
                        cameraState.azimuth -= dx * 0.5
                        cameraState.elevation += dy * 0.5
                        cameraState.elevation = Math.max(-89, Math.min(89, cameraState.elevation))
                        cameraState.updateCamera()
                    } else if (mouse.buttons & Qt.RightButton) {
                        // Pan (in mm)
                        var panSpeed = cameraState.distance * 0.002
                        var azimuthRad = cameraState.azimuth * Math.PI / 180

                        var right = Qt.vector3d(Math.cos(azimuthRad), 0, -Math.sin(azimuthRad))
                        var up = Qt.vector3d(0, 1, 0)

                        cameraState.target = Qt.vector3d(
                            cameraState.target.x - right.x * dx * panSpeed + up.x * dy * panSpeed,
                            cameraState.target.y - right.y * dx * panSpeed + up.y * dy * panSpeed,
                            cameraState.target.z - right.z * dx * panSpeed + up.z * dy * panSpeed
                        )
                        cameraState.updateCamera()
                    }

                    lastPos = Qt.point(mouse.x, mouse.y)
                }

                onWheel: (wheel) => {
                    // Zoom
                    var zoomFactor = wheel.angleDelta.y > 0 ? 0.9 : 1.1
                    cameraState.distance *= zoomFactor
                    cameraState.distance = Math.max(500, Math.min(50000, cameraState.distance))
                    cameraState.updateCamera()
                }
            }
        }
        }  // End RowLayout

        // Status bar
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            color: "#0f0f23"

            RowLayout {
                anchors.fill: parent
                anchors.margins: 4

                Label {
                    text: "Left-drag: rotate | Right-drag: pan | Scroll: zoom"
                    color: "#666"
                    font.pixelSize: 11
                }

                Item { Layout.fillWidth: true }

                Label {
                    text: "Distance: " + (cameraState.distance / 1000).toFixed(2) + "m"
                    color: "#666"
                    font.pixelSize: 11
                    font.family: "monospace"
                }
            }
        }
    }
}
