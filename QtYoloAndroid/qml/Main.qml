import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtMultimedia
import Camera 1.0

ApplicationWindow {
    id: root

    FontLoader {
        id: materialIcons
        source: "qrc:/icons/MaterialIcons-Regular.ttf"
    }

    FontLoader {
        id: headlineFont
        source: "qrc:/icons/SpaceGrotesk-Bold.ttf"
    }

    visible: true
    visibility: Qt.platform.os === "android" ? Window.FullScreen : Window.Windowed
    width: Screen.width < 400 ? Screen.width : 430
    height: Screen.height < 800 ? Screen.height : 900
    minimumWidth: 340
    minimumHeight: 680
    title: "Line Following"

    color: "#0f172a"

    // Global WASD controls that work even when TextFields have focus
    Keys.priority: Keys.BeforeItem

    Keys.onPressed: function(event) {
        if (!autonomousBusy && joystick) {
            if (event.key === Qt.Key_W || event.key === Qt.Key_A ||
                event.key === Qt.Key_S || event.key === Qt.Key_D ||
                event.key === Qt.Key_Up || event.key === Qt.Key_Down ||
                event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
                joystick.Keys.onPressed(event)
                event.accepted = true
            }
        }
    }

    Keys.onReleased: function(event) {
        if (!autonomousBusy && joystick) {
            if (event.key === Qt.Key_W || event.key === Qt.Key_A ||
                event.key === Qt.Key_S || event.key === Qt.Key_D ||
                event.key === Qt.Key_Up || event.key === Qt.Key_Down ||
                event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
                joystick.Keys.onReleased(event)
                event.accepted = true
            }
        }
    }

    property var detectionBoxes: []
    property string uiErrorText: ""
    property bool pendingConnect: false
    readonly property bool autonomousBusy: controlClient.autonomousMode || controlClient.autonomousPending

    // Gamepad connections
    Connections {
        target: gamepad
        enabled: !root.autonomousBusy

        function onJoystickMoved(x, y) {
            // DPAD moves the virtual joystick
            if (joystick && !root.autonomousBusy) {
                joystick.setPositionFromGamepad(x, y)
            }
        }

        function onMotorSpeedChangeRequested(delta) {
            // L2/R2 change motor speed
            if (motorSpeed) {
                var newValue = motorSpeed.value + delta
                if (newValue < motorSpeed.from) newValue = motorSpeed.from
                if (newValue > motorSpeed.to) newValue = motorSpeed.to
                motorSpeed.value = newValue
            }
        }
    }

    function parsePort(value, fallbackValue) {
        const parsed = parseInt(value)
        if (isNaN(parsed) || parsed <= 0 || parsed > 65535)
            return fallbackValue
        return parsed
    }

    function resolvedStreamUrl() {
        const host = raspiIpField.text.trim()
        const port = parsePort(camPortField.text, 8554)
        if (host.length === 0)
            return ""
        return "tcp://" + host + ":" + port

    }

    function connectRaspberry() {
        const host = raspiIpField.text.trim()
        const controlPort = parsePort(hostPortField.text, 5005)
        if (host.length === 0) {
            uiErrorText = "Raspberry IP bos birakilamaz"
            return
        }

        uiErrorText = ""
        pendingConnect = true
        connectionDialog.open()
        yoloEngine.enabled = true
        controlClient.setAutonomousEnabled(false)
        controlClient.connectToHost(host, controlPort)

        const camPort = parsePort(camPortField.text, 8554)
        tcpCameraClient.connectToHost(host, camPort)
    }

    function disconnectRaspberry() {
        pendingConnect = false
        connectionDialog.close()
        controlClient.setAutonomousEnabled(false)
        controlClient.disconnectFromHost()
        tcpCameraClient.disconnectFromHost()
        yoloEngine.clearDetections()
        root.detectionBoxes = []
        overlay.boxes = []
        overlay.requestPaint()
    }

    function streamStatusText() {
        if (tcpCameraClient.lastError.length > 0)
            return "Yayin hatasi"
        if (tcpCameraClient.connected)
            return "Stream online"
        if (pendingConnect)
            return "Stream baglaniyor"
        return "Stream kapali"
    }

    function streamStatusColor() {
        if (tcpCameraClient.lastError.length > 0)
            return "#f87171"
        if (tcpCameraClient.connected)
            return "#4ade80"
        if (pendingConnect)
            return "#facc15"
        return "#94a3b8"
    }

    function popupStatusText(status) {
        if (status === "started")
            return "Baglandi"
        if (status === "failed")
            return "Baslamadi"
        if (status === "starting")
            return "Baglaniyor..."
        return "Bekleniyor..."
    }

    function popupStatusColor(status) {
        if (status === "started")
            return "#4ade80"
        if (status === "failed")
            return "#f87171"
        if (status === "starting")
            return "#facc15"
        return "#94a3b8"
    }

    function hostConnectionStatus() {
        if (controlClient.connected)
            return "started"
        if (controlClient.lastError.length > 0)
            return "failed"
        if (pendingConnect)
            return "starting"
        return "idle"
    }

    function cameraConnectionStatus() {
        if (tcpCameraClient.lastError.length > 0)
            return "failed"
        if (tcpCameraClient.connected)
            return "started"
        if (pendingConnect)
            return "starting"
        return "idle"
    }

    function connectionSummary() {
        const hostStatus = hostConnectionStatus()
        const cameraStatus = cameraConnectionStatus()
        if (pendingConnect)
            return "Host ve kamera baglaniyor..."
        if (hostStatus === "started" && cameraStatus === "started")
            return "Host ve kamera hazir"
        if (hostStatus === "failed" || cameraStatus === "failed")
            return "Baglanti tamamlanamadi"
        return "Baglanti durumu"
    }

    function connectionState() {
        const hostStatus = hostConnectionStatus()
        const cameraStatus = cameraConnectionStatus()
        if (pendingConnect)
            return "connecting"
        if (hostStatus === "started" && cameraStatus === "started")
            return "success"
        if (hostStatus === "started" || cameraStatus === "started")
            return "partial"
        if (hostStatus === "failed" || cameraStatus === "failed")
            return "failed"
        return "idle"
    }

    function connectButtonText() {
        if (connectionState() === "connecting")
            return "BAGLANIYOR..."
        if (connectionState() === "success")
            return "CONNECTED"
        if (connectionState() === "partial")
            return "PARTIAL"
        return "RASPBERRYE BAGLAN"
    }

    function connectButtonIcon() {
        return connectionState() === "success" || connectionState() === "partial"
               ? "\ue5cd"
               : "\ue037"
    }

    function connectButtonBackground() {
        if (connectionState() === "success")
            return "#193629"
        if (connectionState() === "partial" || connectionState() === "connecting")
            return "#3b3115"
        if (connectionState() === "failed")
            return "#3a1f2f"
        return "#2e64c8"
    }

    function connectButtonHoverColor() {
        if (connectionState() === "success")
            return "#1f4533"
        if (connectionState() === "partial" || connectionState() === "connecting")
            return "#4b3e1a"
        if (connectionState() === "failed")
            return "#4a263c"
        return "#3d79e6"
    }

    function connectButtonPressedColor() {
        if (connectionState() === "success" || connectionState() === "partial" || connectionState() === "connecting")
            return "#8f1f1f"
        if (connectionState() === "failed")
            return "#5b1f2f"
        return "#214b9b"
    }

    function connectButtonBorderColor() {
        if (connectionState() === "success")
            return "#4ade80"
        if (connectionState() === "partial" || connectionState() === "connecting")
            return "#facc15"
        if (connectionState() === "failed")
            return "#f87171"
        return "#9cc3ff"
    }

    function connectButtonTextColor() {
        if (connectionState() === "success")
            return "#bbf7d0"
        if (connectionState() === "partial" || connectionState() === "connecting")
            return "#fde68a"
        if (connectionState() === "failed")
            return "#fecaca"
        return "#f8fafc"
    }

    function handleConnectionButtonClick() {
        if (connectionState() === "success" || connectionState() === "partial" || connectionState() === "connecting") {
            disconnectRaspberry()
            return
        }
        connectRaspberry()
    }

    function refreshPendingConnect() {
        if (!pendingConnect)
            return

        const hostDone = hostConnectionStatus() !== "starting"
        const cameraDone = cameraConnectionStatus() !== "starting"
        if (hostDone && cameraDone)
            pendingConnect = false
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#111827" }
            GradientStop { position: 0.55; color: "#0b1323" }
            GradientStop { position: 1.0; color: "#09101e" }
        }
    }

    Connections {
        target: yoloEngine

        function onDetectionsReady(boxes) {
            root.detectionBoxes = boxes
            overlay.boxes = boxes
            overlay.requestPaint()
            controlClient.updateDetections(boxes)
        }
    }

    Connections {
        target: controlClient

        function onConnectedChanged() {
            if (controlClient.connected) {
                uiErrorText = ""
                controlClient.sendSpeed(motorSpeed.value)
            }
            root.refreshPendingConnect()
        }

        function onLastErrorChanged() {
            if (controlClient.lastError.length === 0)
                uiErrorText = ""
            root.refreshPendingConnect()
        }
    }

    Flickable {
        id: mainFlick
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: bottomBar.top
        clip: true
        contentWidth: width
        contentHeight: contentColumn.implicitHeight + 20

        ColumnLayout {
            id: contentColumn
            x: 12
            y: 10
            width: mainFlick.width - 24
            spacing: 12

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 68

                RowLayout {
                    anchors.fill: parent
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 46
                        radius: 16
                        color: "#132033"
                        border.color: "#2f4563"
                        border.width: 1

                        Image {
                            anchors.centerIn: parent
                            width: 32
                            height: 32
                            fillMode: Image.PreserveAspectFit
                            source: "qrc:/icons/luxury-car.png"
                        }
                    }

                    ColumnLayout {
                        spacing: 2

                        Text {
                            text: "Line Following"
                            color: "#f8fafc"
                            font.pixelSize: 27
                            font.bold: true
                            font.family: headlineFont.status === FontLoader.Ready
                                         ? headlineFont.name
                                         : "Sans Serif"
                        }

                        Text {
                            text: controlClient.autonomousPending
                                  ? "Algilama bekleniyor, ilk tespitte otonom baslar"
                                  : yoloEngine.modelStatus
                            color: controlClient.autonomousPending
                                   ? "#facc15"
                                   : (yoloEngine.modelLoaded ? "#4ade80" : "#f87171")
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }

                    Item { Layout.fillWidth: true }

                    ColumnLayout {
                        spacing: 2

                        Text {
                            text: "MODE"
                            color: "#64748b"
                            font.pixelSize: 10
                            font.bold: true
                            horizontalAlignment: Text.AlignRight
                        }

                        Text {
                            text: controlClient.autonomyStatus
                            color: root.autonomousBusy ? "#fca5a5" : "#93c5fd"
                            font.pixelSize: 18
                            font.bold: true
                            horizontalAlignment: Text.AlignRight
                        }

                        Text {
                            text: "FPS " + yoloEngine.fps.toFixed(1)
                            color: "#64748b"
                            font.pixelSize: 11
                            font.bold: true
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.round(contentColumn.width * 0.58)
                radius: 24
                color: "#05070d"
                border.color: "#1f2937"
                border.width: 2
                clip: true

                VideoItem {
                    id: liveVideo
                    objectName: "liveVideo"
                    anchors.fill: parent
                }

                Canvas {
                    id: overlay
                    anchors.fill: parent
                    antialiasing: true
                    property var boxes: []

                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        ctx.clearRect(0, 0, width, height)

                        const rect = liveVideo.contentRect || {x:0, y:0, width:liveVideo.width, height:liveVideo.height}
                        
                        // Draw detection boxes
                        for (let i = 0; i < boxes.length; ++i) {
                            const box = boxes[i]
                            const x = rect.x + box.x * rect.width
                            const y = rect.y + box.y * rect.height
                            const w = box.w * rect.width
                            const h = box.h * rect.height
                            const color = box.color ? box.color : "#4ade80"
                            const scorePercent = Math.round((box.score ? box.score : 0) * 100)

                            ctx.lineWidth = 3
                            ctx.strokeStyle = color
                            ctx.fillStyle = color
                            ctx.strokeRect(x, y, w, h)

                            const label = (box.label ? box.label : "line") + " " + scorePercent + "%"
                            const labelWidth = Math.max(90, label.length * 8)
                            const labelY = Math.max(rect.y, y - 24)

                            ctx.fillRect(x, labelY, labelWidth, 20)
                            ctx.fillStyle = "#0b1323"
                            ctx.font = "bold 12px sans-serif"
                            ctx.fillText(label, x + 6, labelY + 14)
                        }
                        
                        // Autonomous visualization (only when autonomous mode is active)
                        if (controlClient.autonomousMode && boxes.length > 0) {
                            const centerX = rect.x + controlClient.lineCenterX * rect.width
                            const centerY = rect.y + rect.height * 0.8 // 80% down from top
                            
                            // Draw center point (where robot thinks the line is)
                            ctx.beginPath()
                            ctx.arc(centerX, centerY, 8, 0, 2 * Math.PI)
                            ctx.fillStyle = "#facc15" // Yellow
                            ctx.fill()
                            ctx.lineWidth = 2
                            ctx.strokeStyle = "#ffffff"
                            ctx.stroke()
                            
                            // Draw crosshair
                            ctx.beginPath()
                            ctx.moveTo(centerX - 15, centerY)
                            ctx.lineTo(centerX + 15, centerY)
                            ctx.moveTo(centerX, centerY - 15)
                            ctx.lineTo(centerX, centerY + 15)
                            ctx.strokeStyle = "#facc15"
                            ctx.lineWidth = 2
                            ctx.stroke()
                            
                            // Draw PID steering indicator
                            const pidOut = controlClient.pidOutput
                            const maxLineLength = rect.width * 0.3
                            const lineLength = (pidOut / 100) * maxLineLength
                            
                            // Steering line (shows turn direction)
                            ctx.beginPath()
                            ctx.moveTo(centerX, centerY)
                            ctx.lineTo(centerX - lineLength, centerY + 60) // Diagonal line
                            ctx.strokeStyle = pidOut > 0 ? "#4ade80" : "#f87171" // Green for right, red for left
                            ctx.lineWidth = 4
                            ctx.stroke()
                            
                            // Draw motor speed bars
                            const barY = rect.y + rect.height - 30
                            const barWidth = 60
                            const barHeight = 8
                            const leftSpeed = controlClient.leftMotorSpeed
                            const rightSpeed = controlClient.rightMotorSpeed
                            
                            // Left motor bar
                            const leftBarColor = leftSpeed > 0 ? "#3b82f6" : "#ef4444"
                            ctx.fillStyle = leftBarColor
                            ctx.fillRect(rect.x + 10, barY, barWidth * Math.abs(leftSpeed) / 100, barHeight)
                            
                            // Right motor bar  
                            const rightBarColor = rightSpeed > 0 ? "#3b82f6" : "#ef4444"
                            ctx.fillStyle = rightBarColor
                            ctx.fillRect(rect.x + rect.width - 10 - barWidth * Math.abs(rightSpeed) / 100, barY, barWidth * Math.abs(rightSpeed) / 100, barHeight)
                            
                            // Motor labels
                            ctx.fillStyle = "#ffffff"
                            ctx.font = "bold 11px sans-serif"
                            ctx.fillText("L: " + Math.round(leftSpeed), rect.x + 10, barY - 5)
                            ctx.fillText("R: " + Math.round(rightSpeed), rect.x + rect.width - 50, barY - 5)
                            
                            // PID Error text
                            ctx.fillStyle = "#facc15"
                            ctx.font = "bold 14px sans-serif"
                            const errorText = "Err: " + controlClient.pidError.toFixed(2)
                            ctx.fillText(errorText, centerX - 30, rect.y + 20)
                        }
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.leftMargin: 14
                    anchors.top: parent.top
                    anchors.topMargin: 14
                    width: 64
                    height: 24
                    radius: 10
                    color: "#dc2626"

                    Text {
                        anchors.centerIn: parent
                        text: "REC"
                        color: "#f8fafc"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    anchors.top: parent.top
                    anchors.topMargin: 14
                    radius: 12
                    color: "#162033"
                    border.color: streamStatusColor()
                    border.width: 1
                    height: 28
                    width: statusTextItem.implicitWidth + 22

                    Text {
                        id: statusTextItem
                        anchors.centerIn: parent
                        text: streamStatusText()
                        color: streamStatusColor()
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 312
                    radius: 28
                    color: "#162033"
                    border.color: "#293548"
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        RowLayout {
                            spacing: 6

                            Text {
                                text: "\ue55d"
                                font.family: materialIcons.name
                                font.pixelSize: 16
                                color: "#94a3b8"
                            }

                            Text {
                                text: "Steering Control"
                                color: "#94a3b8"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 196

                            Joystick {
                                id: joystick
                                anchors.centerIn: parent
                                width: 156
                                height: 156
                                enabled: !root.autonomousBusy
                                opacity: root.autonomousBusy ? 0.45 : 1.0

                                onMoved: {
                                    if (!root.autonomousBusy) {
                                        controlClient.sendJoystick(x, y, motorSpeed.value)
                                    }
                                }

                                onReleased: {
                                    if (!root.autonomousBusy) {
                                        controlClient.sendStop()
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            ColumnLayout {
                                spacing: 2

                                Text {
                                    text: "Status"
                                    color: "#64748b"
                                    font.pixelSize: 10
                                    font.bold: true
                                }

                                Text {
                                    text: root.autonomousBusy ? "Locked" : (controlClient.connected ? "Active" : "Offline")
                                    color: root.autonomousBusy ? "#facc15" : (controlClient.connected ? "#22c55e" : "#f87171")
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                            }

                            Item { Layout.fillWidth: true }

                            ColumnLayout {
                                spacing: 2

                                Text {
                                    text: "Mode"
                                    color: "#64748b"
                                    font.pixelSize: 10
                                    font.bold: true
                                }

                                Text {
                                    text: controlClient.autonomousPending
                                          ? "Armed"
                                          : (controlClient.autonomousMode ? "Auto" : "Manual")
                                    color: controlClient.autonomousPending
                                           ? "#facc15"
                                           : (controlClient.autonomousMode ? "#f87171" : "#60a5fa")
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 312
                    radius: 28
                    color: "#162033"
                    border.color: "#293548"
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        RowLayout {
                            spacing: 6

                            Text {
                                text: "\ue531"
                                font.family: materialIcons.name
                                font.pixelSize: 16
                                color: "#94a3b8"
                            }

                            Text {
                                text: "Velocity"
                                color: "#94a3b8"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            MotorSpeedController {
                                id: motorSpeed
                                anchors.centerIn: parent
                                width: 176
                                height: 176
                                value: 180

                                onUserValueChanged: controlClient.sendSpeed(value)
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 230
                radius: 28
                color: "#162033"
                border.color: "#293548"
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true

                        RowLayout {
                            spacing: 6

                            Text {
                                text: "\ue0c1"
                                font.family: materialIcons.name
                                font.pixelSize: 16
                                color: "#94a3b8"
                            }

                            Text {
                                text: "Raspberry Connection"
                                color: "#94a3b8"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: controlClient.connected ? "TCP ONLINE" : "TCP OFFLINE"
                            color: controlClient.connected ? "#4ade80" : "#f87171"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }

                    RowLayout {
                        spacing: 6

                        Text {
                            text: "\ue0c8"
                            font.family: materialIcons.name
                            font.pixelSize: 14
                            color: "#64748b"
                        }

                        Text {
                            text: "Raspberry Pi IP"
                            color: "#64748b"
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }

                    TextField {
                        id: raspiIpField
                        Layout.fillWidth: true
                        text: "192.168.1.20"
                        color: "#e2e8f0"
                        font.pixelSize: 12
                        leftPadding: 36
                        topPadding: 8
                        bottomPadding: 8
                        background: Rectangle {
                            radius: 10
                            color: "#0f172a"
                            border.color: "#334155"
                            border.width: 1

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: "\ue0c8"
                                font.family: materialIcons.name
                                font.pixelSize: 16
                                color: "#64748b"
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 36
                                anchors.verticalCenter: parent.verticalCenter
                                text: "10.209.46.181"
                                color: "#64748b"
                                font.pixelSize: 12
                                visible: raspiIpField.text.length === 0
                            }
                        }

                        // Block WASD keys - prevent typing in this field
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_W || event.key === Qt.Key_A ||
                                event.key === Qt.Key_S || event.key === Qt.Key_D ||
                                event.key === Qt.Key_Up || event.key === Qt.Key_Down ||
                                event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
                                event.accepted = true
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        TextField {
                            id: hostPortField
                            Layout.fillWidth: true
                            Layout.maximumWidth: parent.width * 0.5 - 2
                            text: "5005"
                            color: "#e2e8f0"
                            font.pixelSize: 12
                            leftPadding: 36
                            topPadding: 8
                            bottomPadding: 8
                            inputMethodHints: Qt.ImhDigitsOnly
                            background: Rectangle {
                                radius: 10
                                color: "#0f172a"
                                border.color: "#334155"
                                border.width: 1

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "\ue8be"
                                    font.family: materialIcons.name
                                    font.pixelSize: 16
                                    color: "#64748b"
                                }

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 36
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Control Port"
                                    color: "#64748b"
                                    font.pixelSize: 12
                                    visible: hostPortField.text.length === 0
                                }
                            }

                            // Block WASD keys - prevent typing in this field
                            Keys.onPressed: function(event) {
                                if (event.key === Qt.Key_W || event.key === Qt.Key_A ||
                                    event.key === Qt.Key_S || event.key === Qt.Key_D ||
                                    event.key === Qt.Key_Up || event.key === Qt.Key_Down ||
                                    event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
                                    event.accepted = true
                                }
                            }
                            validator: IntValidator { bottom: 1; top: 65535 }
                        }

                        TextField {
                            id: camPortField
                            Layout.fillWidth: true
                            Layout.maximumWidth: parent.width * 0.5 - 2
                            text: "8554"
                            color: "#e2e8f0"
                            font.pixelSize: 12
                            leftPadding: 36
                            topPadding: 8
                            bottomPadding: 8
                            inputMethodHints: Qt.ImhDigitsOnly
                            background: Rectangle {
                                radius: 10
                                color: "#0f172a"
                                border.color: "#334155"
                                border.width: 1

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "\ue04b"
                                    font.family: materialIcons.name
                                    font.pixelSize: 16
                                    color: "#64748b"
                                }

                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 36
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Camera Port"
                                    color: "#64748b"
                                    font.pixelSize: 12
                                    visible: camPortField.text.length === 0
                                }
                            }

                            // Block WASD keys - prevent typing in this field
                            Keys.onPressed: function(event) {
                                if (event.key === Qt.Key_W || event.key === Qt.Key_A ||
                                    event.key === Qt.Key_S || event.key === Qt.Key_D ||
                                    event.key === Qt.Key_Up || event.key === Qt.Key_Down ||
                                    event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
                                    event.accepted = true
                                }
                            }
                            validator: IntValidator { bottom: 1; top: 65535 }
                        }
                    }

                    Text {
                        id: connectionErrorLabel
                        Layout.fillWidth: true
                        text: root.uiErrorText.length > 0
                              ? root.uiErrorText
                              : (controlClient.lastError.length > 0 ? controlClient.lastError : tcpCameraClient.lastError)
                        color: "#f87171"
                        font.pixelSize: 11
                        wrapMode: Text.WrapAnywhere
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        ModernButton {
                            Layout.fillWidth: true
                            text: root.connectButtonText()
                            icon: root.connectButtonIcon()
                            iconFont: materialIcons.name
                            baseColor: root.connectButtonBackground()
                            hoverColor: root.connectButtonHoverColor()
                            pressedColor: root.connectButtonPressedColor()
                            borderColor: root.connectButtonBorderColor()
                            textColor: root.connectButtonTextColor()
                            onClicked: root.handleConnectionButtonClick()
                        }

                        ModernButton {
                            visible: controlClient.connected
                            Layout.preferredWidth: 31
                            text: ""
                            icon: "\ue8ac"
                            iconFont: materialIcons.name
                            baseColor: "#3b1d1d"
                            hoverColor: "#4a2525"
                            pressedColor: "#7f1d1d"
                            borderColor: "#9f3a3a"
                            onClicked: {
                                controlClient.sendShutdown()
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: bottomBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 100
        color: "#0f172a"
        border.color: "#293548"
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 10

            ModernButton {
                Layout.fillWidth: true
                Layout.preferredHeight: Qt.platform.os === "android" ? 48 : 54
                text: root.autonomousBusy ? "OTONOM SURUSU DURDUR" : "OTONOM SURUSU BASLAT"
                icon: root.autonomousBusy ? "\ue047" : "\ue869"
                iconFont: materialIcons.name
                radius: 18
                baseColor: root.autonomousBusy ? "#be2c2c" : "#2e64c8"
                hoverColor: root.autonomousBusy ? "#d94242" : "#3d79e6"
                pressedColor: root.autonomousBusy ? "#8f1f1f" : "#214b9b"
                borderColor: root.autonomousBusy ? "#fca5a5" : "#9cc3ff"
                textColor: "#f8fafc"
                onClicked: {
                    if (root.autonomousBusy) {
                        controlClient.setAutonomousEnabled(false)
                    } else {
                        yoloEngine.enabled = true
                        controlClient.setAutonomousEnabled(true)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true

                Text {
                    text: "MODEL: " + (yoloEngine.modelLoaded ? "READY" : "WAIT")
                    color: "#64748b"
                    font.pixelSize: 11
                    font.family: "Consolas"
                }

                Text {
                    text: "CTRL: " + (controlClient.connected ? "ONLINE" : "OFFLINE")
                    color: "#64748b"
                    font.pixelSize: 11
                    font.family: "Consolas"
                }

                Text {
                    text: "AUTO: " + controlClient.guidanceMode
                    color: "#64748b"
                    font.pixelSize: 11
                    font.family: "Consolas"
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: "STREAM: " + streamStatusText()
                    color: "#64748b"
                    font.pixelSize: 11
                    font.family: "Consolas"
                }
            }
        }
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 4
        width: 120
        height: 4
        radius: 2
        color: "#334155"
        opacity: 0.7
    }

    Popup {
        id: connectionDialog
        width: Math.min(root.width - 26, 360)
        height: 260
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        x: (root.width - width) * 0.5
        y: (root.height - height) * 0.5

        background: Rectangle {
            radius: 18
            color: "#1e293b"
            border.color: "#334155"
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                BusyIndicator {
                    running: root.pendingConnect
                    visible: running
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                }

                ColumnLayout {
                    Text {
                        text: root.pendingConnect ? "Baglaniyor..." : "Baglanti Durumu"
                        color: "#f8fafc"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Text {
                        text: root.connectionSummary()
                        color: "#94a3b8"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    Layout.fillWidth: true
                    text: "Host: tcp://" + raspiIpField.text.trim() + ":" + root.parsePort(hostPortField.text, 5005)
                    color: "#64748b"
                    font.pixelSize: 11
                    wrapMode: Text.WrapAnywhere
                }

                Text {
                    Layout.fillWidth: true
                    text: "Kamera: " + root.resolvedStreamUrl()
                    color: "#64748b"
                    font.pixelSize: 11
                    wrapMode: Text.WrapAnywhere
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: "#334155"
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "\ue30e"
                    font.family: materialIcons.name
                    font.pixelSize: 16
                    color: root.popupStatusColor(root.hostConnectionStatus())
                }

                Text {
                    text: "Host Baglantisi"
                    color: "#94a3b8"
                    font.pixelSize: 12
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: root.popupStatusText(root.hostConnectionStatus())
                    color: root.popupStatusColor(root.hostConnectionStatus())
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "\ue04b"
                    font.family: materialIcons.name
                    font.pixelSize: 16
                    color: root.popupStatusColor(root.cameraConnectionStatus())
                }

                Text {
                    text: "Kamera Baglantisi"
                    color: "#94a3b8"
                    font.pixelSize: 12
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: root.popupStatusText(root.cameraConnectionStatus())
                    color: root.popupStatusColor(root.cameraConnectionStatus())
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            Item { Layout.fillHeight: true }

            ModernButton {
                Layout.fillWidth: true
                text: "OK"
                baseColor: "#1e40af"
                hoverColor: "#1d4ed8"
                pressedColor: "#1e3a8a"
                borderColor: "#60a5fa"
                textColor: "#e2e8f0"
                onClicked: connectionDialog.close()
            }
        }
    }
}
