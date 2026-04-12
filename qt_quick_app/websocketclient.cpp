#include "websocketclient.h"

#include "liveframeprovider.h"

#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>

WebSocketClient::WebSocketClient(LiveFrameProvider *frameProvider, QObject *parent)
    : QObject(parent), m_frameProvider(frameProvider)
{
    connect(&m_socket, &QWebSocket::connected, this, &WebSocketClient::onConnected);
    connect(&m_socket, &QWebSocket::disconnected, this, &WebSocketClient::onDisconnected);
    connect(&m_socket, &QWebSocket::textMessageReceived, this, &WebSocketClient::onTextMessageReceived);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(&m_socket, &QWebSocket::errorOccurred, this, &WebSocketClient::onErrorOccurred);
#else
    connect(&m_socket, QOverload<QAbstractSocket::SocketError>::of(&QWebSocket::error), this, &WebSocketClient::onErrorOccurred);
#endif

    m_pingTimer = new QTimer(this);
    m_pingTimer->setInterval(2000); // Ping every 2 seconds
    connect(m_pingTimer, &QTimer::timeout, this, &WebSocketClient::sendPing);
}

bool WebSocketClient::connected() const
{
    return m_socket.state() == QAbstractSocket::ConnectedState;
}

QString WebSocketClient::hostStatus() const
{
    return m_hostStatus;
}

QString WebSocketClient::cameraStatus() const
{
    return m_cameraStatus;
}

int WebSocketClient::speed() const
{
    return m_speed;
}

qulonglong WebSocketClient::frameRevision() const
{
    return m_frameRevision;
}

int WebSocketClient::latency() const
{
    return m_latency;
}

int WebSocketClient::cpu() const
{
    return m_cpu;
}

QString WebSocketClient::device() const
{
    return m_device;
}

QString WebSocketClient::lastError() const
{
    return m_lastError;
}

void WebSocketClient::connectToEndpoint(const QString &host, int port, bool secure, const QString &path)
{
    const QString trimmedHost = host.trimmed();
    if (trimmedHost.isEmpty() || port <= 0) {
        setLastError(QStringLiteral("Invalid host/port"));
        return;
    }

    QUrl url;
    url.setScheme(secure ? QStringLiteral("wss") : QStringLiteral("ws"));
    url.setHost(trimmedHost);
    url.setPort(port);
    if (path.startsWith('/')) {
        url.setPath(path);
    } else {
        url.setPath(QStringLiteral("/") + path);
    }

    connectToUrl(url.toString());
}

void WebSocketClient::connectToUrl(const QString &url)
{
    const QUrl wsUrl(url.trimmed());
    if (!wsUrl.isValid() || wsUrl.scheme().isEmpty() || wsUrl.host().isEmpty()) {
        setLastError(QStringLiteral("Invalid WebSocket URL"));
        return;
    }

    if (m_socket.state() == QAbstractSocket::ConnectingState || m_socket.state() == QAbstractSocket::ConnectedState) {
        m_socket.abort();
    }

    setLastError(QString());
    setHostStatus(QStringLiteral("idle"));
    setCameraStatus(QStringLiteral("idle"));
    m_socket.open(wsUrl);
    emit connectedChanged();
}

void WebSocketClient::disconnectFromServer()
{
    m_socket.close();
}

bool WebSocketClient::sendJoystick(double x, double y, int speed)
{
    return sendJson(QJsonObject {
        {QStringLiteral("type"), QStringLiteral("joystick")},
        {QStringLiteral("x"), x},
        {QStringLiteral("y"), y},
        {QStringLiteral("speed"), speed}
    });
}

bool WebSocketClient::sendSpeed(int value)
{
    setSpeed(value);
    return sendJson(QJsonObject {
        {QStringLiteral("type"), QStringLiteral("speed")},
        {QStringLiteral("value"), value}
    });
}

bool WebSocketClient::sendAutonomous(bool enabled)
{
    return sendJson(QJsonObject {
        {QStringLiteral("type"), QStringLiteral("autonomous")},
        {QStringLiteral("enabled"), enabled}
    });
}

bool WebSocketClient::sendConnect(const QString &hostIp, int hostPort, const QString &camIp, int camPort)
{
    setHostStatus(QStringLiteral("starting"));
    setCameraStatus(QStringLiteral("starting"));

    return sendJson(QJsonObject {
        {QStringLiteral("type"), QStringLiteral("connect")},
        {QStringLiteral("host_ip"), hostIp.trimmed()},
        {QStringLiteral("host_port"), hostPort},
        {QStringLiteral("cam_ip"), camIp.trimmed()},
        {QStringLiteral("cam_port"), camPort}
    });
}

bool WebSocketClient::sendStop()
{
    return sendJson(QJsonObject {
        {QStringLiteral("type"), QStringLiteral("stop")}
    });
}

