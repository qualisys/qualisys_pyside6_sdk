import QtQuick
import QtQuick3D
import Qualisys.Scene.Native

// Labeled markers in their QTM label colors and unlabeled markers in gray.
// Highlighted and hovered markers are drawn larger.
Node {
    id: layer
    property QtObject scene: null
    property bool showLabeled: true
    property bool showUnlabeled: true
    property real size: 24              // marker diameter, mm
    property real unlabeledSize: 18
    property real highlightScale: 1.5
    property color unlabeledColor: QtmTheme.unlabeled
    property bool castsShadows: true

    Model {
        visible: layer.showLabeled
        source: "#Sphere"
        castsShadows: layer.castsShadows
        instancing: MarkerInstancing {
            scene: layer.scene
            active: layer.visible && layer.showLabeled
            kind: "labeled"
            size: layer.size
            highlightScale: layer.highlightScale
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.3 }
    }

    Model {
        visible: layer.showUnlabeled
        source: "#Sphere"
        castsShadows: layer.castsShadows
        instancing: MarkerInstancing {
            scene: layer.scene
            active: layer.visible && layer.showUnlabeled
            kind: "unlabeled"
            size: layer.unlabeledSize
            color: layer.unlabeledColor
            highlightScale: layer.highlightScale
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.4 }
    }
}
