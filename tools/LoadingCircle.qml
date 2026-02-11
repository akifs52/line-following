import QtQuick 2.15

Rectangle {
    width: 48
    height: 48
    color: "#111827"
    radius: 24
  
    // Glow effect background (blur circle)
    Rectangle {
        width: 64
        height: 64
        anchors.centerIn: parent
        color: "#111827"
        radius: 32
        
        // Create glow effect using Rectangle with opacity
        Rectangle {
            width: parent.width
            height: parent.height
            anchors.centerIn: parent
            color: Qt.rgba(0.067, 0.09, 0.149, 0.1)
            radius: parent.radius
        }
    }
    
    // Main spinner with border-top effect
    Rectangle {
        id: mainSpinner
        width: parent.width
        height: parent.height
        anchors.centerIn: parent
        color: "#111827"
        border.width: 3
        border.color: Qt.rgba(0.231, 0.51, 0.965, 0.1)
        radius: parent.radius
        
        // Create border-top effect using Canvas
        Canvas {
            width: parent.width
            height: parent.height
            anchors.centerIn: parent
            antialiasing: false

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.clearRect(0, 0, width, height)
                ctx.translate(width / 2, height / 2)
                
                // Draw full background border (Electric Blue 10% opacity)
                ctx.beginPath()
                ctx.arc(0, 0, width / 2 - 1.5, 0, Math.PI * 2, false)
                ctx.strokeStyle = Qt.rgba(0.231, 0.51, 0.965, 0.1)
                ctx.lineWidth = 3
                ctx.lineCap = "butt"
                ctx.lineJoin = "miter"
                ctx.stroke()
                
                // Draw top segment (solid Electric Blue) - covers about 25% of the circle
                ctx.beginPath()
                ctx.arc(0, 0, width / 2 - 1.5, -Math.PI / 2, Math.PI / 2, false)
                ctx.strokeStyle = "#3B82F6"
                ctx.lineWidth = 3
                ctx.lineCap = "butt"
                ctx.lineJoin = "miter"
                ctx.stroke()
            }
        }
        
        // Rotation animation matching CSS 1s linear infinite
        NumberAnimation on rotation {
            from: 0
            to: 360
            duration: 1000
            loops: Animation.Infinite
            running: true
        }
    }
    
    // Center dot indicator - Electric Blue with 20% opacity
    Rectangle {
        width: 4
        height: 4
        anchors.centerIn: parent
        color: Qt.rgba(0.231, 0.51, 0.965, 0.1)
        radius: 2
    }
}
