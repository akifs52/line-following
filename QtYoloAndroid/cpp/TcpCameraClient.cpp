#include "TcpCameraClient.h"
#include "VideoItem.h"

#include <QDebug>
#include <QStringList>

namespace {
constexpr int kRawHeaderSize = 20;
constexpr int kTelemetryHeaderSize = 8;
constexpr int kRawFormatBgra = 1;
constexpr quint32 kMaxTelemetryPayloadSize = 16u * 1024u;

quint32 readLe32(const char *data)
{
    return quint32(quint8(data[0]))
        | (quint32(quint8(data[1])) << 8)
        | (quint32(quint8(data[2])) << 16)
        | (quint32(quint8(data[3])) << 24);
}
} // namespace

TcpCameraClient::TcpCameraClient(QObject *parent)
    : QObject(parent)
    , m_ringBuffer(5) // Increased buffer for smoother playback
    , m_frameWorker(nullptr)
    , m_frameUpdatePending(false)
{
    connect(&m_socket, &QTcpSocket::connected, this, &TcpCameraClient::onConnected);
    connect(&m_socket, &QTcpSocket::disconnected, this, &TcpCameraClient::onDisconnected);
    connect(&m_socket, &QTcpSocket::readyRead, this, &TcpCameraClient::onReadyRead);
    connect(&m_socket, &QTcpSocket::errorOccurred, this, &TcpCameraClient::onErrorOccurred);

    m_reconnectTimer.setSingleShot(true);
    connect(&m_reconnectTimer, &QTimer::timeout, this, &TcpCameraClient::onReconnectTimeout);

    // Frame update timer - throttled to 30 FPS for smooth UI
    m_frameUpdateTimer.setSingleShot(true);
    connect(&m_frameUpdateTimer, &QTimer::timeout, this, &TcpCameraClient::onFrameUpdateTimer);
    m_frameTimer.start();
}

TcpCameraClient::~TcpCameraClient()
{
    disconnectFromHost();
    if (m_frameWorker) {
        m_frameWorker->stop();
        m_frameWorker->wait();
        delete m_frameWorker;
    }
}

QString TcpCameraClient::frameSource() const
{
    return m_frameSource;
}

bool TcpCameraClient::isConnected() const
{
    return m_socket.state() == QAbstractSocket::ConnectedState;
}

QString TcpCameraClient::lastError() const
{
    return m_lastError;
}

bool TcpCameraClient::simulationTelemetryValid() const
{
    return m_simulationTelemetryValid;
}

QString TcpCameraClient::simulationGuidanceMode() const
{
    return m_simulationGuidanceMode;
}

QString TcpCameraClient::simulationSource() const
{
    return m_simulationSource;
}

double TcpCameraClient::simulationWallDistance() const
{
    return m_simulationWallDistance;
}

double TcpCameraClient::simulationError() const
{
    return m_simulationError;
}

double TcpCameraClient::simulationTurnRatio() const
{
    return m_simulationTurnRatio;
}

double TcpCameraClient::simulationBaseSpeed() const
{
    return m_simulationBaseSpeed;
}

double TcpCameraClient::simulationLeftMotorSpeed() const
{
    return m_simulationLeftMotorSpeed;
}

double TcpCameraClient::simulationRightMotorSpeed() const
{
    return m_simulationRightMotorSpeed;
}

double TcpCameraClient::simulationLineCenterX() const
{
    return m_simulationLineCenterX;
}

double TcpCameraClient::simulationScore() const
{
    return m_simulationScore;
}

int TcpCameraClient::simulationClusters() const
{
    return m_simulationClusters;
}

void TcpCameraClient::connectToHost(const QString &host, int port)
{
    if (host.isEmpty() || port <= 0 || port > 65535) {
        m_lastError = QStringLiteral("Invalid host or port");
        emit errorOccurred();
        return;
    }

    m_host = host;
    m_port = port;
    m_buffer.clear();
    m_lastError.clear();
    resetSimulationTelemetry();

    if (m_socket.state() != QAbstractSocket::UnconnectedState) {
        m_socket.abort();
    }

    m_socket.connectToHost(host, static_cast<quint16>(port));
}

void TcpCameraClient::disconnectFromHost()
{
    m_autoReconnect = false;
    m_reconnectTimer.stop();

    // Stop frame worker
    if (m_frameWorker) {
        m_frameWorker->stop();
        m_frameWorker->wait();
        delete m_frameWorker;
        m_frameWorker = nullptr;
    }

    if (m_socket.state() != QAbstractSocket::UnconnectedState) {
        m_socket.disconnectFromHost();
        if (m_socket.state() != QAbstractSocket::UnconnectedState) {
            m_socket.abort();
        }
    }
    m_buffer.clear();
    m_ringBuffer.clear();
    resetSimulationTelemetry();
}

void TcpCameraClient::onReadyRead()
{
    m_buffer.append(m_socket.readAll());
    extractJpegFrames();
}

