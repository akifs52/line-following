import QtQuick 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property alias text: label.text
    property string icon: ""
    property string iconFont: ""
    property color baseColor: "#1e40af"
    property color hoverColor: "#1d4ed8"
    property color pressedColor: "#1e3a8a"
    property color borderColor: "#60a5fa"
    property color textColor: "#e2e8f0"
    property color disabledColor: "#334155"
    property color disabledBorderColor: "#64748b"
    property int radius: 10

    signal clicked()

    implicitWidth: 140
    implicitHeight: Qt.platform.os === "android" ? 36 : Math.min(40, Math.max(36, Screen.height * 0.045))

    readonly property bool hovered: hitArea.containsMouse
    readonly property bool pressed: hitArea.pressed

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: root.radius
        color: !root.enabled ? root.disabledColor
              : (root.pressed ? root.pressedColor : (root.hovered ? root.hoverColor : root.baseColor))
        border.width: 1
        border.color: !root.enabled ? root.disabledBorderColor : root.borderColor
        antialiasing: true

        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 6

        Text {
            visible: root.icon !== ""
            text: root.icon
            font.family: root.iconFont
            font.pixelSize: root.height * 0.4
            color: root.textColor
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            id: label
            color: root.textColor
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            wrapMode: Text.NoWrap
            maximumLineCount: 1

            // Auto-fit text to prevent overflow
            fontSizeMode: Text.Fit
            minimumPixelSize: 7
            font.pixelSize: 14

            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
        }
    }

    MouseArea {
        id: hitArea
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: !Qt.platform.os || Qt.platform.os !== "android"
        cursorShape: root.enabled && (!Qt.platform.os || Qt.platform.os !== "android") ? Qt.PointingHandCursor : Qt.ArrowCursor

        onPressed: {
            if (haptics && root.enabled) {
                haptics.vibrateShort() // Light feedback on press
            }
        }

        onClicked: {
            if (haptics && root.enabled) {
                haptics.vibrateMedium() // Medium feedback on click
            }
            root.clicked()
        }
    }
}
