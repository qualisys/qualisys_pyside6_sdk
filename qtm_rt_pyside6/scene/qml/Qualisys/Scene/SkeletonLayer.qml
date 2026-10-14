import QtQuick
import QtQuick3D
import Qualisys.Scene.Native

// Solved skeletons. The default "keeled" bones are octahedral bones with three
// chamfered corners and one sharp ridge, drawn as a light stripe, that marks
// the segment's forward axis (local +Y; +Z for bones along Y, the toes), so
// each bone's twist is visible. Left bones are blue, right gold, centre gray.
Node {
    id: layer
    property QtObject scene: null
    property string boneStyle: "keeled"     // "keeled" | "octahedral" | "capsule" | "stick"
    property string axesMode: "none"        // local-axis tripods: "none" | "selected" | "all"
    property bool showJoints: true
    property real jointSize: 22             // mm
    property real stickWidth: 8             // mm, for boneStyle "stick"
    property real axisLength: 90            // mm
    property color leftColor: QtmTheme.left
    property color rightColor: QtmTheme.right
    property color centerColor: QtmTheme.center
    property color keelColor: QtmTheme.keel
    property color jointColor: QtmTheme.joint
    property var axisColors: QtmTheme.axisColors
    property bool castsShadows: true

    readonly property bool keelShaped: boneStyle === "keeled" || boneStyle === "octahedral"

    // Bone bodies: keeled / octahedral
    Model {
        id: keelBodies
        visible: layer.keelShaped
        castsShadows: layer.castsShadows
        geometry: KeelBoneGeometry { style: layer.boneStyle === "octahedral" ? "octahedral" : "keeled"; part: "body" }
        instancing: SkeletonInstancing {
            scene: layer.scene
            active: layer.visible && keelBodies.visible
            part: "bones"
            style: layer.boneStyle
            leftColor: layer.leftColor
            rightColor: layer.rightColor
            centerColor: layer.centerColor
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.45 }
    }

    // The ridge stripes: same transforms as the bodies, near-white
    Model {
        id: keelRidges
        visible: layer.boneStyle === "keeled"
        castsShadows: layer.castsShadows
        geometry: KeelBoneGeometry { style: "keeled"; part: "keel" }
        instancing: SkeletonInstancing {
            scene: layer.scene
            active: layer.visible && keelRidges.visible
            part: "keels"
            style: layer.boneStyle
            keelColor: layer.keelColor
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.35 }
    }

    // Bone bodies: capsule / stick
    Model {
        id: tubes
        visible: !layer.keelShaped
        castsShadows: layer.castsShadows
        source: "#Cylinder"
        instancing: SkeletonInstancing {
            scene: layer.scene
            active: layer.visible && tubes.visible
            part: "bones"
            style: layer.boneStyle
            stickWidth: layer.stickWidth
            leftColor: layer.leftColor
            rightColor: layer.rightColor
            centerColor: layer.centerColor
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.45 }
    }

    // Rounded ends for "capsule"
    Model {
        id: caps
        visible: layer.boneStyle === "capsule"
        castsShadows: layer.castsShadows
        source: "#Sphere"
        instancing: SkeletonInstancing {
            scene: layer.scene
            active: layer.visible && caps.visible
            part: "caps"
            style: layer.boneStyle
            leftColor: layer.leftColor
            rightColor: layer.rightColor
            centerColor: layer.centerColor
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.45 }
    }

    Model {
        id: joints
        visible: layer.showJoints
        castsShadows: layer.castsShadows
        source: "#Sphere"
        instancing: SkeletonInstancing {
            scene: layer.scene
            active: layer.visible && joints.visible
            part: "joints"
            jointSize: layer.jointSize
            jointColor: layer.jointColor
        }
        materials: PrincipledMaterial { baseColor: "white"; roughness: 0.3 }
    }

    // Local X / Y / Z of each segment
    Model {
        id: axes
        visible: layer.axesMode !== "none"
        castsShadows: false
        source: "#Cylinder"
        instancing: SkeletonInstancing {
            scene: layer.scene
            active: layer.visible && axes.visible
            part: "axes"
            axesMode: layer.axesMode
            axisLength: layer.axisLength
            axisColors: layer.axisColors
        }
        materials: PrincipledMaterial { baseColor: "white"; lighting: PrincipledMaterial.NoLighting }
    }
}