void TcpCameraClient::onConnected()
{
    qDebug() << "[TcpCameraClient] Connected to" << m_host << ":" << m_port;
    m_lastError.clear();
    m_buffer.clear();
    m_ringBuffer.clear();

    // Start frame worker thread
    m_frameWorker = new FrameWorker(&m_ringBuffer, this);
    connect(m_frameWorker, &FrameWorker::frameReady, this, &TcpCameraClient::onFrameReady);
    m_frameWorker->start();

    emit connectionStateChanged();
}

void TcpCameraClient::onDisconnected()
{
    qDebug() << "[TcpCameraClient] Disconnected from" << m_host << ":" << m_port;
    emit connectionStateChanged();

    if (m_autoReconnect && !m_host.isEmpty() && m_port > 0) {
        m_reconnectTimer.start(2000);
    }
}

void TcpCameraClient::onErrorOccurred(QAbstractSocket::SocketError socketError)
{
    Q_UNUSED(socketError);
    m_lastError = m_socket.errorString();
    qDebug() << "[TcpCameraClient] Error:" << m_lastError;
    emit errorOccurred();

    if (m_autoReconnect && !m_host.isEmpty() && m_port > 0) {
        m_reconnectTimer.start(3000);
    }
}

void TcpCameraClient::onReconnectTimeout()
{
    if (!m_host.isEmpty() && m_port > 0 && m_socket.state() == QAbstractSocket::UnconnectedState) {
        qDebug() << "[TcpCameraClient] Attempting to reconnect...";
        m_socket.connectToHost(m_host, static_cast<quint16>(m_port));
    }
}

void TcpCameraClient::extractJpegFrames()
{
    // Supports both:
    // - JPEG byte stream: SOI 0xFFD8 ... EOI 0xFFD9
    // - Webots raw stream: "WBFR" + le32(width,height,format,payloadSize) + BGRA bytes
    // - Webots telemetry: "WBTM" + le32(payloadSize) + UTF-8 key/value payload
    while (true) {
        const int rawStart = m_buffer.indexOf("WBFR");
        const int telemetryStart = m_buffer.indexOf("WBTM");
        const int soi = m_buffer.indexOf("\xFF\xD8");

        enum class PacketType { None, RawFrame, Telemetry, Jpeg };
        PacketType packetType = PacketType::None;
        int packetStart = -1;
        const auto considerPacket = [&](int start, PacketType type) {
            if (start >= 0 && (packetStart < 0 || start < packetStart)) {
                packetStart = start;
                packetType = type;
            }
        };

        considerPacket(rawStart, PacketType::RawFrame);
        considerPacket(telemetryStart, PacketType::Telemetry);
        considerPacket(soi, PacketType::Jpeg);

        if (packetStart == -1) {
            if (m_buffer.size() > 3) {
                m_buffer = m_buffer.right(3);
            }
            return;
        }

        if (packetStart > 0) {
            m_buffer.remove(0, packetStart);
        }

        if (packetType == PacketType::Telemetry) {
            if (m_buffer.size() < kTelemetryHeaderSize) {
                return;
            }

            const quint32 payloadSize = readLe32(m_buffer.constData() + 4);
            if (payloadSize > kMaxTelemetryPayloadSize) {
                m_buffer.remove(0, 1);
                continue;
            }

            if (m_buffer.size() < kTelemetryHeaderSize + int(payloadSize)) {
                return;
            }

            parseTelemetryPayload(m_buffer.mid(kTelemetryHeaderSize, int(payloadSize)));
            m_buffer.remove(0, kTelemetryHeaderSize + int(payloadSize));
            continue;
        }

        if (packetType == PacketType::RawFrame) {
            if (m_buffer.size() < kRawHeaderSize) {
                return;
            }

            const char *header = m_buffer.constData();
            const quint32 frameWidth = readLe32(header + 4);
            const quint32 frameHeight = readLe32(header + 8);
            const quint32 format = readLe32(header + 12);
            const quint32 payloadSize = readLe32(header + 16);
            const quint64 expectedPayload = quint64(frameWidth) * quint64(frameHeight) * 4u;

            const bool validHeader = frameWidth > 0
                && frameHeight > 0
                && frameWidth <= 4096
                && frameHeight <= 4096
                && format == kRawFormatBgra
                && payloadSize == expectedPayload
                && payloadSize <= 64u * 1024u * 1024u;

            if (!validHeader) {
                m_buffer.remove(0, 1);
                continue;
            }

            if (m_buffer.size() < kRawHeaderSize + int(payloadSize)) {
                return;
            }

            const uchar *pixels = reinterpret_cast<const uchar *>(m_buffer.constData() + kRawHeaderSize);
            QImage rawFrame(pixels, int(frameWidth), int(frameHeight), QImage::Format_ARGB32);
            if (!rawFrame.isNull()) {
                onFrameReady(rawFrame.copy());
            }

            m_buffer.remove(0, kRawHeaderSize + int(payloadSize));
            continue;
        }

        const int eoi = m_buffer.indexOf("\xFF\xD9", 2);
        if (eoi == -1) {
            return;
        }

        QByteArray jpegData = m_buffer.mid(0, eoi + 2);
        m_ringBuffer.push(jpegData);

        m_buffer.remove(0, eoi + 2);

        if (m_buffer.size() > 10 * 1024 * 1024) { // 10 MB limit
            qDebug() << "[TcpCameraClient] Buffer too large, clearing";
            m_buffer.clear();
            return;
        }
    }
}

