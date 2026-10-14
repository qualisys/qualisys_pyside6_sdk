import QtQuick
import QtQuick.Controls.Basic  // a non-native base, so the customisation works under any app style

// Flat 4 px button. `primary` carries the one red accent; checked toggles turn light gray.
Button {
    id: control
    property bool primary: false

    font.family: QtmTheme.displayFont
    font.weight: Font.DemiBold
    font.pixelSize: QtmTheme.smallFontSize
    leftPadding: 12
    rightPadding: 12

    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? QtmTheme.overline
             : control.checked && !control.primary ? QtmTheme.bgBar : QtmTheme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        implicitHeight: QtmTheme.controlHeight
        radius: QtmTheme.radius
        color: !control.enabled ? QtmTheme.disabledFill
             : control.primary ? (control.down ? QtmTheme.primaryPressed : control.hovered ? QtmTheme.primaryHover : QtmTheme.primary)
             : control.checked ? QtmTheme.neutral
             : control.down ? QtmTheme.lineStrong : control.hovered ? QtmTheme.hover : QtmTheme.line
        border.width: control.primary || control.checked ? 0 : 1
        border.color: QtmTheme.lineStrong
    }
}
