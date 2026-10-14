import QtQuick
import QtQuick.Layouts
import QtQuick3D
import QtQuick3D.Helpers

// A ready-made 3D view of a QtmScene: markers, QTM bones, skeletons, rigid
// bodies, labels, floor, grid and axes, with QTM's mouse (left orbit, right
// pan, wheel zoom) and picking.
//
//     QtmView { anchors.fill: parent; scene: qtmScene }
//
// 3D children are added to the scene: QtmView { scene: qtmScene; Model { ... } }
Item {
    id: root
    property QtObject scene: null

    // Layers
    property bool showFloor: true
    property bool showGrid: true
    property bool showAxes: true
    property bool showMarkers: true
    property bool showUnlabeled: true
    property bool showBones: true
    property bool showSkeletons: true
    property bool showRigidBodies: true
    property string labelMode: "highlighted"    // "none" | "highlighted" (and hovered) | "all"
    property string boneStyle: "keeled"         // "keeled" | "octahedral" | "capsule" | "stick"
    property string axesMode: "none"            // skeleton tripods: "none" | "selected" | "all"
    property bool showToggles: true             // the layer switches in the top-right corner

    // Behaviour
    property bool autoFit: true                 // fit the camera to the first frame with data
    property bool hoverEnabled: true            // hovered points grow and show their name
    property bool pickEnabled: true
    property bool shadows: true

    readonly property alias view3d: view3d
    readonly property alias camera: camera
    readonly property alias cameraController: controller
    readonly property alias markerLayer: markers
    readonly property alias boneLayer: bones
    readonly property alias skeletonLayer: skeletons
    readonly property alias rigidBodyLayer: bodies
    readonly property alias labels: labelOverlay
    property alias environment: view3d.environment
    default property alias content: userContent.data

    // A click on a marker, joint or rigid body ("" on empty space)
    signal picked(string name, int button)

    function fit() { controller.fit() }

    // Mouse ray in scene coordinates: [origin, direction]
    function rayAt(x, y) {
        var o = view3d.mapTo3DScene(Qt.vector3d(x, y, 0))
        return [o, view3d.mapTo3DScene(Qt.vector3d(x, y, 1000)).minus(o)]
    }

    // The point under (x, y) in view coordinates, or ""
    function pickAt(x, y) {
        if (!root.scene)
            return ""
        var r = rayAt(x, y)
        return root.scene.pick(r[0], r[1])
    }

    Connections {
        target: root.scene
        function onFirstData() { if (root.autoFit) controller.fit() }
    }

    View3D {
        id: view3d
        anchors.fill: parent
        camera: camera

        environment: ExtendedSceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: QtmTheme.sceneBackground
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            tonemapMode: SceneEnvironment.TonemapModeFilmic
            aoEnabled: true
            aoStrength: 40
            aoDistance: 40
            aoSoftness: 50
            // Image-based light only: the sky lights the scene, the background stays flat
            lightProbe: Texture {
                textureData: ProceduralSkyTextureData {
                    skyTopColor: "#3a3a3a"
                    skyHorizonColor: "#2a2a2a"
                    groundHorizonColor: "#2a2a2a"
                    groundBottomColor: "#151515"
                }
            }
            probeExposure: 0.6
        }

        PerspectiveCamera {
            id: camera
            clipNear: 20
            clipFar: 200000
        }

        // Key light with soft shadows on the floor, plus a dim fill from the other side
        DirectionalLight {
            eulerRotation: Qt.vector3d(-50, -150, 0)
            brightness: 1.1
            castsShadow: root.shadows
            shadowMapQuality: Light.ShadowMapQualityHigh
            shadowFactor: 45
        }
        DirectionalLight {
            eulerRotation: Qt.vector3d(-20, 60, 0)
            brightness: 0.35
        }

        Floor {
            visible: root.showFloor || root.showGrid
            showPlane: root.showFloor
            showGrid: root.showGrid
        }
        QtmAxes {
            visible: root.showAxes
            scene: root.scene
        }
        BoneLayer {
            id: bones
            visible: root.showBones
            scene: root.scene
            castsShadows: root.shadows
        }
        SkeletonLayer {
            id: skeletons
            visible: root.showSkeletons
            scene: root.scene
            boneStyle: root.boneStyle
            axesMode: root.axesMode
            castsShadows: root.shadows
        }
        RigidBodyLayer {
            id: bodies
            visible: root.showRigidBodies
            scene: root.scene
            castsShadows: root.shadows
        }
        MarkerLayer {
            id: markers
            visible: root.showMarkers
            showUnlabeled: root.showUnlabeled
            scene: root.scene
            castsShadows: root.shadows
        }

        Node { id: userContent }
    }

    LabelOverlay {
        id: labelOverlay
        anchors.fill: view3d
        view: view3d
        scene: root.scene
        mode: root.labelMode
        showMarkers: root.showMarkers
        showJoints: root.showSkeletons && !root.showMarkers  // joint names only when markers are hidden
        showBodies: root.showRigidBodies
    }

    QtmCameraController {
        id: controller
        anchors.fill: view3d
        camera: camera
        scene: root.scene
        hoverEnabled: root.hoverEnabled
        cursorShape: root.scene && root.scene.hovered !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor

        onTapped: (x, y, button) => {
            if (root.pickEnabled)
                root.picked(root.pickAt(x, y), button)
        }
        onHoverMoved: (x, y) => {
            if (root.hoverEnabled && root.scene)
                root.scene.hovered = root.pickAt(x, y)
        }
        onExited: if (root.scene) root.scene.hovered = ""
    }

    // Layer switches
    Rectangle {
        visible: root.showToggles
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 10
        width: toggles.implicitWidth + 16
        height: toggles.implicitHeight + 8
        radius: 6
        color: QtmTheme.bgOverlay

        RowLayout {
            id: toggles
            anchors.centerIn: parent
            spacing: 4

            QtmSwitch { text: "Markers"; checked: root.showMarkers; onToggled: root.showMarkers = checked }
            QtmSwitch { text: "Bones"; checked: root.showBones; onToggled: root.showBones = checked }
            QtmSwitch { text: "Skeletons"; checked: root.showSkeletons; onToggled: root.showSkeletons = checked }
            QtmSwitch { text: "Bodies"; checked: root.showRigidBodies; onToggled: root.showRigidBodies = checked }
            QtmSwitch {
                text: "Labels"
                checked: root.labelMode === "all"
                onToggled: root.labelMode = checked ? "all" : "highlighted"
            }
            QtmButton { text: "Fit"; onClicked: controller.fit() }
        }
    }
}