void WebSocketClient::onConnected()
{
    setLastError(QString());
    emit connectedChanged();
    m_pingTimer->start();
}

void WebSocketClient::onDisconnected()
{
    m_pingTimer->stop();
    setHostStatus(QStringLiteral("idle"));
    setCameraStatus(QStringLiteral("idle"));
    emit connectedChanged();
}

void WebSocketClient::onErrorOccurred(QAbstractSocket::SocketError socketError)
{
    Q_UNUSED(socketError);
    setLastError(m_socket.errorString());
    emit connectedChanged();
}

void WebSocketClient::onTextMessageReceived(const QString &message)
{
    QJsonParseError error {};
    const QJsonDocument doc = QJsonDocument::fromJson(message.toUtf8(), &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject()) {
        return;
    }

    const QJsonObject obj = doc.object();
    const QString type = obj.value(QStringLiteral("type")).toString();

    if (type == QStringLiteral("frame")) {
        const QString frameB64 = obj.value(QStringLiteral("frame")).toString();
        if (!frameB64.isEmpty() && m_frameProvider) {
            const QByteArray raw = QByteArray::fromBase64(frameB64.toUtf8());
            QImage frame;
            if (frame.loadFromData(raw)) {
                m_frameProvider->setFrame(frame);
                ++m_frameRevision;
                emit frameRevisionChanged();
            }
        }

        if (obj.contains(QStringLiteral("latency"))) {
            setLatency(obj.value(QStringLiteral("latency")).toInt(m_latency));
        }

        if (obj.contains(QStringLiteral("cpu"))) {
            setCpu(obj.value(QStringLiteral("cpu")).toInt(m_cpu));
        }

        if (obj.contains(QStringLiteral("device"))) {
            setDevice(obj.value(QStringLiteral("device")).toString(m_device));
        }
        return;
    }

    if (type == QStringLiteral("host_status")) {
        setHostStatus(obj.value(QStringLiteral("status")).toString(QStringLiteral("idle")));
        return;
    }

    if (type == QStringLiteral("camera_status")) {
        setCameraStatus(obj.value(QStringLiteral("status")).toString(QStringLiteral("idle")));
        return;
    }

    if (type == QStringLiteral("speed")) {
        if (obj.contains(QStringLiteral("value"))) {
            setSpeed(obj.value(QStringLiteral("value")).toInt(m_speed));
        } else if (obj.contains(QStringLiteral("speed"))) {
            setSpeed(obj.value(QStringLiteral("speed")).toInt(m_speed));
        }
        return;
    }

    if (type == QStringLiteral("command")) {
        emit commandReceived(obj.value(QStringLiteral("value")).toString());
        return;
    }

    // Handle pong response for latency measurement
    if (type == QStringLiteral("pong")) {
        if (m_pingSentTime > 0) {
            qint64 roundTripMs = QDateTime::currentMSecsSinceEpoch() - m_pingSentTime;
            setLatency(static_cast<int>(roundTripMs));
            m_pingSentTime = 0;
        }
        return;
    }
}

bool WebSocketClient::sendJson(const QJsonObject &payload)
{
    if (!connected()) {
        setLastError(QStringLiteral("WebSocket not connected"));
        return false;
    }

    const QByteArray data = QJsonDocument(payload).toJson(QJsonDocument::Compact);
    m_socket.sendTextMessage(QString::fromUtf8(data));
    return true;
}

void WebSocketClient::setHostStatus(const QString &status)
{
    if (m_hostStatus == status) {
        return;
    }
    m_hostStatus = status;
    emit hostStatusChanged();
}

void WebSocketClient::setCameraStatus(const QString &status)
{
    if (m_cameraStatus == status) {
        return;
    }
    m_cameraStatus = status;
    emit cameraStatusChanged();
}

void WebSocketClient::setSpeed(int speedValue)
{
    if (m_speed == speedValue) {
        return;
    }
    m_speed = speedValue;
    emit speedChanged();
}

void WebSocketClient::setLatency(int value)
{
    if (m_latency == value) {
        return;
    }
    m_latency = value;
    emit latencyChanged();
}

void WebSocketClient::setCpu(int value)
{
    if (m_cpu == value) {
        return;
    }
    m_cpu = value;
    emit cpuChanged();
}

void WebSocketClient::setDevice(const QString &value)
{
    if (m_device == value) {
        return;
    }
    m_device = value;
    emit deviceChanged();
}

void WebSocketClient::setLastError(const QString &message)
{
    if (m_lastError == message) {
        return;
    }
    m_lastError = message;
    emit lastErrorChanged();
}

void WebSocketClient::sendPing()
{
    if (!connected()) {
        return;
    }
    m_pingSentTime = QDateTime::currentMSecsSinceEpoch();
    sendJson(QJsonObject {
        {QStringLiteral("type"), QStringLiteral("ping")},
        {QStringLiteral("timestamp"), m_pingSentTime}
    });
}
