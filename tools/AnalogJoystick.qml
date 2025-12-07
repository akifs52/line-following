import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Item {
    id: root
    width: 200
    height: 200

    scale: 1.04
    
    // Hover effect properties
    property bool hovered: false
    
    
    // Hover effect animation
    Behavior on scale {
        NumberAnimation { duration: 200 }
    }
    
    states: [
        State {
            name: "hovered"
            when: hovered
            PropertyChanges { target: root; scale: 1.05 }
        }
    ]

    // Gradient background
    Rectangle {
        id: background
        anchors.fill: parent
        radius: Math.min(width, height) / 15
        clip: true
        
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "#1d318a" } // RGB(5, 10, 30)
            GradientStop { position: 1.0; color: "#2850a0" } // RGB(40, 80, 160)
        }
        
        // Thin border
        border.width: 1
        border.color: Qt.rgba(100/255, 120/255, 180/255, 0.6)
    }

    property real angle: 0
    property real distance: 0
    property bool active: false
    property real centerX: width / 2
    property real centerY: height / 2
    property real maxDistance: Math.min(width, height) * 0.4
    
    // Enable keyboard focus
    focus: true
    
    // Track keyboard state
    Keys.onPressed: {
        if (event.isAutoRepeat) {
            event.accepted = true
            return
        }
        
        switch(event.key) {
        case Qt.Key_W: wPressed = true; break
        case Qt.Key_A: aPressed = true; break
        case Qt.Key_S: sPressed = true; break
        case Qt.Key_D: dPressed = true; break
        default: return
        }
        updateKeyboardPosition()
        event.accepted = true
    }
    
    Keys.onReleased: {
        if (event.isAutoRepeat) {
            event.accepted = true
            return
        }
        
        switch(event.key) {
        case Qt.Key_W: wPressed = false; break
        case Qt.Key_A: aPressed = false; break
        case Qt.Key_S: sPressed = false; break
        case Qt.Key_D: dPressed = false; break
        default: return
        }
        updateKeyboardPosition()
        event.accepted = true
    }
    
    signal positionChanged(real x, real y)
    signal released()
    
    // Keyboard handling
    property bool wPressed: false
    property bool aPressed: false
    property bool sPressed: false
    property bool dPressed: false
    
    function updateKeyboardPosition() {
        var x = 0, y = 0
        
        if (wPressed) y -= 1
        if (sPressed) y += 1
        if (aPressed) x -= 1
        if (dPressed) x += 1
        
        // Normalize
        var length = Math.sqrt(x*x + y*y)
        if (length > 0) {
            x /= length
            y /= length
        }
        
        if (x !== 0 || y !== 0) {
            setJoystickPosition(x * maxDistance, y * maxDistance)
            root.active = true
            root.positionChanged(x, y)
        } else {
            resetPosition()
        }
    }
    
    function setJoystickPosition(deltaX, deltaY) {
        // Clamp to max distance
        var dist = Math.sqrt(deltaX * deltaX + deltaY * deltaY)
        if (dist > maxDistance) {
            deltaX = deltaX * maxDistance / dist
            deltaY = deltaY * maxDistance / dist
            dist = maxDistance
        }
        
        // Update inner circle position
        innerCircle.x = root.centerX + deltaX - innerCircle.width/2
        innerCircle.y = root.centerY + deltaY - innerCircle.height/2
        
        // Update properties
        root.distance = dist / maxDistance
        root.angle = Math.atan2(deltaY, deltaX)
    }
    
    function resetPosition() {
        root.active = false
        centerJoystick()
        root.positionChanged(0, 0)
        root.released()
    }
    
    function centerJoystick() {
        innerCircle.x = root.centerX - innerCircle.width/2
        innerCircle.y = root.centerY - innerCircle.height/2
        root.distance = 0
        root.angle = 0
    }
    
    onWidthChanged: {
        centerX = width / 2
        centerY = height / 2
        maxDistance = Math.min(width, height) * 0.4
        if (!root.active) {
            centerJoystick()
        }
    }
    
    onHeightChanged: {
        centerX = width / 2
        centerY = height / 2
        maxDistance = Math.min(width, height) * 0.4
        if (!root.active) {
            centerJoystick()
        }
    }
    
    Component.onCompleted: {
        centerJoystick()
    }
    
    // Outer circle with hover effect
    Rectangle {
        id: outerCircle
        width: Math.min(parent.width, parent.height) * 0.9
        height: width
        radius: width / 2
        color: "transparent"
        border.color: mouseArea.containsMouse ? "#4CAF50" : "#404040"
        border.width: 2
        anchors.centerIn: parent
        
        Behavior on border.color {
            ColorAnimation { duration: 200 }
        }
    }
    
    Rectangle {
        id: innerCircle
        width: outerCircle.width * 0.4
        height: width
        radius: width / 2
        color: root.active ? "#4CAF50" : "#2196F3"
        border.color: "#E0E0E0"
        border.width: 2
        
        // Position is managed by JavaScript functions
        x: root.centerX - width/2
        y: root.centerY - height/2
        
        Behavior on color {
            ColorAnimation { duration: 150 }
        }
        
        Behavior on x {
            enabled: !mouseArea.pressed && !root.active
            NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
        }
        
        Behavior on y {
            enabled: !mouseArea.pressed && !root.active
            NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
        }
    }
    
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true
        
        // Enable keyboard focus
        onActiveFocusChanged: {
            if (activeFocus) {
                forceActiveFocus()
            }
        }
        
        onEntered: root.hovered = true
        onExited: {
            root.hovered = false
            if (pressed) {
                // Calculate position at edge of circle
                var relX = mouseX - root.centerX
                var relY = mouseY - root.centerY
                var dist = Math.sqrt(relX * relX + relY * relY)
                
                if (dist > root.maxDistance) {
                    relX = relX * root.maxDistance / dist
                    relY = relY * root.maxDistance / dist
                    setJoystickPosition(relX, relY)
                    
                    // Normalized values
                    var normX = relX / root.maxDistance
                    var normY = relY / root.maxDistance
                    root.positionChanged(normX, normY)
                }
            }
        }
        
        onPressed: function(mouse) {
            root.active = true
            forceActiveFocus()
            updateJoystick(mouse.x, mouse.y)
        }
        
        onPositionChanged: function(mouse) {
            if (pressed) {
                updateJoystick(mouse.x, mouse.y)
            }
        }
        
        onReleased: {
            if (!wPressed && !aPressed && !sPressed && !dPressed) {
                resetPosition()
            } else {
                // Still have keyboard pressed, update keyboard position
                updateKeyboardPosition()
            }
        }
        
        function updateJoystick(x, y) {
            // Calculate position relative to center
            var relX = x - root.centerX
            var relY = y - root.centerY
            
            setJoystickPosition(relX, relY)
            
            // Normalized values (-1 to 1)
            var normX = relX / root.maxDistance
            var normY = relY / root.maxDistance
            
            // Emit position changed signal with normalized values
            root.positionChanged(normX, normY)
        }
    }
    
    // Center point indicator with crosshair
    Canvas {
        id: centerCross
        anchors.fill: parent
        opacity: 0.7
        
        onPaint: {
            var ctx = getContext("2d")
            var centerX = width / 2
            var centerY = height / 2
            var length = 10
            
            ctx.strokeStyle = "#FFFFFF"
            ctx.lineWidth = 1.5
            
            // Draw crosshair
            ctx.beginPath()
            // Horizontal line
            ctx.moveTo(centerX - length, centerY)
            ctx.lineTo(centerX + length, centerY)
            // Vertical line
            ctx.moveTo(centerX, centerY - length)
            ctx.lineTo(centerX, centerY + length)
            
            // Draw inner circle
            ctx.ellipse(centerX - 2, centerY - 2, 4, 4)
            
            ctx.stroke()
        }
    }
    
    // Debug text (optional)
    Text {
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        color: "white"
        font.pixelSize: 10
        text: root.active ? "Active" : "Inactive"
        opacity: 0.5
    }
}