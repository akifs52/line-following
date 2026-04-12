import QtQuick 2.15

Item {
    id: root

    implicitWidth: 170
    implicitHeight: 170

    property int minValue: 0
    property int maxValue: 255
    property int value: 0
    property color progressColor: colorFromValue(value)
    property bool dragging: false

    function colorFromValue(v) {
        if (v <= 100) return "#ff5252"      // Red (low speed)
        if (v <= 200) return "#ffca28"      // Yellow (medium speed)
        return "#66bb6a"                   // Green (high speed)
    }

    signal userValueChanged(int value)

    readonly property real startAngle: -135
    readonly property real sweepAngle: 270
    readonly property real centerX: width * 0.5
    readonly property real centerY: height * 0.5
    readonly property real radius: Math.max(20, Math.min(width, height) * 0.5 - 12)
    readonly property real knobAngleDeg: angleFromValue(value)
    readonly property real knobAngleRad: knobAngleDeg * Math.PI / 180

    function clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    function ratioFromValue(v) {
        if (maxValue <= minValue) {
            return 0;
        }
        return (clamp(v, minValue, maxValue) - minValue) / (maxValue - minValue);
    }

    function angleFromValue(v) {
        return startAngle + ratioFromValue(v) * sweepAngle;
    }

    function valueFromAngle(deg) {
        var ratio = (deg - startAngle) / sweepAngle;
        ratio = clamp(ratio, 0, 1);
        return Math.round(minValue + ratio * (maxValue - minValue));
    }

    function setFromPointer(px, py, fromUser) {
        var dx = px - centerX;
        var dy = py - centerY;
        var deg = Math.atan2(dy, dx) * 180 / Math.PI;
        deg = clamp(deg, startAngle, startAngle + sweepAngle);

        var nextValue = valueFromAngle(deg);
        if (nextValue !== value) {
            value = nextValue;
            if (fromUser) {
                userValueChanged(value);
            }
        }
    }

    onValueChanged: {
        value = clamp(value, minValue, maxValue);
        arc.requestPaint();
    }

    onWidthChanged: arc.requestPaint()
    onHeightChanged: arc.requestPaint()

    Rectangle {
        anchors.fill: parent
        radius: width * 0.5
        color: "#19243d"
    }

    Canvas {
        id: arc
        anchors.fill: parent
        antialiasing: true

        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();

            var start = startAngle * Math.PI / 180;
            var end = (startAngle + sweepAngle) * Math.PI / 180;
            var active = knobAngleDeg * Math.PI / 180;
            var lineWidth = Math.max(7, Math.round(root.width * 0.055));

            ctx.lineCap = "round";
            ctx.lineWidth = lineWidth;

            ctx.beginPath();
            ctx.strokeStyle = "rgba(255,255,255,0.1)";
            ctx.arc(centerX, centerY, radius, start, end, false);
            ctx.stroke();

            ctx.beginPath();
            ctx.strokeStyle = progressColor;
            ctx.arc(centerX, centerY, radius, start, active, false);
            ctx.stroke();
        }
    }

    Rectangle {
        width: 22
        height: 22
        radius: width * 0.5
        color: colorFromValue(root.value)
        opacity: 0.2
        x: centerX + Math.cos(knobAngleRad) * root.radius - width * 0.5
        y: centerY + Math.sin(knobAngleRad) * root.radius - height * 0.5
    }

    Rectangle {
        width: 14
        height: 14
        radius: width * 0.5
        color: root.progressColor
        border.color: Qt.lighter(root.progressColor, 1.3)
        border.width: 1
        x: centerX + Math.cos(knobAngleRad) * root.radius - width * 0.5
        y: centerY + Math.sin(knobAngleRad) * root.radius - height * 0.5
    }

    Text {
        anchors.centerIn: parent
        text: root.value
        color: "#e2e8f0"
        font.pixelSize: 42
        font.bold: true
    }

    MouseArea {
        anchors.fill: parent
        preventStealing: true

        onPressed: {
            if (haptics) haptics.vibrateMedium();
            root.dragging = true;
            root.setFromPointer(mouse.x, mouse.y, true);
        }
        onPositionChanged: {
            if (pressed) {
                root.setFromPointer(mouse.x, mouse.y, true);
            }
        }
        onReleased: {
            if (haptics) haptics.vibrateShort();
            root.dragging = false;
        }
        onCanceled: {
            if (haptics) haptics.vibrateShort();
            root.dragging = false;
        }
    }
}
