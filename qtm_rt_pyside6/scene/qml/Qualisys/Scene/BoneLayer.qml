import QtQuick
import QtQuick3D
import Qualisys.Scene.Native

// QTM's bones between labeled markers, as thin capsules in the bones' QTM colors
Node {
    id: layer
    property QtObject scene: null
    property real thickness: 6          // mm
    property bool castsShadows: true

    Model {
        source: "#Cylinder"
        castsShadows: layer.castsShadows
        instancing: BoneInstancing {
            scene: layer.scene
            active: layer.visible
            part: "shaft"
            thickness: layer.thickness
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.5 }
    }

    Model {
        source: "#Sphere"
        castsShadows: layer.castsShadows
        instancing: BoneInstancing {
            scene: layer.scene
            active: layer.visible
            part: "caps"
            thickness: layer.thickness
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.5 }
    }
}
