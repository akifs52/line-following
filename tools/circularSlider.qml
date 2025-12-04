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
    property bool hovered: false

    scale:1.05
    

    onValueChanged: {
        if (value < minimumValue) value = minimumValue
        if (value > maximumValue) value = maximumValue
        canvas.requestPaint()
    }
    
    // Hover efekti için koyulaşma layer'ı
    Rectangle {
        id: hoverLayer
        anchors.fill: parent
        color: hovered ? Qt.rgba(0, 0, 0, 0.2) : "transparent"
        radius: container.radius
        Behavior on color {
            ColorAnimation { duration: 200 }
        }
        z: 1
    }
    
    // Ana konteyner
    Rectangle {
        id: container
        anchors.fill: parent
        
        // Gradient arka plan
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "#1d318a" } // RGB(5, 10, 30)
            GradientStop { position: 1.0; color: "#2850a0" } // RGB(40, 80, 160)
        }
        
        // Köşe yuvarlatma - beyazlık olmaması için
        radius: Math.min(width, height) / 15
        clip: true // İçeriğin köşelerden taşmasını engelle
        
        // İnce kenarlık
        border.width: 1
        border.color: Qt.rgba(100/255, 120/255, 180/255, 0.6)
        
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
                
                // Arkaplan dairesi
                ctx.beginPath()
                ctx.lineWidth = 8
                ctx.strokeStyle = "rgba(30, 40, 60, 0.8)"
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
                
                // Knob gölgesi
                ctx.beginPath()
                ctx.fillStyle = "rgba(0, 0, 0, 0.4)"
                ctx.arc(knobX + 2, knobY + 2, 8, 0, 2 * Math.PI)
                ctx.fill()
                
                // Knob kendisi
                ctx.beginPath()
                ctx.fillStyle = "white"
                ctx.arc(knobX, knobY, 8, 0, 2 * Math.PI)
                ctx.fill()
                
                // Knob parlaklık efekti
                ctx.beginPath()
                ctx.fillStyle = "rgba(255, 255, 255, 0.3)"
                ctx.arc(knobX - 2, knobY - 2, 4, 0, 2 * Math.PI)
                ctx.fill()
            }
        }
        
        // Değer göstergesi
        Rectangle {
            id: valueDisplay
            width: 60
            height: 40
            anchors.centerIn: parent
            color: Qt.rgba(0, 0, 0, 0.3)
            radius: 8
            border.width: 1
            border.color: Qt.rgba(255/255, 255/255, 255/255, 0.2)
            
            Text {
                anchors.centerIn: parent
                text: root.value
                color: "white"
                font.pointSize: 16
                font.bold: true
                style: Text.Outline
                styleColor: Qt.rgba(0, 0, 0, 0.5)
            }
        }
    }
    
    // Mouse alanı
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        
        onEntered: root.hovered = true
        onExited: root.hovered = false
        
        onPressed: {
            root.hovered = true
            handleMouse(mouse)
        }
        
        onPositionChanged: {
            if (pressed) {
                handleMouse(mouse)
            }
        }
        
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
    
    // Hover efekti animasyonu
    Behavior on scale {
        NumberAnimation { duration: 200 }
    }
    
    states: [
        State {
            name: "hovered"
            when: hovered
            PropertyChanges { target: root; scale: 1.08 }
        }
    ]
}