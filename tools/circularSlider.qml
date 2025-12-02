import QtQuick
import QtQuick.Shapes

Item {
    id: root
    
    width: 150
    height: 150
    
    property int value: 0
    property color progressColor: "#4CAF50"
    property int minimumValue: 0
    property int maximumValue: 255
    
    
    
    onValueChanged: {
        if (value < minimumValue) value = minimumValue
        if (value > maximumValue) value = maximumValue
        canvas.requestPaint()
    }
    
    Rectangle {
        id: container
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(5/255, 10/255, 30/255, 1) }
            GradientStop { position: 1.0; color: Qt.rgba(40/255, 80/255, 160/255, 1) }
        }
        radius: 10
        
        Canvas {
            id: canvas
            anchors.fill: parent
            antialiasing: true
            
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                
                var centerX = width / 2
                var centerY = height / 2
                var radius = Math.min(width, height) / 2.5
                var startAngle = Math.PI / 2 // 90 derece
                var angle = (root.value / (maximumValue - minimumValue)) * 2 * Math.PI
                
                // Arkaplan dairesi (daha koyu bir renk)
                ctx.beginPath()
                ctx.lineWidth = 8
                ctx.strokeStyle = "rgba(30, 30, 50, 0.7)"
                ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI)
                ctx.stroke()
                
                // İlerleme yayı
                ctx.beginPath()
                ctx.lineWidth = 10
                ctx.strokeStyle = root.progressColor
                ctx.lineCap = "round"
                ctx.arc(centerX, centerY, radius, startAngle - angle, startAngle)
                ctx.stroke()
                
                // Knob (kaydırıcı düğmesi)
                var knobAngle = startAngle - angle
                var knobX = centerX + radius * Math.cos(knobAngle)
                var knobY = centerY + radius * Math.sin(knobAngle)
                
                ctx.beginPath()
                ctx.fillStyle = "white" // Beyaz renk daha iyi görünür
                ctx.arc(knobX, knobY, 8, 0, 2 * Math.PI)
                ctx.fill()
                
                // Knob kenarlık
                ctx.beginPath()
                ctx.lineWidth = 2
                ctx.strokeStyle = "rgba(0, 0, 0, 0.5)"
                ctx.arc(knobX, knobY, 8, 0, 2 * Math.PI)
                ctx.stroke()
            }
        }
        
        Text {
            anchors.centerIn: parent
            text: root.value
            color: "white"
            font.pointSize: 18
            font.bold: true
            
           
        }
    }
    
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        onPressed: handleMouse(mouse)
        onPositionChanged: handleMouse(mouse)
        
        function handleMouse(mouse) {
            var centerX = width / 2
            var centerY = height / 2
            var deltaX = mouse.x - centerX
            var deltaY = mouse.y - centerY
            
            // Açı hesaplama
            var angle = Math.atan2(deltaY, deltaX)
            
            // 0-360 derece aralığına çevirme
            var angleDeg = angle * 180 / Math.PI
            angleDeg = 90 - angleDeg
            if (angleDeg < 0) angleDeg += 360
            
            // Değeri hesaplama
            var range = maximumValue - minimumValue
            var newValue = Math.round(angleDeg / 360 * range)
            
            if (newValue !== root.value) {
                root.value = newValue
                root.valueChanged(newValue)
            }
        }
    }
}