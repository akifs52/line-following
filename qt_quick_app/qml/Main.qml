import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import Qt5Compat.GraphicalEffects

import QtCore 6.2

ApplicationWindow {
    id: window

    FontLoader {
        id: materialIcons
        source: "qrc:/icons/MaterialIcons-Regular.ttf"
    }

    visible: true
    visibility: Qt.platform.os === "android" ? Window.FullScreen : Window.Windowed
    width: Screen.width < 400 ? Screen.width : 430
    height: Screen.height < 800 ? Screen.height : 900
    minimumWidth: 320
    minimumHeight: 600
    title: "Autonomous Car UI"
    color: "#0f172a"

    // Window flags - Android uses default window, desktop uses standard flags
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint

    property bool autonomousMode: false
    property bool pendingWsConnect: false
    property bool pendingRaspiConnect: false

    property string wsIp: "192.168.1.10"
    property int wsPort: 8000

    property string pendingRaspiIp: ""
    property int pendingHostPort: 0
    property int pendingCamPort: 0

    property string clockText: "00:00"

    function parsePort(value, fallbackValue) {
        var n = parseInt(value);
        if (isNaN(n) || n <= 0 || n > 65535) {
            return fallbackValue;
        }
        return n;
    }

    function pad2(v) {
        return (v < 10 ? "0" : "") + v;
    }

    function refreshClock() {
        var now = new Date();
        clockText = pad2(now.getHours()) + ":" + pad2(now.getMinutes());
    }

    function resolvedRaspiIp() {
        var ip = raspiIpField.text.trim();
        if (ip.length > 0) {
            return ip;
        }
        return wsIp;
    }

    function websocketUrlText() {
        return "ws://" + wsIp + ":" + wsPort + "/ws";
    }

    function statusText(status) {
        if (status === "started") return "Basladi";
        if (status === "failed") return "Baslamadi";
        if (status === "starting") return "Baslatiliyor...";
        return "Bekleniyor...";
    }

    function statusColor(status) {
        if (status === "started") return "#4ade80";
        if (status === "failed") return "#f87171";
        if (status === "starting") return "#facc15";
        return "#94a3b8";
    }

    function connectionState() {
        if (!wsClient.connected) {
            return pendingWsConnect ? "ws_connecting" : "ws_offline";
        }
        if (pendingRaspiConnect || wsClient.hostStatus === "starting" || wsClient.cameraStatus === "starting") {
            return "connecting";
        }
        if (wsClient.hostStatus === "started" && wsClient.cameraStatus === "started") {
            return "success";
        }
        if ((wsClient.hostStatus === "started" && wsClient.cameraStatus === "failed")
                || (wsClient.hostStatus === "failed" && wsClient.cameraStatus === "started")) {
            return "partial";
        }
        if (wsClient.hostStatus === "failed" && wsClient.cameraStatus === "failed") {
            return "failed";
        }
        return "ws_ready";
    }

    function connectionSummary() {
        if (connectionState() === "ws_connecting") return "WebSocket baglaniyor...";
        if (connectionState() === "ws_offline") {
            if (wsClient.lastError.length > 0) return wsClient.lastError;
            return "WebSocket bagli degil";
        }
        if (connectionState() === "connecting") return "Host ve Kamera baglaniyor...";
        if (connectionState() === "success") return "Host ve Kamera basladi";
        if (connectionState() === "partial" && wsClient.hostStatus === "started") return "Sadece Host basladi";
        if (connectionState() === "partial" && wsClient.cameraStatus === "started") return "Sadece Kamera basladi";
        if (connectionState() === "failed") return "Host ve Kamera baslamadi";
        return "WebSocket bagli, RasPi baglantisi bekleniyor";
    }

    function connectButtonText() {
        if (connectionState() === "ws_connecting") return "WS CONNECTING...";
        if (connectionState() === "ws_offline") return "WS BAGLANMADI";
        if (connectionState() === "connecting") return "CONNECTING...";
        if (connectionState() === "success") return "CONNECTED";
        if (connectionState() === "partial") return "PARTIAL";
        if (connectionState() === "failed") return "FAILED";
        return "CONNECT RASPI";
    }

    function connectButtonForeground() {
        if (connectionState() === "ws_offline" || connectionState() === "failed") return "#fca5a5";
        if (connectionState() === "ws_connecting" || connectionState() === "connecting" || connectionState() === "partial") return "#fde68a";
        return "#bbf7d0";
    }

    function connectButtonBackground() {
        if (connectionState() === "ws_offline" || connectionState() === "failed") return "#3a1f2f";
        if (connectionState() === "ws_connecting" || connectionState() === "connecting" || connectionState() === "partial") return "#3b3115";
        return "#193629";
    }

    function connectButtonHoverBackground() {
        if (connectionState() === "ws_offline" || connectionState() === "failed") return "#4a263c";
        if (connectionState() === "ws_connecting" || connectionState() === "connecting" || connectionState() === "partial") return "#4b3e1a";
        return "#1f4533";
    }

    function connectButtonPressedBackground() {
        if (connectionState() === "ws_offline" || connectionState() === "failed") return "#2e1624";
        if (connectionState() === "ws_connecting" || connectionState() === "connecting" || connectionState() === "partial") return "#302710";
        return "#12291f";
    }

    function connectButtonBorderColor() {
        if (connectionState() === "ws_offline" || connectionState() === "failed") return "#f87171";
        if (connectionState() === "ws_connecting" || connectionState() === "connecting" || connectionState() === "partial") return "#facc15";
        return "#4ade80";
    }

    function startWsConnection() {
        var ip = wsIpField.text.trim();
        var port = parsePort(wsPortField.text, 8000);

        if (ip.length === 0) {
            wsErrorLabel.text = "IP bos birakilamaz";
            return;
        }

        wsIp = ip;
        wsPort = port;
        wsErrorLabel.text = "";

        pendingWsConnect = true;
        wsClient.connectToEndpoint(wsIp, wsPort, false, "/ws");
    }

    function beginRaspiConnection() {
        if (!wsClient.connected) {
            wsLoginPopup.open();
            return;
        }

        pendingRaspiIp = resolvedRaspiIp();
        pendingHostPort = parsePort(hostPortField.text, 8000);
        pendingCamPort = parsePort(camPortField.text, 8001);
        pendingRaspiConnect = true;

        connectionDialog.open();
        var ok = wsClient.sendConnect(pendingRaspiIp, pendingHostPort, pendingRaspiIp, pendingCamPort);
        if (!ok) {
            pendingRaspiConnect = false;
        }
    }

    function hostUrlText() {
        var hostIp = pendingRaspiIp.length > 0 ? pendingRaspiIp : resolvedRaspiIp();
        var hostPortValue = pendingHostPort > 0 ? pendingHostPort : parsePort(hostPortField.text, 8000);
        return "tcp://" + hostIp + ":" + hostPortValue;
    }

    function cameraUrlText() {
        var hostIp = pendingRaspiIp.length > 0 ? pendingRaspiIp : resolvedRaspiIp();
        var cameraPortValue = pendingCamPort > 0 ? pendingCamPort : parsePort(camPortField.text, 8001);
        return "tcp://" + hostIp + ":" + cameraPortValue;
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: refreshClock()
    }

    Component.onCompleted: {
        refreshClock();
        wsIpField.text = wsIp;
        wsPortField.text = wsPort.toString();
        if (Qt.platform.os === "android") {
            window.flags = window.flags | Qt.MaximizeUsingFullscreenGeometryHint;
        }
        wsLoginPopup.open();
    }

    Connections {
        target: wsClient

        function onConnectedChanged() {
            if (wsClient.connected) {
                pendingWsConnect = false;
                wsErrorLabel.text = "";
                wsLoginPopup.close();
                if (raspiIpField.text.trim().length === 0) {
                    raspiIpField.text = wsIp;
                }
                return;
            }
            pendingRaspiConnect = false;
            if (pendingWsConnect) {
                pendingWsConnect = false;
            }
        }

        function onHostStatusChanged() {
            if (wsClient.hostStatus !== "starting" && wsClient.cameraStatus !== "starting") {
                pendingRaspiConnect = false;
            }
        }

        function onCameraStatusChanged() {
            if (wsClient.hostStatus !== "starting" && wsClient.cameraStatus !== "starting") {
                pendingRaspiConnect = false;
            }
        }

        function onSpeedChanged() {
            if (!motorSpeed.dragging) {
                motorSpeed.value = wsClient.speed;
            }
        }

        function onLastErrorChanged() {
            if (wsClient.lastError.length > 0) {
                wsErrorLabel.text = wsClient.lastError;
                if (!wsClient.connected) {
                    wsLoginPopup.open();
                }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#111827" }
            GradientStop { position: 0.6; color: "#0b1323" }
            GradientStop { position: 1.0; color: "#09101e" }
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
            y: 8
            width: mainFlick.width - 24
            spacing: 12

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 58

                RowLayout {
                    anchors.fill: parent

                    ColumnLayout {
                        spacing: 2

                        Text {
                            text: "Otonom Car"
                            color: "#f8fafc"
                            font.pixelSize: 27
                            font.bold: true
                        }

                        Text {
                            text: wsClient.connected ? "System Ready: WS Online" : "System Ready: WS Offline"
                            color: wsClient.connected ? "#4ade80" : "#f87171"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 20
                        color: "#1e293b"
                        border.color: "#334155"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "S"
                            color: "#60a5fa"
                            font.pixelSize: 16
                            font.bold: true
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.round(contentColumn.width * 0.56)
                radius: 24
                color: "#05070d"
                border.color: "#1f2937"
                border.width: 2
                clip: true

                Image {
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectCrop
                    source: "image://live/frame?rev=" + wsClient.frameRevision
                    cache: false
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.leftMargin: 14
                    anchors.top: parent.top
                    anchors.topMargin: 14
                    width: 54
                    height: 22
                    radius: 8
                    color: "#dc2626"

                    Text {
                        anchors.centerIn: parent
                        text: "REC"
                        color: "white"
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
                    Layout.preferredHeight: 300
                    radius: 28
                    color: "#162033"
                    border.color: "#293548"
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        Text {
                            text: "Steering Control"
                            color: "#94a3b8"
                            font.pixelSize: 11
                            font.bold: true
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 188

                            Joystick {
                                anchors.centerIn: parent
                                width: 150
                                height: 150
                                enabled: !autonomousMode
                                opacity: autonomousMode ? 0.55 : 1.0

                                onMoved: {
                                    if (!autonomousMode && wsClient.connected) {
                                        wsClient.sendJoystick(x, y, motorSpeed.value);
                                    }
                                }

                                onReleased: {
                                    if (!autonomousMode && wsClient.connected) {
                                        wsClient.sendStop();
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
                                    text: autonomousMode ? "Inactive" : "Active"
                                    color: autonomousMode ? "#94a3b8" : "#22c55e"
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
                                    text: autonomousMode ? "Autonomous" : "Manual"
                                    color: autonomousMode ? "#f87171" : "#60a5fa"
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 300
                    radius: 28
                    color: "#162033"
                    border.color: "#293548"
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        Text {
                            text: "Velocity"
                            color: "#94a3b8"
                            font.pixelSize: 11
                            font.bold: true
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            MotorSpeedController {
                                id: motorSpeed
                                anchors.centerIn: parent
                                width: 168
                                height: 168

                                onUserValueChanged: {
                                    if (wsClient.connected) {
                                        wsClient.sendSpeed(value);
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 320
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

                        Text {
                            text: "Connection"
                            color: "#94a3b8"
                            font.pixelSize: 12
                            font.bold: true
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: wsClient.connected ? "WS ONLINE" : "WS OFFLINE"
                            color: wsClient.connected ? "#4ade80" : "#f87171"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }

                    Text {
                        text: "WebSocket Endpoint"
                        color: "#64748b"
                        font.pixelSize: 10
                        font.bold: true
                    }

                    Text {
                        Layout.fillWidth: true
                        text: websocketUrlText()
                        color: "#93c5fd"
                        font.pixelSize: 11
                        wrapMode: Text.WrapAnywhere
                    }

                    ModernButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Qt.platform.os === "android" ? 32 : 36
                        text: "WS AYARLARI"
                        icon: "\ue8b8"
                        iconFont: materialIcons.name
                        radius: 10
                        baseColor: "#1f3f8d"
                        hoverColor: "#2854b0"
                        pressedColor: "#18326e"
                        borderColor: "#6ea4ff"
                        textColor: "#eaf1ff"
                        onClicked: {
                            wsIpField.text = wsIp;
                            wsPortField.text = wsPort.toString();
                            wsLoginPopup.open();
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
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

                            // Icon
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: "\ue0c8"
                                font.family: materialIcons.name
                                font.pixelSize: 16
                                color: "#64748b"
                            }

                            // Custom placeholder (fixes Android alignment issue)
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 36
                                text: "192.168.1.20"
                                color: "#64748b"
                                font.pixelSize: 12
                                visible: raspiIpField.text.length === 0
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            text: "\ue8be"
                            font.family: materialIcons.name
                            font.pixelSize: 14
                            color: "#64748b"
                        }

                        Text {
                            text: "Host & Kamera Portları"
                            color: "#64748b"
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        TextField {
                            id: hostPortField
                            Layout.fillWidth: true
                            Layout.maximumWidth: parent.width * 0.5 - 2
                            implicitWidth: 120
                            text: "9000"
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

                                // Icon
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "\ue8be"
                                    font.family: materialIcons.name
                                    font.pixelSize: 16
                                    color: "#64748b"
                                }

                                // Custom placeholder (fixes Android alignment issue)
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 36
                                    text: "Host:9000"
                                    color: "#64748b"
                                    font.pixelSize: 12
                                    visible: hostPortField.text.length === 0
                                }
                            }
                        }

                        TextField {
                            id: camPortField
                            Layout.fillWidth: true
                            Layout.maximumWidth: parent.width * 0.5 - 2
                            implicitWidth: 120
                            text: "9001"
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

                                // Icon
                                Text {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "\ue04b"
                                    font.family: materialIcons.name
                                    font.pixelSize: 16
                                    color: "#64748b"
                                }

                                // Custom placeholder (fixes Android alignment issue)
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 36
                                    text: "Cam:9001"
                                    color: "#64748b"
                                    font.pixelSize: 12
                                    visible: camPortField.text.length === 0
                                }
                            }
                        }
                    }

                    ModernButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Qt.platform.os === "android" ? 38 : 42
                        enabled: wsClient.connected && connectionState() !== "connecting"
                        text: connectButtonText()
                        icon: connectionState() === "connected" ? "\ue5cd" : "\ue037"
                        iconFont: materialIcons.name
                        radius: 10
                        baseColor: connectButtonBackground()
                        hoverColor: connectButtonHoverBackground()
                        pressedColor: connectButtonPressedBackground()
                        borderColor: connectButtonBorderColor()
                        textColor: connectButtonForeground()
                        onClicked: beginRaspiConnection()
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
        height: 90
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
                text: autonomousMode ? "OTONOM SURUSU DURDUR" : "OTONOM SURUSU BASLAT"
                icon: autonomousMode ? "\ue047" : "\ue869"
                iconFont: materialIcons.name
                radius: 18
                baseColor: autonomousMode ? "#be2c2c" : "#2e64c8"
                hoverColor: autonomousMode ? "#d94242" : "#3d79e6"
                pressedColor: autonomousMode ? "#8f1f1f" : "#214b9b"
                borderColor: autonomousMode ? "#fca5a5" : "#9cc3ff"
                textColor: "#f8fafc"
                onClicked: {
                    autonomousMode = !autonomousMode;
                    if (wsClient.connected) {
                        wsClient.sendAutonomous(autonomousMode);
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true

                Text {
                    text: wsClient.device + " - 45C"
                    color: "#64748b"
                    font.pixelSize: 11
                    font.family: "Consolas"
                }

                Text {
                    text: "CPU: " + wsClient.cpu + "%"
                    color: "#64748b"
                    font.pixelSize: 11
                    font.family: "Consolas"
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: "LATENCY: " + wsClient.latency + "ms"
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
        id: wsLoginPopup
        width: Math.min(window.width - 30, 340)
        height: 260
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        x: (window.width - width) * 0.5
        y: (window.height - height) * 0.5

        background: Rectangle {
            radius: 18
            color: "#1e293b"
            border.color: "#334155"
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    text: "\ue63e"
                    font.family: materialIcons.name
                    font.pixelSize: 18
                    color: "#f8fafc"
                }

                Text {
                    text: "WebSocket Girişi"
                    color: "#f8fafc"
                    font.pixelSize: 16
                    font.bold: true
                }
            }

            Text {
                text: "Backend WS IP ve Port"
                color: "#94a3b8"
                font.pixelSize: 12
            }

            TextField {
                id: wsIpField
                Layout.fillWidth: true
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

                    // Icon
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: "\ue0c8"
                        font.family: materialIcons.name
                        font.pixelSize: 16
                        color: "#64748b"
                    }

                    // Custom placeholder (fixes Android alignment issue)
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 36
                        text: "192.168.1.10"
                        color: "#64748b"
                        font.pixelSize: 12
                        visible: wsIpField.text.length === 0
                    }
                }
            }

            TextField {
                id: wsPortField
                Layout.fillWidth: true
                inputMethodHints: Qt.ImhDigitsOnly
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

                    // Icon
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: "\ue8be"
                        font.family: materialIcons.name
                        font.pixelSize: 16
                        color: "#64748b"
                    }

                    // Custom placeholder (fixes Android alignment issue)
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 36
                        text: "8000"
                        color: "#64748b"
                        font.pixelSize: 12
                        visible: wsPortField.text.length === 0
                    }
                }
            }

            Text {
                id: wsErrorLabel
                Layout.fillWidth: true
                text: ""
                color: "#f87171"
                font.pixelSize: 11
                wrapMode: Text.WrapAnywhere
            }

            ModernButton {
                id: wsConnectBtn
                Layout.fillWidth: true
                Layout.preferredHeight: Qt.platform.os === "android" ? 36 : 40

                text: pendingWsConnect ? "BAĞLANIYOR..." : "WS BAĞLAN"
                icon: pendingWsConnect ? "" : "\ue157"
                iconFont: materialIcons.name

                baseColor: "#166534"
                hoverColor: "#16a34a"
                pressedColor: "#14532d"
                borderColor: "#22c55e"
                textColor: "#ecfdf5"

                enabled: !pendingWsConnect

                onClicked: startWsConnection()
            }

            ModernButton {
                id: wsOfflineBtn
                Layout.fillWidth: true
                Layout.preferredHeight: Qt.platform.os === "android" ? 32 : 36

                text: "KAPAT (OFFLINE)"
                icon: "\ue5cd"
                iconFont: materialIcons.name

                baseColor: "#334155"
                hoverColor: "#475569"
                pressedColor: "#1e293b"
                borderColor: "#64748b"
                textColor: "#e2e8f0"

                onClicked: wsLoginPopup.close()
            }
        }
    }

    Popup {
        id: connectionDialog
        width: Math.min(window.width - 26, 360)
        height: 260
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        x: (window.width - width) * 0.5
        y: (window.height - height) * 0.5

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

            // Title row with busy indicator
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                BusyIndicator {
                    running: pendingRaspiConnect
                    visible: running
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                }

                ColumnLayout {
                    Text {
                        text: pendingRaspiConnect ? "Başlatılıyor..." : "Bağlantı Durumu"
                        color: "#f8fafc"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Text {
                        text: connectionSummary()
                        color: "#94a3b8"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }

            // Connection URLs
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    Layout.fillWidth: true
                    text: "Host: " + hostUrlText()
                    color: "#64748b"
                    font.pixelSize: 11
                    wrapMode: Text.WrapAnywhere
                }

                Text {
                    Layout.fillWidth: true
                    text: "Kamera: " + cameraUrlText()
                    color: "#64748b"
                    font.pixelSize: 11
                    wrapMode: Text.WrapAnywhere
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#334155"
            }

            // Host status row
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "\ue30e"
                    font.family: materialIcons.name
                    font.pixelSize: 16
                    color: statusColor(wsClient.hostStatus)
                }

                Text {
                    text: "Host Bağlantısı"
                    color: "#94a3b8"
                    font.pixelSize: 12
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: statusText(wsClient.hostStatus)
                    color: statusColor(wsClient.hostStatus)
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            // Camera status row
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: "\ue04b"
                    font.family: materialIcons.name
                    font.pixelSize: 16
                    color: statusColor(wsClient.cameraStatus)
                }

                Text {
                    text: "Kamera Bağlantısı"
                    color: "#94a3b8"
                    font.pixelSize: 12
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: statusText(wsClient.cameraStatus)
                    color: statusColor(wsClient.cameraStatus)
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
