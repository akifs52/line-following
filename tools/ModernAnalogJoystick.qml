import QtQuick 2.15
import Qt5Compat.GraphicalEffects

Rectangle {
    id: root
    width: 192
    height: 192
    color: "#19243d"
    
    // Prevent keyboard focus stealing
    focus: false
    Keys.enabled: false

    property real xValue: 0
    property real yValue: 0
    property bool isActive: false
    
    // WASD state properties
    property bool wPressed: false
    property bool aPressed: false
    property bool sPressed: false
    property bool dPressed: false

    signal positionChanged(real x, real y)
    signal released()
    
    // Update joystick position based on WASD keys
    onWPressedChanged: updateWASDPosition()
    onAPressedChanged: updateWASDPosition()
    onSPressedChanged: updateWASDPosition()
    onDPressedChanged: updateWASDPosition()
    
    function updateWASDPosition() {
        var maxDist = joystickContainer.width/2 - joystickHandle.width/2
        var dx = 0
        var dy = 0
        
        if (wPressed) dy = -maxDist
        if (sPressed) dy = maxDist
        if (aPressed) dx = -maxDist
        if (dPressed) dx = maxDist
        
        // Update handle position
        joystickHandle.anchors.centerIn = undefined
        joystickHandle.x = joystickContainer.width/2 - joystickHandle.width/2 + dx
        joystickHandle.y = joystickContainer.height/2 - joystickHandle.height/2 + dy
        
        // Update values
        root.xValue = dx / maxDist
        // Keep Y consistent with mouse: positive = up/forward
        root.yValue = -dy / maxDist
        root.positionChanged(root.xValue, root.yValue)
        
        // Update active state
        root.isActive = (wPressed || aPressed || sPressed || dPressed)
        
        if (!root.isActive) {
            root.positionChanged(0, 0)
            root.released()
        }
    }

    Rectangle {
        id: joystickContainer
        width: 192
        height: 192
        anchors.centerIn: parent
        radius: 96
        color: "#0B1624"
        border.color: Qt.rgba(1, 1, 1, 0.06)
        border.width: 1

        // Inner ring
        Rectangle {
            width: parent.width * 0.75
            height: parent.height * 0.75
            anchors.centerIn: parent
            radius: width / 2
            color: "transparent"
            border.color: Qt.rgba(1, 1, 1, 0.04)
            border.width: 1
        }

        // Vertical line
        Rectangle {
            width: 1
            height: parent.height
            anchors.centerIn: parent
            color: Qt.rgba(1, 1, 1, 0.04)
        }

        // Horizontal line
        Rectangle {
            width: parent.width
            height: 1
            anchors.centerIn: parent
            color: Qt.rgba(1, 1, 1, 0.04)
        }

        // Joystick handle
        Rectangle {
            id: joystickHandle
            width: 78
            height: 78
            radius: 39
            anchors.centerIn: parent
            color: "#4F8DF9"
            
            // REALISTIC GLOW (RADIAL)
            RadialGradient {
                anchors.centerIn: parent
                width: parent.width * 2.2
                height: parent.height * 2.2
                horizontalRadius: width / 2
                verticalRadius: height / 2
                
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(63/255,131/255,248/255,0.55) }
                    GradientStop { position: 0.3; color: Qt.rgba(63/255,131/255,248/255,0.35) }
                    GradientStop { position: 0.6; color: Qt.rgba(63/255,131/255,248/255,0.15) }
                    GradientStop { position: 1.0; color: Qt.rgba(63/255,131/255,248/255,0.0) }
                }
                
                // Glow sadece aktifken artsın
                opacity: root.isActive ? 1.0 : 0.7
                Behavior on opacity { NumberAnimation { duration: 150 } }
            }


            scale: mouseArea.containsMouse ? 1.05 : 1.0
            Behavior on scale {
                NumberAnimation { duration: 120 }
            }

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                hoverEnabled: true
                
                // Prevent keyboard focus stealing
                focus: false
                Keys.enabled: false

                onPressed: {
                    root.isActive = true
                    updatePosition(mouseX, mouseY)
                }

                onPositionChanged: if (pressed)
                    updatePosition(mouseX, mouseY)

                onReleased: {
                    root.isActive = false
                    joystickHandle.anchors.centerIn = joystickContainer
                    root.xValue = 0
                    root.yValue = 0
                    root.positionChanged(0, 0)
                    root.released()
                }

                function updatePosition(mx, my) {
                    var cx = joystickContainer.width / 2
                    var cy = joystickContainer.height / 2
                    var dx = mx - cx
                    var dy = my - cy

                    var dist = Math.sqrt(dx*dx + dy*dy)
                    var maxDist = joystickContainer.width/2 - joystickHandle.width/2

                    if (dist > maxDist) {
                        var a = Math.atan2(dy, dx)
                        dx = Math.cos(a) * maxDist
                        dy = Math.sin(a) * maxDist
                    }

                    joystickHandle.anchors.centerIn = undefined
                    joystickHandle.x = cx - joystickHandle.width/2 + dx
                    joystickHandle.y = cy - joystickHandle.height/2 + dy

                    root.xValue = dx / maxDist
                    root.yValue = -dy / maxDist
                    root.positionChanged(root.xValue, root.yValue)
                }
            }
        }
    }
}
