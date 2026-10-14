import QtQuick
import QtQuick.Controls.Basic  // a non-native base, so the customisation works under any app style

// Flat monochrome switch: light gray track when on (no colored accent)
Switch {
    id: control

    font.family: QtmTheme.bodyFont
    font.pixelSize: QtmTheme.fontSize

    indicator: Rectangle {
        implicitWidth: 30
        implicitHeight: 16
        x: control.leftPadding
        y: control.topPadding + (control.availableHeight - height) / 2
        radius: 8
        color: control.checked ? QtmTheme.neutral : QtmTheme.line
        border.color: control.checked ? QtmTheme.neutral : QtmTheme.lineStrong
        opacity: control.enabled ? 1 : 0.4

        Rectangle {
            width: 12
            height: 12
            radius: 6
            y: 2
            x: control.checked ? parent.width - width - 2 : 2
            color: control.checked ? QtmTheme.bgBar : QtmTheme.muted
            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
    }

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? QtmTheme.text : QtmTheme.overline
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + control.spacing
    }
}
