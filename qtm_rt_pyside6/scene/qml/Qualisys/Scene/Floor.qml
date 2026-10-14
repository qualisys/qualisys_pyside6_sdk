import QtQuick
import QtQuick3D
import Qualisys.Scene.Native

// The floor (QTM's ground plane, scene y = 0) with a grid, centred on the origin
Node {
    id: floor
    property real size: 20000           // mm, edge length
    property real spacing: 500          // mm between grid lines
    property int majorEvery: 2          // every n-th line is a major line
    property bool showPlane: true
    property bool showGrid: true
    property color color: QtmTheme.floor
    property color gridColor: QtmTheme.grid
    property color majorColor: QtmTheme.gridMajor

    Model {
        visible: floor.showPlane
        source: "#Rectangle"
        y: -2
        eulerRotation.x: -90
        scale: Qt.vector3d(floor.size / 100, floor.size / 100, 1)
        castsShadows: false
        receivesShadows: true
        materials: PrincipledMaterial { baseColor: floor.color; roughness: 0.95 }
    }

    Model {
        visible: floor.showGrid
        geometry: GridGeometry { size: floor.size; spacing: floor.spacing; skipEvery: floor.majorEvery }
        castsShadows: false
        receivesShadows: false
        materials: PrincipledMaterial { baseColor: floor.gridColor; lighting: PrincipledMaterial.NoLighting }
    }

    Model {
        visible: floor.showGrid && floor.majorEvery > 0
        y: 0.5
        geometry: GridGeometry { size: floor.size; spacing: floor.spacing * Math.max(1, floor.majorEvery) }
        castsShadows: false
        receivesShadows: false
        materials: PrincipledMaterial { baseColor: floor.majorColor; lighting: PrincipledMaterial.NoLighting }
    }
}
