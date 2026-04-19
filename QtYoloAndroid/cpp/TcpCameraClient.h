#pragma once

#include <QObject>
#include <QTcpSocket>
#include <QImage>
#include <QTimer>
#include <QBuffer>
#include <QElapsedTimer>
#include "FrameRingBuffer.h"
#include "FrameWorker.h"

class VideoItem;

class TcpCameraClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString frameSource READ frameSource NOTIFY frameSourceChanged)
    Q_PROPERTY(bool connected READ isConnected NOTIFY connectionStateChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY errorOccurred)

public:
    explicit TcpCameraClient(QObject *parent = nullptr);
    ~TcpCameraClient();

    QString frameSource() const;
    bool isConnected() const;
    QString lastError() const;

public slots:
    void connectToHost(const QString &host, int port);
    void disconnectFromHost();
    void setVideoItem(VideoItem *item);

signals:
    void frameSourceChanged();
    void connectionStateChanged();
    void errorOccurred();
    void frameReady(const QImage &image); // Forward from FrameWorker to YoloEngine

private slots:
    void onFrameReady(const QImage &image); // Receives from FrameWorker, updates display

private slots:
    void onReadyRead();
    void onConnected();
    void onDisconnected();
    void onErrorOccurred(QAbstractSocket::SocketError socketError);
    void onReconnectTimeout();
    void onFrameUpdateTimer(); // Throttled UI update at 30 FPS

private:
    void extractJpegFrames();
    void updateFrameSource();
    bool isValidJpeg(const QByteArray &data);
    void scheduleFrameUpdate(); // Schedule UI update at throttled rate
    void updateDisplay(); // Update image provider with current frame

    QTcpSocket m_socket;
    QByteArray m_buffer;
    FrameRingBuffer m_ringBuffer;
    FrameWorker *m_frameWorker;
    QImage m_currentFrame;
    QImage m_pendingFrame; // Frame waiting to be displayed
    QString m_frameSource; // Kept for compatibility, now unused
    VideoItem *m_videoItem = nullptr;
    QString m_lastError;
    QString m_host;
    int m_port = 0;
    QTimer m_reconnectTimer;
    QTimer m_frameUpdateTimer; // Throttles UI updates to 30 FPS
    QElapsedTimer m_frameTimer;
    bool m_autoReconnect = true;
    bool m_frameUpdatePending = false;
    static constexpr int FRAME_UPDATE_INTERVAL_MS = 33; // ~30 FPS
};
