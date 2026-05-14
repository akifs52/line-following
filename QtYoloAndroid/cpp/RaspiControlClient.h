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
    Q_PROPERTY(double headingError READ headingError NOTIFY pidDataChanged)
    Q_PROPERTY(double totalError READ totalError NOTIFY pidDataChanged)
    Q_PROPERTY(double turnRatio READ turnRatio NOTIFY pidDataChanged)
    Q_PROPERTY(double wallDistance READ wallDistance NOTIFY pidDataChanged)
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
    double headingError() const { return m_currentHeadingError; }
    double totalError() const { return m_currentTotalError; }
    double turnRatio() const { return m_currentTurnRatio; }
    double wallDistance() const { return m_currentWallDistance; }
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
    void onCommandBufferTimeout();

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

    // Durum makinesi için tracking state
    enum class TrackingState {
        TwoLine,      // 2 şerit arası PID
        OneLineArc,   // 1 şerit görülüyor → yay dönüşü
        NoLineFwd,    // Hiç şerit yok, kısa süre düz git
        NoLineStop,   // Uzun süre şerit yok → dur
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
    bool sendRawCommandImpl(const QString &command);  // direkt socket write
    // Yeni durum makinesi yardımcıları
    bool dispatchMotor(double left, double right);
    bool dispatchRaw(const QString &cmd, bool throttle);

    QTcpSocket m_socket;
    QElapsedTimer m_commandTimer;
    QTimer m_autonomousWatchdog;
    QTimer m_commandBufferTimer;  // buffer'daki komutu rate-limit sonunda gönder
    static constexpr qint64 kMinCommandIntervalMs = 30;  // 25-30 ms gönderim sınırı
    qint64 m_lastCommandMs = 0;

    // ── Command buffer & deduplication ──
    QString m_commandBuffer;      // rate-limit dolana kadar biriken son komut
    QString m_lastSentCommand;    // son gönderilen komut (duplicate kontrolü)
    qint64 m_lastSentCommandMs = 0;
    bool m_autonomousMode = false;
    bool m_autonomousPending = false;
    QString m_lastError;
    int m_speed = 0;
    QString m_guidanceMode = QStringLiteral("MANUAL");
    QString m_lastAutonomousCommand;
    qint64 m_lastAutonomousCommandMs = 0;
    qint64 m_lastDetectionUpdateMs = 0;
    qint64 m_lastLineSeenMs = 0;
    qint64 m_pidLastMs = 0;
    double m_pidPrevError = 0.0;
    double m_pidIntegral = 0.0;
    double m_pidLastError = 0.0;
    double m_smoothedSpeed = 40.0;
    LineSide m_lastSeenSide = LineSide::Unknown;
    QString m_searchDir = QStringLiteral("left");
    // Durum makinesi değişkenleri
    TrackingState m_trackingState = TrackingState::TwoLine;
    qint64 m_arcStartMs = 0;
    qint64 m_noLineStartMs = 0;

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

    // ═══════════════════════════════════════════════════════════════
    // ✅ TEK ÇİZGİ REAKTİF TAKİP
    // Hangi çizgiyi görüyorsan ona göre mesafe tut
    // 5cm'den yakınsa sert kaç, uzaktaysa düz git
    // ═══════════════════════════════════════════════════════════════
    static constexpr double kLaneWidthCm = 27.0;
    static constexpr double kWallTargetCm = 15;  // Hedef mesafe (yol/2'den biraz fazla)
    static constexpr double kDangerZoneCm = 11.0;  // Bu mesafenin altında sert dönüş
    static constexpr double kBaseSpeed = 33;
    static constexpr double kMinPwm = 23.0;
    static constexpr double kMaxPwm = 50.0;
    static constexpr double kSteerGain = 0.12;     // Mesafe→dönüş oranı (cm başına)

    static constexpr double kRoiTopRatio = 0.35;

    // State variables
    double m_pixelPerCm = 0.0;  // Varsayılan tahmin ilk frame'de set edilir



    // New methods for ARC PID
    void extractLaneCentersFromMask(const QVariantList &masks, QVector<double> &leftCenters, QVector<double> &rightCenters);
    double computeHeadingError(const QVariantList &masks, int imageWidth, int imageHeight);
    void resetPidController();
    void handleSearchMode(qint64 nowMs);

    // Visualization data (updated each frame during autonomous)
    double m_currentPidError = 0.0;
    double m_currentPidOutput = 0.0;
    double m_currentBaseSpeed = 0.0;
    double m_currentLeftSpeed = 0.0;
    double m_currentRightSpeed = 0.0;
    double m_currentLineCenterX = 0.5; // Normalized 0-1
    double m_currentWallDistance = 0.0;   // Çizgiden mesafe (cm)
    double m_currentTargetCenter = 0.5;  // Target center (avgCx + offset)
    double m_currentHeadingError = 0.0;   // Heading error in radians
    double m_currentTotalError = 0.0;     // Total error (position + heading)
    double m_currentTurnRatio = 0.0;      // Turn ratio after tanh
    QString m_currentMode = "MANUAL";     // Current mode: ARC-FINAL, SEARCH, etc.
};
