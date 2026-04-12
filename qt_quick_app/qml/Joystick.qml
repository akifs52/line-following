import QtQuick 2.15
import Qt5Compat.GraphicalEffects

Item {
    id: root

    implicitWidth: 150
    implicitHeight: 150

    property real xValue: 0.0
    property real yValue: 0.0
    property bool active: false

    signal moved(real x, real y)
    signal released()

    readonly property real centerX: width * 0.5
    readonly property real centerY: height * 0.5
    readonly property real maxOffset: Math.max(1, width * 0.5 - handle.width * 0.5 - 6)

    function updateFromPoint(px, py) {
        var dx = px - centerX;
        var dy = py - centerY;
        var distance = Math.sqrt(dx * dx + dy * dy);

        if (distance > maxOffset) {
            var angle = Math.atan2(dy, dx);
            dx = Math.cos(angle) * maxOffset;
            dy = Math.sin(angle) * maxOffset;
        }

        handle.x = centerX - handle.width * 0.5 + dx;
        handle.y = centerY - handle.height * 0.5 + dy;
        xValue = dx / maxOffset;
        yValue = dy / maxOffset;
        moved(xValue, yValue);
    }

    function resetHandle() {
        handle.x = centerX - handle.width * 0.5;
        handle.y = centerY - handle.height * 0.5;
        xValue = 0.0;
        yValue = 0.0;
        moved(0.0, 0.0);
        released();
    }

    onWidthChanged: resetHandle()
    onHeightChanged: resetHandle()
    Component.onCompleted: resetHandle()

    Rectangle {
        anchors.fill: parent
        radius: width * 0.5
        color: "#0b1624"
        border.color: "#334155"
        border.width: 1
    }

    Rectangle {
        width: parent.width * 0.74
        height: width
        anchors.centerIn: parent
        radius: width * 0.5
        color: "transparent"
        border.color: "#1f2937"
        border.width: 1
    }

    Rectangle {
        width: 1
        height: parent.height
        anchors.centerIn: parent
        color: "#1f2937"
    }

    Rectangle {
        width: parent.width
        height: 1
        anchors.centerIn: parent
        color: "#1f2937"
    }

    Rectangle {
        id: handle
        width: 74
        height: 74
        radius: width * 0.5

        // Gradient for depth effect
        gradient: Gradient {
            GradientStop { position: 0; color: "#6ea8ff" }
            GradientStop { position: 1; color: "#3b82f6" }
        }

        border.color: "#60a5fa"
        border.width: 1
        z: 2

        // Realistic glow effect
        layer.enabled: true
        layer.effect: Glow {
            color: "#3b82f6"
            radius: root.active ? 22 : 10
            samples: 16
            spread: 0.2
            transparentBorder: true
        }

        Behavior on x {
            enabled: !root.active
            NumberAnimation {
                duration: 130
                easing.type: Easing.OutQuad
            }
        }

        Behavior on y {
            enabled: !root.active
            NumberAnimation {
                duration: 130
                easing.type: Easing.OutQuad
            }
        }

    }

    MouseArea {
        anchors.fill: parent
        preventStealing: true
        hoverEnabled: true

        onPressed: {
            if (haptics) haptics.vibrateMedium();
            root.active = true;
            root.updateFromPoint(mouse.x, mouse.y);
        }

        onPositionChanged: {
            if (pressed) {
                root.updateFromPoint(mouse.x, mouse.y);
            }
        }

        onReleased: {
            if (haptics) haptics.vibrateShort();
            root.active = false;
            root.resetHandle();
        }

        onCanceled: {
            if (haptics) haptics.vibrateShort();
            root.active = false;
            root.resetHandle();
        }
    }
}
