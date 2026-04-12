#pragma once

#include <QAbstractSocket>
#include <QDateTime>
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QUrl>
#include <QtWebSockets/QWebSocket>

class LiveFrameProvider;

class WebSocketClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString hostStatus READ hostStatus NOTIFY hostStatusChanged)
    Q_PROPERTY(QString cameraStatus READ cameraStatus NOTIFY cameraStatusChanged)
    Q_PROPERTY(int speed READ speed NOTIFY speedChanged)
    Q_PROPERTY(qulonglong frameRevision READ frameRevision NOTIFY frameRevisionChanged)
    Q_PROPERTY(int latency READ latency NOTIFY latencyChanged)
    Q_PROPERTY(int cpu READ cpu NOTIFY cpuChanged)
    Q_PROPERTY(QString device READ device NOTIFY deviceChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)

public:
    explicit WebSocketClient(LiveFrameProvider *frameProvider, QObject *parent = nullptr);

    bool connected() const;
    QString hostStatus() const;
    QString cameraStatus() const;
    int speed() const;
    qulonglong frameRevision() const;
    int latency() const;
    int cpu() const;
    QString device() const;
    QString lastError() const;

    Q_INVOKABLE void connectToEndpoint(const QString &host, int port, bool secure = false, const QString &path = "/ws");
    Q_INVOKABLE void connectToUrl(const QString &url);
    Q_INVOKABLE void disconnectFromServer();

    Q_INVOKABLE bool sendJoystick(double x, double y, int speed);
    Q_INVOKABLE bool sendSpeed(int value);
    Q_INVOKABLE bool sendAutonomous(bool enabled);
    Q_INVOKABLE bool sendConnect(const QString &hostIp, int hostPort, const QString &camIp, int camPort);
    Q_INVOKABLE bool sendStop();

signals:
    void connectedChanged();
    void hostStatusChanged();
    void cameraStatusChanged();
    void speedChanged();
    void frameRevisionChanged();
    void latencyChanged();
    void cpuChanged();
    void deviceChanged();
    void lastErrorChanged();
    void commandReceived(const QString &command);

private slots:
    void onConnected();
    void onDisconnected();
    void onErrorOccurred(QAbstractSocket::SocketError socketError);
    void onTextMessageReceived(const QString &message);
    void sendPing();

private:
    bool sendJson(const QJsonObject &payload);
    void setHostStatus(const QString &status);
    void setCameraStatus(const QString &status);
    void setSpeed(int speedValue);
    void setLatency(int value);
    void setCpu(int value);
    void setDevice(const QString &value);
    void setLastError(const QString &message);

    QWebSocket m_socket;
    LiveFrameProvider *m_frameProvider = nullptr;
    QTimer *m_pingTimer = nullptr;
    qint64 m_pingSentTime = 0;

    QString m_hostStatus = QStringLiteral("idle");
    QString m_cameraStatus = QStringLiteral("idle");
    int m_speed = 0;
    qulonglong m_frameRevision = 0;
    int m_latency = 12;
    int m_cpu = 12;
    QString m_device = QStringLiteral("CUDA:0");
    QString m_lastError;
};
