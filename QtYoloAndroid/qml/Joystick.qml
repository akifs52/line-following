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

    function setPositionFromGamepad(gx, gy) {
        // Set position from gamepad/gamecontroller (gx, gy range: -1.0 to 1.0)
        var dx = gx * maxOffset;
        var dy = gy * maxOffset;
        handle.x = centerX - handle.width * 0.5 + dx;
        handle.y = centerY - handle.height * 0.5 + dy;
        xValue = gx;
        yValue = gy;
        moved(xValue, yValue);
    }

    onWidthChanged: resetHandle()
    onHeightChanged: resetHandle()
    Component.onCompleted: {
        resetHandle()
        forceActiveFocus()
    }

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

    // Keyboard controls (WASD) - prevent text input
    Keys.enabled: true
    Keys.forwardTo: []
    Keys.priority: Keys.BeforeItem

    Keys.onPressed: function(event) {
        var dx = 0
        var dy = 0
        var keyActive = false

        if (event.key === Qt.Key_W || event.key === Qt.Key_Up) {
            dy = -maxOffset
            keyActive = true
        } else if (event.key === Qt.Key_S || event.key === Qt.Key_Down) {
            dy = maxOffset
            keyActive = true
        }

        if (event.key === Qt.Key_A || event.key === Qt.Key_Left) {
            dx = -maxOffset
            keyActive = true
        } else if (event.key === Qt.Key_D || event.key === Qt.Key_Right) {
            dx = maxOffset
            keyActive = true
        }

        if (keyActive) {
            root.active = true
            handle.x = centerX - handle.width * 0.5 + dx
            handle.y = centerY - handle.height * 0.5 + dy
            xValue = dx / maxOffset
            yValue = dy / maxOffset
            moved(xValue, yValue)
        }
        event.accepted = true
    }

    Keys.onReleased: function(event) {
        if (event.key === Qt.Key_W || event.key === Qt.Key_Up ||
            event.key === Qt.Key_S || event.key === Qt.Key_Down ||
            event.key === Qt.Key_A || event.key === Qt.Key_Left ||
            event.key === Qt.Key_D || event.key === Qt.Key_Right) {
            root.resetHandle()
            event.accepted = true
        }
    }

    MouseArea {
        anchors.fill: parent
        preventStealing: true
        hoverEnabled: true

        onPressed: {
            if (typeof haptics !== "undefined" && haptics) haptics.vibrateMedium();
            root.forceActiveFocus();
            root.active = true;
            root.updateFromPoint(mouse.x, mouse.y);
        }

        onPositionChanged: {
            if (pressed) {
                root.updateFromPoint(mouse.x, mouse.y);
            }
        }

        onReleased: {
            if (typeof haptics !== "undefined" && haptics) haptics.vibrateShort();
            root.active = false;
            root.resetHandle();
        }

        onCanceled: {
            if (typeof haptics !== "undefined" && haptics) haptics.vibrateShort();
            root.active = false;
            root.resetHandle();
        }
    }
}
