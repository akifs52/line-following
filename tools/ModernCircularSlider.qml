import QtQuick 2.15

Rectangle {
    id: root
    width: 192
    height: 192
    radius: width / 2
    color: "#19243d"

    property int minValue: 0
    property int maxValue: 255
    property int value: 0
    property color progressColor: "#3B82F6"

    property real startAngle: -135
    property real sweepAngle: 270
    property real angle: startAngle + (value / maxValue) * sweepAngle

    Behavior on angle {
        NumberAnimation {
            duration: 160
            easing.type: Easing.OutQuad
        }
    }

    onAngleChanged: {
        value = Math.round((angle - startAngle) / sweepAngle * maxValue)
        fg.requestPaint()
    }

    // Background arc
    Canvas {
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.beginPath()
            ctx.lineWidth = 10
            ctx.lineCap = "round"
            ctx.strokeStyle = "rgba(255,255,255,0.08)"
            ctx.arc(width/2, height/2, 90,
                    startAngle * Math.PI/180,
                    (startAngle + sweepAngle) * Math.PI/180)
            ctx.stroke()
        }
    }

    // Active arc (NO GLOW)
    Canvas {
        id: fg
        anchors.fill: parent
        renderTarget: Canvas.FramebufferObject
        renderStrategy: Canvas.Cooperative

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()

            var cx = width / 2
            var cy = height / 2
            var r  = 90

            // ---- MAIN ARC ONLY ----
            ctx.beginPath()
            ctx.lineWidth = 10
            ctx.strokeStyle = progressColor
            ctx.lineCap = "round"
            ctx.arc(cx, cy, r,
                    startAngle * Math.PI/180,
                    angle * Math.PI/180)
            ctx.stroke()
        }
    }

    // --- HANDLE GLOW (OPTIMIZED) ---
    Rectangle {
        width: 24
        height: 24
        radius: 12
        opacity: 0.4
        color: "#3B82F6"

        property real rad: angle * Math.PI / 180

        x: root.width/2 + Math.cos(rad) * 90 - width/2
        y: root.height/2 + Math.sin(rad) * 90 - height/2
    }

    // --- HANDLE ---
    Rectangle {
        id: handle
        width: 18
        height: 18
        radius: 9
        color: "#4F8DF9"

        property real rad: angle * Math.PI / 180

        x: root.width/2 + Math.cos(rad) * 90 - width/2
        y: root.height/2 + Math.sin(rad) * 90 - height/2
    }

    // Mouse control
    MouseArea {
        anchors.fill: parent
        onPressed: update(mouse.x, mouse.y)
        onPositionChanged: if (pressed) update(mouse.x, mouse.y)

        function update(mx, my) {
            var dx = mx - root.width/2
            var dy = my - root.height/2
            var deg = Math.atan2(dy, dx) * 180 / Math.PI
            if (deg < startAngle) deg = startAngle
            if (deg > startAngle + sweepAngle) deg = startAngle + sweepAngle
            root.angle = deg
        }
    }

    // Center value
    Text {
        anchors.centerIn: parent
        text: value
        color: "#E5E7EB"
        font.pixelSize: 52
        font.weight: Font.DemiBold
    }
}
