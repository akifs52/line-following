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
    Q_PROPERTY(bool simulationTelemetryValid READ simulationTelemetryValid NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(QString simulationGuidanceMode READ simulationGuidanceMode NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(QString simulationSource READ simulationSource NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationWallDistance READ simulationWallDistance NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationError READ simulationError NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationTurnRatio READ simulationTurnRatio NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationBaseSpeed READ simulationBaseSpeed NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationLeftMotorSpeed READ simulationLeftMotorSpeed NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationRightMotorSpeed READ simulationRightMotorSpeed NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationLineCenterX READ simulationLineCenterX NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(double simulationScore READ simulationScore NOTIFY simulationTelemetryChanged)
    Q_PROPERTY(int simulationClusters READ simulationClusters NOTIFY simulationTelemetryChanged)

public:
    explicit TcpCameraClient(QObject *parent = nullptr);
    ~TcpCameraClient();

    QString frameSource() const;
    bool isConnected() const;
    QString lastError() const;
    bool simulationTelemetryValid() const;
    QString simulationGuidanceMode() const;
    QString simulationSource() const;
    double simulationWallDistance() const;
    double simulationError() const;
    double simulationTurnRatio() const;
    double simulationBaseSpeed() const;
    double simulationLeftMotorSpeed() const;
    double simulationRightMotorSpeed() const;
    double simulationLineCenterX() const;
    double simulationScore() const;
    int simulationClusters() const;

public slots:
    void connectToHost(const QString &host, int port);
    void disconnectFromHost();
    void setVideoItem(VideoItem *item);

signals:
    void frameSourceChanged();
    void connectionStateChanged();
    void errorOccurred();
    void frameReady(const QImage &image); // Forward from FrameWorker to YoloEngine
    void simulationTelemetryChanged();

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
    void parseTelemetryPayload(const QByteArray &payload);
    void resetSimulationTelemetry();
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
    bool m_simulationTelemetryValid = false;
    QString m_simulationGuidanceMode = QStringLiteral("STOP");
    QString m_simulationSource = QStringLiteral("none");
    double m_simulationWallDistance = 0.0;
    double m_simulationError = 0.0;
    double m_simulationTurnRatio = 0.0;
    double m_simulationBaseSpeed = 0.0;
    double m_simulationLeftMotorSpeed = 0.0;
    double m_simulationRightMotorSpeed = 0.0;
    double m_simulationLineCenterX = -1.0;
    double m_simulationScore = 0.0;
    int m_simulationClusters = 0;
    static constexpr int FRAME_UPDATE_INTERVAL_MS = 33; // ~30 FPS
};