void TcpCameraClient::parseTelemetryPayload(const QByteArray &payload)
{
    const QStringList fields = QString::fromUtf8(payload).split(QLatin1Char(';'), Qt::SkipEmptyParts);
    for (const QString &field : fields) {
        const int separator = field.indexOf(QLatin1Char('='));
        if (separator <= 0)
            continue;

        const QString key = field.left(separator);
        const QString value = field.mid(separator + 1);
        bool ok = false;

        if (key == QLatin1String("mode")) {
            m_simulationGuidanceMode = value;
        } else if (key == QLatin1String("source")) {
            m_simulationSource = value;
        } else if (key == QLatin1String("distance")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationWallDistance = parsed;
        } else if (key == QLatin1String("error")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationError = parsed;
        } else if (key == QLatin1String("turn")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationTurnRatio = parsed;
        } else if (key == QLatin1String("base")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationBaseSpeed = parsed;
        } else if (key == QLatin1String("left")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationLeftMotorSpeed = parsed;
        } else if (key == QLatin1String("right")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationRightMotorSpeed = parsed;
        } else if (key == QLatin1String("lineX")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationLineCenterX = parsed;
        } else if (key == QLatin1String("score")) {
            const double parsed = value.toDouble(&ok);
            if (ok)
                m_simulationScore = parsed;
        } else if (key == QLatin1String("clusters")) {
            const int parsed = value.toInt(&ok);
            if (ok)
                m_simulationClusters = parsed;
        }
    }

    m_simulationTelemetryValid = true;
    emit simulationTelemetryChanged();
}

void TcpCameraClient::resetSimulationTelemetry()
{
    if (!m_simulationTelemetryValid)
        return;

    m_simulationTelemetryValid = false;
    m_simulationGuidanceMode = QStringLiteral("STOP");
    m_simulationSource = QStringLiteral("none");
    m_simulationWallDistance = 0.0;
    m_simulationError = 0.0;
    m_simulationTurnRatio = 0.0;
    m_simulationBaseSpeed = 0.0;
    m_simulationLeftMotorSpeed = 0.0;
    m_simulationRightMotorSpeed = 0.0;
    m_simulationLineCenterX = -1.0;
    m_simulationScore = 0.0;
    m_simulationClusters = 0;
    emit simulationTelemetryChanged();
}

void TcpCameraClient::updateFrameSource()
{
    // Deprecated: base64 method causes flickering
    // Use updateDisplay() with ImageProvider instead
}

void TcpCameraClient::setVideoItem(VideoItem *item)
{
    m_videoItem = item;
}

void TcpCameraClient::updateDisplay()
{
    if (m_currentFrame.isNull()) {
        qDebug() << "[TcpCameraClient] updateDisplay: frame is null";
        return;
    }
    if (!m_videoItem) {
        qDebug() << "[TcpCameraClient] updateDisplay: videoItem is null";
        return;
    }

    // Thread-safe update: VideoItem paint must be called from GUI thread
    QImage frameCopy = m_currentFrame;
    QMetaObject::invokeMethod(m_videoItem, [this, frameCopy]() {
        m_videoItem->setFrame(frameCopy);
    }, Qt::QueuedConnection);
    
    // Still emit signal for bindings that may depend on frame updates
    emit frameSourceChanged();
}

void TcpCameraClient::onFrameReady(const QImage &image)
{
    if (!image.isNull()) {
        // Store frame and schedule throttled UI update
        m_pendingFrame = image;
        emit frameReady(image); // Forward to YoloEngine immediately
        scheduleFrameUpdate();
    }
}

void TcpCameraClient::scheduleFrameUpdate()
{
    if (m_frameUpdatePending) {
        return; // Already scheduled
    }

    // Check if we can update immediately or need to wait
    qint64 elapsed = m_frameTimer.elapsed();
    if (elapsed >= FRAME_UPDATE_INTERVAL_MS) {
        // Update immediately
        m_frameTimer.restart();
        onFrameUpdateTimer();
    } else {
        // Schedule update for remaining time
        m_frameUpdatePending = true;
        m_frameUpdateTimer.start(FRAME_UPDATE_INTERVAL_MS - static_cast<int>(elapsed));
    }
}

void TcpCameraClient::onFrameUpdateTimer()
{
    m_frameUpdatePending = false;
    m_frameTimer.restart();

    if (!m_pendingFrame.isNull()) {
        m_currentFrame = m_pendingFrame;
        updateDisplay(); // Use ImageProvider instead of base64
        m_pendingFrame = QImage(); // Clear pending frame
    }
}

bool TcpCameraClient::isValidJpeg(const QByteArray &data)
{
    return data.size() > 2 &&
           static_cast<unsigned char>(data[0]) == 0xFF &&
           static_cast<unsigned char>(data[1]) == 0xD8;
}
