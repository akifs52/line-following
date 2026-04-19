#include "TcpCameraClient.h"
#include "VideoItem.h"

#include <QDebug>

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
    // JPEG markers: SOI = 0xFFD8, EOI = 0xFFD9
    while (true) {
        // Find SOI (Start of Image)
        int soi = m_buffer.indexOf("\xFF\xD8");
        if (soi == -1) {
            // No SOI found, keep last byte in case it's 0xFF
            if (!m_buffer.isEmpty() && m_buffer.at(m_buffer.size() - 1) == '\xFF') {
                m_buffer = m_buffer.right(1);
            } else {
                m_buffer.clear();
            }
            return;
        }

        // Find EOI (End of Image)
        int eoi = m_buffer.indexOf("\xFF\xD9", soi + 2);
        if (eoi == -1) {
            // EOI not found yet, need more data
            if (soi > 0) {
                m_buffer.remove(0, soi);
            }
            return;
        }

        // Extract JPEG data and push to ring buffer (drops old frames automatically)
        QByteArray jpegData = m_buffer.mid(soi, eoi - soi + 2);
        m_ringBuffer.push(jpegData);

        // Remove processed data from buffer
        m_buffer.remove(0, eoi + 2);

        // Limit buffer size to prevent memory issues
        if (m_buffer.size() > 10 * 1024 * 1024) { // 10 MB limit
            qDebug() << "[TcpCameraClient] Buffer too large, clearing";
            m_buffer.clear();
            return;
        }
    }
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

    qDebug() << "[TcpCameraClient] updateDisplay: sending frame" << m_currentFrame.width() << "x" << m_currentFrame.height();

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
