#pragma once

#include <QObject>
#include <QElapsedTimer>
#include <QTcpSocket>
#include <QTimer>
#include <QVariantList>
#include <QVector>
#include <QDebug>

class RaspiControlClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(int speed READ speed NOTIFY speedChanged)
    Q_PROPERTY(bool autonomousMode READ autonomousMode NOTIFY autonomousModeChanged)
    Q_PROPERTY(bool autonomousPending READ autonomousPending NOTIFY autonomousPendingChanged)
    Q_PROPERTY(QString autonomyStatus READ autonomyStatus NOTIFY autonomyStatusChanged)
    Q_PROPERTY(QString guidanceMode READ guidanceMode NOTIFY guidanceModeChanged)
    // Autonomous visualization properties
    Q_PROPERTY(double pidError READ pidError NOTIFY pidDataChanged)
    Q_PROPERTY(double pidOutput READ pidOutput NOTIFY pidDataChanged)
    Q_PROPERTY(double baseSpeed READ baseSpeed NOTIFY pidDataChanged)
    Q_PROPERTY(double leftMotorSpeed READ leftMotorSpeed NOTIFY pidDataChanged)
    Q_PROPERTY(double rightMotorSpeed READ rightMotorSpeed NOTIFY pidDataChanged)
    Q_PROPERTY(double lineCenterX READ lineCenterX NOTIFY pidDataChanged)
    Q_PROPERTY(double dynamicCenter READ dynamicCenter NOTIFY pidDataChanged)
    Q_PROPERTY(double targetCenter READ targetCenter NOTIFY pidDataChanged)

public:
    explicit RaspiControlClient(QObject *parent = nullptr);

    bool connected() const;
    QString lastError() const;
    int speed() const;
    bool autonomousMode() const;
    bool autonomousPending() const;
    QString autonomyStatus() const;
    QString guidanceMode() const;
    // Visualization getters
    double pidError() const { return m_currentPidError; }
    double pidOutput() const { return m_currentPidOutput; }
    double baseSpeed() const { return m_currentBaseSpeed; }
    double leftMotorSpeed() const { return m_currentLeftSpeed; }
    double rightMotorSpeed() const { return m_currentRightSpeed; }
    double lineCenterX() const { return m_currentLineCenterX; }
    double dynamicCenter() const { return m_currentDynamicCenter; }
    double targetCenter() const { return m_currentTargetCenter; }

    Q_INVOKABLE void connectToHost(const QString &host, int port);
    Q_INVOKABLE void disconnectFromHost();
    Q_INVOKABLE bool sendSpeed(int value);
    Q_INVOKABLE bool sendJoystick(double x, double y, int speedValue);
    Q_INVOKABLE bool sendStop();
    Q_INVOKABLE bool sendShutdown();
    Q_INVOKABLE void setAutonomousEnabled(bool enabled);
    Q_INVOKABLE void updateDetections(const QVariantList &boxes);

signals:
    void connectedChanged();
    void lastErrorChanged();
    void speedChanged();
    void autonomousModeChanged();
    void autonomousPendingChanged();
    void autonomyStatusChanged();
    void guidanceModeChanged();
    void pidDataChanged(); // Emitted when PID visualization data updates

private slots:
    void onConnected();
    void onDisconnected();
    void onErrorOccurred(QAbstractSocket::SocketError socketError);
    void onAutonomousWatchdog();

private:
    struct SteeringDecision {
        bool valid = false;
        double error = 0.0;
        QString mode;
    };

    enum class LineSide {
        Unknown,
        Left,
        Right,
        Both,
    };

    void setLastError(const QString &errorText);
    void setAutonomousModeInternal(bool enabled);
    void setAutonomousPendingInternal(bool pending);
    void setGuidanceMode(const QString &mode);
    void resetAutonomousController();
    void clearAutonomousState(bool sendStopCommand);
    QVector<double> extractLineCenters(const QVariantList &boxes) const;
    SteeringDecision computeSteeringDecision(const QVector<double> &lineCenters);
    bool dispatchAutonomousCommand(const QString &command, bool throttle);
    QString currentAutonomyStatus() const;
    double pidCompute(double error, qint64 nowMs);
    double applyDeadzone(double speedValue) const;
    bool sendRawCommand(const QString &command, bool throttle);

    QTcpSocket m_socket;
    QElapsedTimer m_commandTimer;
    QTimer m_autonomousWatchdog;
    QString m_lastError;
    int m_speed = 0;
    qint64 m_lastCommandMs = 0;
    bool m_autonomousMode = false;
    bool m_autonomousPending = false;
    QString m_guidanceMode = QStringLiteral("MANUAL");
    QString m_lastAutonomousCommand;
    qint64 m_lastAutonomousCommandMs = 0;
    qint64 m_lastDetectionUpdateMs = 0;
    qint64 m_lastLineSeenMs = 0;
    qint64 m_pidLastMs = 0;
    double m_pidPrevError = 0.0;
    double m_pidIntegral = 0.0;
    double m_smoothedSpeed = 40.0;
    double m_estimatedHalfRoadWidth = -1.0;
    LineSide m_lastSeenLineSide = LineSide::Unknown;
    QString m_searchDir = QStringLiteral("left");

    // ── CX-based hysteresis (mirror of main.py slope hysteresis) ──
    QVector<double> m_cxHistory;           // son N frame'in cx değerleri (smoothing)
    static constexpr int kCxHistorySize = 5;
    int m_lastIsLeftDecision = -1;         // -1=unknown, 0=right, 1=left (hysteresis)

    // ── PID stability fixes ──
    double m_filteredError = 0.0;          // EMA-smoothed error (Fix #4)
    QString m_lastMode;                    // mode change detection → PID reset (Fix #3)
    SteeringDecision m_lastSteeringDecision; // cached for line-jump filter (Fix #6)

    // ── Debug flag ──
    bool m_debugEnabled = true;

    // Visualization data (updated each frame during autonomous)
    double m_currentPidError = 0.0;
    double m_currentPidOutput = 0.0;
    double m_currentBaseSpeed = 0.0;
    double m_currentLeftSpeed = 0.0;
    double m_currentRightSpeed = 0.0;
    double m_currentLineCenterX = 0.5; // Normalized 0-1
    double m_currentDynamicCenter = 0.5; // Dynamic center with bias
    double m_currentTargetCenter = 0.5;  // Target center (avgCx + offset)
};
