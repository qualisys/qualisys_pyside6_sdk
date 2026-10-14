import QtQuick
import QtQuick3D
import Qualisys.Scene.Native

// QTM's global axes at the origin: X red, Y green, Z blue, following AxisUpwards
Node {
    id: layer
    property QtObject scene: null
    property real axisLength: 500       // mm
    property real axisThickness: 8
    property var axisColors: QtmTheme.axisColors

    Model {
        source: "#Cylinder"
        castsShadows: false
        instancing: AxesInstancing {
            scene: layer.scene
            active: layer.visible
            axisLength: layer.axisLength
            axisThickness: layer.axisThickness
            axisColors: layer.axisColors
        }
        materials: PrincipledMaterial { baseColor: "white"; lighting: PrincipledMaterial.NoLighting }
    }
}
