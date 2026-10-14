import QtQuick
import QtQuick3D

// Orbit camera with QTM's mouse: left-drag orbits, right-drag (or middle) pans,
// the wheel zooms. Distances are in mm. Place it over the View3D.
//
// A click without dragging emits tapped(x, y, button); moving the mouse with no
// button down emits hoverMoved(x, y) - QtmView picks markers with them.
Item {
    id: ctl
    property Camera camera: null
    property QtObject scene: null       // for fit(): QtmScene.bounds()

    property vector3d target: Qt.vector3d(0, 900, 0)
    property real distance: 4500
    property real azimuth: 35           // degrees about scene +Y; 0 = camera on scene +Z
    property real elevation: 20         // degrees above the floor
    property real minDistance: 150
    property real maxDistance: 200000
    property real orbitSpeed: 0.4       // degrees per pixel
    property real zoomFactor: 1.12      // per wheel step
    property alias hoverEnabled: mouse.hoverEnabled
    property alias cursorShape: mouse.cursorShape
    readonly property bool dragging: mouse.dragging

    signal tapped(real x, real y, int button)
    signal hoverMoved(real x, real y)
    signal exited()

    // The view reset() and fit() fall back to
    property vector3d homeTarget: Qt.vector3d(0, 900, 0)
    property real homeDistance: 4500
    property real homeAzimuth: 35
    property real homeElevation: 20

    onTargetChanged: update()
    onDistanceChanged: update()
    onAzimuthChanged: update()
    onElevationChanged: update()
    onCameraChanged: update()
    Component.onCompleted: update()

    function update() {
        if (!camera)
            return
        var az = azimuth * Math.PI / 180
        var el = elevation * Math.PI / 180
        camera.position = Qt.vector3d(
            target.x + distance * Math.cos(el) * Math.sin(az),
            target.y + distance * Math.sin(el),
            target.z + distance * Math.cos(el) * Math.cos(az))
        camera.lookAt(target)
    }

    function setView(az, el) {
        azimuth = az
        elevation = Math.max(-89.9, Math.min(89.9, el))
    }

    function reset() {
        target = homeTarget
        distance = homeDistance
        setView(homeAzimuth, homeElevation)
    }

    // Aim at the tracked points' bounding sphere, keeping the viewing direction
    function fit() {
        var b = scene ? scene.bounds() : []
        if (b.length !== 4) {
            reset()
            return
        }
        var vfov = (camera && camera.fieldOfView ? camera.fieldOfView : 60) * Math.PI / 180
        var aspect = width > 0 && height > 0 ? width / height : 16 / 9
        var hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect)
        var radius = Math.max(b[3], 300)
        target = Qt.vector3d(b[0], b[1], b[2])
        distance = Math.max(minDistance, Math.min(maxDistance, radius * 1.15 / Math.sin(Math.min(vfov, hfov) / 2)))
    }

    // Look from a side: "default", "top", "front" (camera on QTM -Y), "back" (+Y),
    // "left" (-X), "right" (+X), or "+x", "-x", "+y", "-y" for the QTM axis the camera sits on.
    function preset(name) {
        if (name === "default") {
            setView(homeAzimuth, homeElevation)
            return
        }
        if (name === "top") {
            setView(azimuth, 89.9)
            return
        }
        var axes = { "front": [0, -1, 0], "back": [0, 1, 0], "left": [-1, 0, 0], "right": [1, 0, 0],
                     "+x": [1, 0, 0], "-x": [-1, 0, 0], "+y": [0, 1, 0], "-y": [0, -1, 0] }
        var a = axes[name]
        if (!a)
            return
        var d = scene ? scene.toScene(a[0], a[1], a[2]) : Qt.vector3d(a[0], a[2], -a[1])
        setView(Math.atan2(d.x, d.z) * 180 / Math.PI, 10)
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        hoverEnabled: true

        property point last
        property point pressPos
        property bool dragging: false

        onPressed: (event) => {
            last = Qt.point(event.x, event.y)
            pressPos = last
            dragging = false
        }

        onPositionChanged: (event) => {
            var dx = event.x - last.x
            var dy = event.y - last.y
            last = Qt.point(event.x, event.y)
            if (!(event.buttons & (Qt.LeftButton | Qt.RightButton | Qt.MiddleButton))) {
                ctl.hoverMoved(event.x, event.y)
                return
            }
            if (Math.abs(event.x - pressPos.x) + Math.abs(event.y - pressPos.y) >= 4)
                dragging = true
            if (event.buttons & Qt.LeftButton) {
                ctl.setView(ctl.azimuth - dx * ctl.orbitSpeed, ctl.elevation + dy * ctl.orbitSpeed)
            } else {
                // Pan in the view plane, so the floor point under the cursor follows it
                var vfov = (ctl.camera && ctl.camera.fieldOfView ? ctl.camera.fieldOfView : 60) * Math.PI / 180
                var speed = 2 * ctl.distance * Math.tan(vfov / 2) / Math.max(1, ctl.height)
                var az = ctl.azimuth * Math.PI / 180
                var el = ctl.elevation * Math.PI / 180
                var right = Qt.vector3d(Math.cos(az), 0, -Math.sin(az))
                var up = Qt.vector3d(-Math.sin(el) * Math.sin(az), Math.cos(el), -Math.sin(el) * Math.cos(az))
                ctl.target = ctl.target.minus(right.times(dx * speed)).plus(up.times(dy * speed))
            }
        }

        onReleased: (event) => {
            if (!dragging)
                ctl.tapped(event.x, event.y, event.button)
            dragging = false
        }

        onExited: ctl.exited()

        onWheel: (event) => {
            var steps = event.angleDelta.y / 120
            var d = ctl.distance * Math.pow(ctl.zoomFactor, -steps)
            ctl.distance = Math.max(ctl.minDistance, Math.min(ctl.maxDistance, d))
        }
    }
}
