import QtQuick
import QtQuick3D
import Qualisys.Scene.Native

// Rigid bodies (6DOF): each body's local X / Y / Z axes and a sphere in its QTM color
Node {
    id: layer
    property QtObject scene: null
    property real axisLength: 120       // mm
    property real axisThickness: 6
    property real originSize: 22
    property bool showOrigin: true
    property var axisColors: QtmTheme.axisColors
    property bool castsShadows: true

    Model {
        source: "#Cylinder"
        castsShadows: layer.castsShadows
        instancing: RigidBodyInstancing {
            scene: layer.scene
            active: layer.visible
            part: "axes"
            axisLength: layer.axisLength
            axisThickness: layer.axisThickness
            axisColors: layer.axisColors
        }
        materials: PrincipledMaterial { baseColor: "white"; lighting: PrincipledMaterial.NoLighting }
    }

    Model {
        visible: layer.showOrigin
        source: "#Sphere"
        castsShadows: layer.castsShadows
        instancing: RigidBodyInstancing {
            scene: layer.scene
            active: layer.visible && layer.showOrigin
            part: "origin"
            originSize: layer.originSize
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.35 }
    }
}
