import QtQuick 2.15

Rectangle {
    width: 48
    height: 48
    color: "transparent"
    radius: 24
    
    // Background circle (light gray) - static reference track
    Rectangle {
        width: parent.width
        height: parent.height
        anchors.centerIn: parent
        color: "transparent"
        border.width: 3
        border.color: Qt.rgba(0, 0, 0, 0.1)
        radius: parent.radius
    }
    
    // Rotating spinner with blue border-top effect
    Rectangle {
        id: mainSpinner
        width: parent.width
        height: parent.height
        anchors.centerIn: parent
        color: "transparent"
        radius: parent.radius
        
        // Create the border-top effect using Canvas
        Canvas {
            width: parent.width
            height: parent.height
            anchors.centerIn: parent
            antialiasing: true

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.clearRect(0, 0, width, height)
                ctx.translate(width / 2, height / 2)
                
                // Draw full background border (light gray)
                ctx.beginPath()
                ctx.arc(0, 0, width / 2 - 1.5, 0, Math.PI * 2, false)
                ctx.strokeStyle = Qt.rgba(0, 0, 0, 0.1)
                ctx.lineWidth = 3
                ctx.stroke()
                
                // Draw top segment (blue) - covers about 25% of the circle
                ctx.beginPath()
                ctx.arc(0, 0, width / 2 - 1.5, -Math.PI / 2, Math.PI / 2, false)
                ctx.strokeStyle = "#0078D4"
                ctx.lineWidth = 3
                ctx.lineCap = "round"
                ctx.stroke()
            }
        }
        
        // Rotation animation matching CSS cubic-bezier(0.53, 0.21, 0.29, 0.67)
        NumberAnimation on rotation {
            from: 0
            to: 360
            duration: 1000
            loops: Animation.Infinite
            running: true
        }
    }
    
    // Center dot indicator
    Rectangle {
        width: 4
        height: 4
        anchors.centerIn: parent
        color: "#0078D4"
        radius: 2
        opacity: 0.2
    }
}
