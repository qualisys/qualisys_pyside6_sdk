import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qualisys.Scene

ApplicationWindow {
    id: window
    width: 1280
    height: 760
    visible: true
    title: "QTM 3D Viewer"
    color: QtmTheme.bg
    palette: QtmTheme.palette  // the controls don't take the application palette
    font.family: QtmTheme.bodyFont
    font.pixelSize: QtmTheme.fontSize

    readonly property QtObject scene: backend.scene

    // Highlight what was clicked; clicking it again (or empty space) clears it
    function select(names) {
        var same = names.length > 0 && JSON.stringify(names) === JSON.stringify(scene.highlighted)
        scene.highlight(same ? [] : names)
    }

    header: ToolBar {
        background: Rectangle {
            color: QtmTheme.bgBar
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#000000" }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 8

            Label { text: "QTM host" }

            ComboBox {
                id: hostBox
                editable: true
                model: backend.hosts
                enabled: !backend.connected
                Layout.preferredWidth: 160
            }

            QtmButton {
                text: backend.discovering ? "Searching..." : "Find"
                enabled: !backend.connected && !backend.discovering
                onClicked: backend.discover()
            }

            QtmButton {
                text: backend.connected ? "Disconnect" : "Connect"
                primary: !backend.connected
                onClicked: backend.connected ? backend.disconnectFromQtm() : backend.connectTo(hostBox.editText)
            }

            ToolSeparator {}

            QtmSwitch {
                text: "Demo data"
                checked: backend.demo
                enabled: !backend.connected
                onToggled: backend.demo = checked
            }

            ToolSeparator {}

            Repeater {
                model: [
                    scene.fps + " fps",
                    "frame " + scene.frameNumber,
                    scene.markerCount + " markers",
                    scene.skeletonNames.length + " skeletons",
                    scene.bodyNames.length + " rigid bodies"
                ]
                delegate: Label {
                    required property string modelData
                    text: modelData
                    font.family: QtmTheme.monoFont
                    Layout.rightMargin: 10
                }
            }

            Item { Layout.fillWidth: true }
        }
    }

    footer: Rectangle {
        height: 26
        color: QtmTheme.bgBar

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10

            Label {
                text: backend.status
                color: QtmTheme.muted
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Label {
                text: "Left-drag: orbit  |  Right-drag: pan  |  Wheel: zoom  |  Click: highlight"
                color: QtmTheme.overline
            }
            Label {
                text: (view.cameraController.distance / 1000).toFixed(2) + " m"
                color: QtmTheme.overline
                font.family: QtmTheme.monoFont
                Layout.leftMargin: 12
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // =================================================================
        // Side panel: what QTM has defined, and how to draw it
        // =================================================================
        Rectangle {
            Layout.preferredWidth: 250
            Layout.fillHeight: true
            color: QtmTheme.bg

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 6

                QtmSection { text: "Scene" }

                ListView {
                    id: tree
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: backend.tree
                    ScrollBar.vertical: ScrollBar {}

                    delegate: ItemDelegate {
                        id: row
                        required property var modelData
                        readonly property bool header: modelData.kind === "header"
                        readonly property bool selected: !header
                            && JSON.stringify(modelData.names) === JSON.stringify(window.scene.highlighted)
                        width: tree.width
                        height: header ? 30 : 24
                        enabled: !header
                        leftPadding: 6 + modelData.indent * 14
                        onClicked: window.select(modelData.names)

                        background: Rectangle {
                            radius: QtmTheme.radius
                            color: row.selected ? QtmTheme.selectedRow : row.hovered ? QtmTheme.hoverRow : "transparent"
                        }

                        contentItem: RowLayout {
                            spacing: 6
                            Rectangle {
                                visible: !row.header
                                width: 8
                                height: 8
                                radius: row.modelData.kind === "group" ? 1 : 4
                                color: row.modelData.kind === "skeleton" ? QtmTheme.left
                                     : row.modelData.kind === "body" ? QtmTheme.axisColors[2]
                                     : QtmTheme.neutral
                            }
                            Text {
                                Layout.fillWidth: true
                                text: row.modelData.text
                                elide: Text.ElideRight
                                color: row.header ? QtmTheme.overline : row.selected ? QtmTheme.text : QtmTheme.muted
                                font.family: row.header ? QtmTheme.displayFont : QtmTheme.bodyFont
                                font.weight: row.header || row.modelData.kind === "group" ? Font.Bold : Font.Normal
                                font.pixelSize: row.header ? QtmTheme.smallFontSize : QtmTheme.fontSize
                            }
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: QtmTheme.line }

                QtmSection { text: "View" }

                GridLayout {
                    columns: 2
                    columnSpacing: 8
                    rowSpacing: 6
                    Layout.fillWidth: true

                    Label { text: "Bones" }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["keeled", "octahedral", "capsule", "stick"]
                        onActivated: (i) => view.boneStyle = model[i]
                    }

                    Label { text: "Local axes" }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["none", "selected", "all"]
                        onActivated: (i) => view.axesMode = model[i]
                    }

                    Label { text: "Labels" }
                    ComboBox {
                        Layout.fillWidth: true
                        model: ["highlighted", "all", "none"]
                        onActivated: (i) => view.labelMode = model[i]
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    QtmButton { text: "Fit"; Layout.fillWidth: true; onClicked: view.fit() }
                    QtmButton { text: "Top"; Layout.fillWidth: true; onClicked: view.cameraController.preset("top") }
                    QtmButton { text: "Reset"; Layout.fillWidth: true; onClicked: view.cameraController.reset() }
                }
            }
        }

        // =================================================================
        // 3D view
        // =================================================================
        QtmView {
            id: view
            Layout.fillWidth: true
            Layout.fillHeight: true
            scene: window.scene
            showToggles: true
            onPicked: (name) => window.select(name ? [name] : [])
        }
    }
}
