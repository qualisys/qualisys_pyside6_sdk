import QtQuick
import QtQuick3D

// Names of markers, joints and rigid bodies drawn over a View3D.
//
// mapFrom3DScene() uses the camera as of the last rendered frame, so the labels
// are re-projected once per frame (FrameAnimation) rather than on camera changes.
Item {
    id: overlay
    property View3D view: null
    property QtObject scene: null
    property string mode: "highlighted"     // "none" | "highlighted" (and hovered) | "all"
    property bool showMarkers: true         // in "all" mode
    property bool showJoints: false
    property bool showBodies: true
    property real lift: 30                  // mm above the point, in scene up (+Y)
    property color color: QtmTheme.labelText
    property color outlineColor: QtmTheme.labelOutline
    property string fontFamily: QtmTheme.bodyFont
    property int fontSize: QtmTheme.fontSize

    property int frame: 0
    FrameAnimation {
        running: overlay.visible && overlay.mode !== "none" && overlay.scene !== null
        onTriggered: overlay.frame++
    }

    function project(p) {
        overlay.frame  // dependency: re-evaluate every rendered frame
        if (!overlay.view || !overlay.view.camera)
            return Qt.vector3d(0, 0, -1)
        return overlay.view.mapFrom3DScene(Qt.vector3d(p.x, p.y + overlay.lift, p.z))
    }

    function shown(kind) {
        return kind === "marker" ? overlay.showMarkers
             : kind === "joint" ? overlay.showJoints
             : kind === "body" ? overlay.showBodies : false
    }

    Repeater {
        model: overlay.mode !== "none" && overlay.scene ? overlay.scene.pointModel : null

        delegate: Text {
            required property string name
            required property string kind
            required property vector3d position
            required property bool valid
            required property bool highlighted
            readonly property bool wanted: valid && (highlighted || (overlay.mode === "all" && overlay.shown(kind)))
            readonly property vector3d p: wanted ? overlay.project(position) : Qt.vector3d(0, 0, -1)

            visible: wanted && p.z > 0
            x: p.x - width / 2
            y: p.y - height
            text: name
            color: overlay.color
            font.bold: highlighted
            font.family: overlay.fontFamily
            font.pixelSize: overlay.fontSize
            style: Text.Outline
            styleColor: overlay.outlineColor
        }
    }

    // The hovered unlabeled marker (not in the point model)
    Text {
        readonly property string hovered: overlay.scene && overlay.mode !== "none" ? overlay.scene.hovered : ""
        readonly property var sp: {
            overlay.frame
            return hovered.indexOf("Unlabeled #") === 0 ? overlay.scene.scenePosition(hovered) : []
        }
        readonly property vector3d p: sp.length === 3 ? overlay.project(Qt.vector3d(sp[0], sp[1], sp[2])) : Qt.vector3d(0, 0, -1)
        visible: sp.length === 3 && p.z > 0
        x: p.x - width / 2
        y: p.y - height
        text: hovered
        color: QtmTheme.muted
        font.family: overlay.fontFamily
        font.pixelSize: overlay.fontSize
        style: Text.Outline
        styleColor: overlay.outlineColor
    }
}
