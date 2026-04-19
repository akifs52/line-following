#include "RaspiControlClient.h"

#include <QVariantMap>

#include <algorithm>
#include <cmath>

namespace {
constexpr qint64 kMinCommandIntervalMs = 40;
constexpr qint64 kAutonomousWatchdogIntervalMs = 80;
constexpr qint64 kDetectionFeedTimeoutMs = 450;
constexpr double kDetectionScoreThreshold = 0.40;

constexpr double kPidKp = 25.0;
constexpr double kPidKi = 0.05;
constexpr double kPidKd = 10.0;
constexpr double kPidIntegralLimit = 30.0;

constexpr double kAutoBaseSpeed = 40.0;
constexpr double kAutoMinSpeed = 35.0;
constexpr double kAutoMaxSpeed = 50.0;
constexpr double kAutoSpeedSmoothingAlpha = 0.1;
constexpr double kDefaultHalfRoadPct = 0.20;
constexpr double kRoadWidthAlpha = 0.1;

constexpr qint64 kNoLineTimeoutMs = 800;
constexpr double kSearchTurnSpeed = 20.0;
} // namespace

RaspiControlClient::RaspiControlClient(QObject *parent)
    : QObject(parent)
{
    connect(&m_socket, &QTcpSocket::connected, this, &RaspiControlClient::onConnected);
    connect(&m_socket, &QTcpSocket::disconnected, this, &RaspiControlClient::onDisconnected);
    connect(&m_socket, &QTcpSocket::errorOccurred, this, &RaspiControlClient::onErrorOccurred);
    connect(&m_autonomousWatchdog, &QTimer::timeout, this, &RaspiControlClient::onAutonomousWatchdog);

    m_commandTimer.start();
    m_autonomousWatchdog.setInterval(int(kAutonomousWatchdogIntervalMs));
}

bool RaspiControlClient::connected() const
{
    return m_socket.state() == QAbstractSocket::ConnectedState;
}

QString RaspiControlClient::lastError() const
{
    return m_lastError;
}

int RaspiControlClient::speed() const
{
    return m_speed;
}

bool RaspiControlClient::autonomousMode() const
{
    return m_autonomousMode;
}

bool RaspiControlClient::autonomousPending() const
{
    return m_autonomousPending;
}

QString RaspiControlClient::autonomyStatus() const
{
    return currentAutonomyStatus();
}

QString RaspiControlClient::guidanceMode() const
{
    return m_guidanceMode;
}

void RaspiControlClient::connectToHost(const QString &host, int port)
{
    const QString trimmedHost = host.trimmed();
    if (trimmedHost.isEmpty() || port <= 0 || port > 65535) {
        setLastError(QStringLiteral("Gecersiz IP veya port"));
        return;
    }

    clearAutonomousState(false);

    if (m_socket.state() != QAbstractSocket::UnconnectedState) {
        m_socket.abort();
    }

    setLastError(QString());
    m_socket.connectToHost(trimmedHost, quint16(port));
}

void RaspiControlClient::disconnectFromHost()
{
    clearAutonomousState(true);

    if (m_socket.state() != QAbstractSocket::UnconnectedState) {
        m_socket.disconnectFromHost();
        if (m_socket.state() != QAbstractSocket::UnconnectedState) {
            m_socket.abort();
        }
    }
}

bool RaspiControlClient::sendSpeed(int value)
{
    const int clamped = qBound(0, value, 255);
    if (m_speed != clamped) {
        m_speed = clamped;
        emit speedChanged();
    }

    return sendRawCommand(QStringLiteral("PWM%1").arg(clamped), false);
}

bool RaspiControlClient::sendJoystick(double x, double y, int speedValue)
{
    if (m_autonomousMode || m_autonomousPending) {
        return false;
    }

    const double steering = qBound(-1.0, -x, 1.0);
    const double throttle = qBound(-1.0, -y, 1.0);
    const double speedScale = qBound(0.0, speedValue / 255.0, 1.0);

    if (qAbs(throttle) < 0.08 && qAbs(steering) < 0.08) {
        return sendStop();
    }

    const double left = qBound(-100.0, (throttle + steering) * speedScale * 100.0, 100.0);
    const double right = qBound(-100.0, (throttle - steering) * speedScale * 100.0, 100.0);

    return sendRawCommand(
        QStringLiteral("DIFF,%1,%2").arg(left, 0, 'f', 1).arg(right, 0, 'f', 1),
        true);
}

bool RaspiControlClient::sendStop()
{
    return sendRawCommand(QStringLiteral("S"), false);
}

void RaspiControlClient::setAutonomousEnabled(bool enabled)
{
    if (!enabled) {
        clearAutonomousState(true);
        return;
    }

    if (!connected()) {
        setLastError(QStringLiteral("Otonom surus icin TCP baglantisi gerekli"));
        return;
    }

    resetAutonomousController();
    setAutonomousPendingInternal(true);
    setGuidanceMode(QStringLiteral("ARMED"));
    sendStop();
}

void RaspiControlClient::updateDetections(const QVariantList &boxes)
{
    const qint64 nowMs = m_commandTimer.elapsed();
    m_lastDetectionUpdateMs = nowMs;

    if (!m_autonomousPending && !m_autonomousMode) {
        return;
    }

    if (!connected()) {
        clearAutonomousState(false);
        return;
    }

    if (m_autonomousPending) {
        resetAutonomousController();
        m_lastDetectionUpdateMs = nowMs;
        setAutonomousPendingInternal(false);
        setAutonomousModeInternal(true);
    }

    const QVector<double> lineCenters = extractLineCenters(boxes);
    SteeringDecision decision = computeSteeringDecision(lineCenters);

    if (decision.valid) {
        m_lastLineSeenMs = nowMs;

        double pidOut = pidCompute(decision.error, nowMs);
        pidOut = qBound(-100.0, pidOut, 100.0);
        pidOut = std::tanh(pidOut / 90.0) * 100.0;

        double dynamicBase = kAutoBaseSpeed;
        m_smoothedSpeed = (1.0 - kAutoSpeedSmoothingAlpha) * m_smoothedSpeed
            + kAutoSpeedSmoothingAlpha * dynamicBase;
        dynamicBase = m_smoothedSpeed;

        // Swapped directions: left motor gets +pidOut, right motor gets -pidOut
        double speedLeft = qBound(-kAutoMaxSpeed, dynamicBase + pidOut, kAutoMaxSpeed);
        double speedRight = qBound(-kAutoMaxSpeed, dynamicBase - pidOut, kAutoMaxSpeed);

        speedLeft = applyDeadzone(speedLeft);
        speedRight = applyDeadzone(speedRight);

        if (decision.error > 0.1) {
            m_searchDir = QStringLiteral("right");
        } else if (decision.error < -0.1) {
            m_searchDir = QStringLiteral("left");
        }

        // Update visualization data
        m_currentPidError = decision.error;
        m_currentPidOutput = pidOut;
        m_currentBaseSpeed = dynamicBase;
        m_currentLeftSpeed = speedLeft;
        m_currentRightSpeed = speedRight;
        m_currentLineCenterX = 0.5 + (decision.error * 0.5); // Convert error to 0-1 range
        emit pidDataChanged();

        setGuidanceMode(decision.mode);
        dispatchAutonomousCommand(
            QStringLiteral("DIFF,%1,%2")
                .arg(speedLeft, 0, 'f', 1)
                .arg(speedRight, 0, 'f', 1),
            true);
        return;
    }

    const qint64 elapsedMs = nowMs - m_lastLineSeenMs;
    QString command;
    if (elapsedMs < kNoLineTimeoutMs) {
        command = QStringLiteral("DIFF,%1,%2")
                      .arg(kAutoMinSpeed, 0, 'f', 1)
                      .arg(kAutoMinSpeed, 0, 'f', 1);
    } else if (elapsedMs < (kNoLineTimeoutMs * 3)) {
        bool searchLeft = false;
        if (m_lastSeenLineSide == LineSide::Left) {
            searchLeft = true;
        } else if (m_lastSeenLineSide == LineSide::Right) {
            searchLeft = false;
        } else {
            searchLeft = (m_searchDir == QLatin1String("left"));
        }

        if (searchLeft) {
            command = QStringLiteral("DIFF,%1,%2")
                          .arg(-kSearchTurnSpeed, 0, 'f', 1)
                          .arg(kSearchTurnSpeed, 0, 'f', 1);
        } else {
            command = QStringLiteral("DIFF,%1,%2")
                          .arg(kSearchTurnSpeed, 0, 'f', 1)
                          .arg(-kSearchTurnSpeed, 0, 'f', 1);
        }
    } else {
        command = QStringLiteral("S");
    }

    setGuidanceMode(QStringLiteral("SEARCH"));
    dispatchAutonomousCommand(command, command != QLatin1String("S"));
}

void RaspiControlClient::onConnected()
{
    setLastError(QString());
    emit connectedChanged();
    emit autonomyStatusChanged();
}

void RaspiControlClient::onDisconnected()
{
    clearAutonomousState(false);
    emit connectedChanged();
    emit autonomyStatusChanged();
}

void RaspiControlClient::onErrorOccurred(QAbstractSocket::SocketError socketError)
{
    Q_UNUSED(socketError);
    clearAutonomousState(false);
    setLastError(m_socket.errorString());
    emit connectedChanged();
    emit autonomyStatusChanged();
}

void RaspiControlClient::onAutonomousWatchdog()
{
    if (!m_autonomousMode) {
        m_autonomousWatchdog.stop();
        return;
    }

    const qint64 nowMs = m_commandTimer.elapsed();
    if (m_lastDetectionUpdateMs > 0 && (nowMs - m_lastDetectionUpdateMs) <= kDetectionFeedTimeoutMs) {
        return;
    }

    dispatchAutonomousCommand(QStringLiteral("S"), false);
    setGuidanceMode(QStringLiteral("WAITING"));
}

void RaspiControlClient::setLastError(const QString &errorText)
{
    if (m_lastError == errorText) {
        return;
    }

    m_lastError = errorText;
    emit lastErrorChanged();
}

void RaspiControlClient::setAutonomousModeInternal(bool enabled)
{
    if (m_autonomousMode == enabled) {
        return;
    }

    m_autonomousMode = enabled;
    emit autonomousModeChanged();
    emit autonomyStatusChanged();

    if (m_autonomousMode) {
        m_autonomousWatchdog.start();
    } else {
        m_autonomousWatchdog.stop();
    }
}

void RaspiControlClient::setAutonomousPendingInternal(bool pending)
{
    if (m_autonomousPending == pending) {
        return;
    }

    m_autonomousPending = pending;
    emit autonomousPendingChanged();
    emit autonomyStatusChanged();
}

void RaspiControlClient::setGuidanceMode(const QString &mode)
{
    if (m_guidanceMode == mode) {
        return;
    }

    m_guidanceMode = mode;
    emit guidanceModeChanged();
}

void RaspiControlClient::resetAutonomousController()
{
    const qint64 nowMs = m_commandTimer.elapsed();
    m_pidPrevError = 0.0;
    m_pidIntegral = 0.0;
    m_pidLastMs = nowMs;
    m_lastLineSeenMs = nowMs;
    m_lastDetectionUpdateMs = 0;
    m_lastAutonomousCommand.clear();
    m_lastAutonomousCommandMs = 0;
    m_smoothedSpeed = kAutoBaseSpeed;
    m_estimatedHalfRoadWidth = -1.0;
    m_lastSeenLineSide = LineSide::Unknown;
    m_searchDir = QStringLiteral("left");
}

void RaspiControlClient::clearAutonomousState(bool sendStopCommand)
{
    const bool wasActive = m_autonomousMode || m_autonomousPending;
    if (sendStopCommand && wasActive && connected()) {
        sendStop();
    }

    setAutonomousPendingInternal(false);
    setAutonomousModeInternal(false);
    resetAutonomousController();
    setGuidanceMode(QStringLiteral("MANUAL"));
}

QVector<double> RaspiControlClient::extractLineCenters(const QVariantList &boxes) const
{
    QVector<double> centers;
    centers.reserve(boxes.size());

    for (const QVariant &item : boxes) {
        const QVariantMap box = item.toMap();
        if (box.isEmpty()) {
            continue;
        }

        const double score = box.value(QStringLiteral("score")).toDouble();
        if (score < kDetectionScoreThreshold) {
            continue;
        }

        const double x = box.value(QStringLiteral("x")).toDouble();
        const double w = box.value(QStringLiteral("w")).toDouble();
        const double centerX = qBound(0.0, x + (w * 0.5), 1.0);
        centers.push_back(centerX);
    }

    std::sort(centers.begin(), centers.end());
    return centers;
}

RaspiControlClient::SteeringDecision RaspiControlClient::computeSteeringDecision(const QVector<double> &lineCenters)
{
    SteeringDecision decision;

    const double halfRoad = m_estimatedHalfRoadWidth > 0.0 ? m_estimatedHalfRoadWidth : kDefaultHalfRoadPct;
    if (lineCenters.isEmpty()) {
        decision.mode = QStringLiteral("SEARCH");
        return decision;
    }

    double targetCenter = 0.5;
    if (lineCenters.size() >= 2) {
        const double leftCenter = lineCenters.constFirst();
        const double rightCenter = lineCenters.constLast();
        const double gap = rightCenter - leftCenter;
        if (gap > 0.03) {
            const double newHalfRoad = gap * 0.5;
            if (m_estimatedHalfRoadWidth < 0.0) {
                m_estimatedHalfRoadWidth = newHalfRoad;
            } else {
                m_estimatedHalfRoadWidth = ((1.0 - kRoadWidthAlpha) * m_estimatedHalfRoadWidth)
                    + (kRoadWidthAlpha * newHalfRoad);
            }
        }

        targetCenter = (leftCenter + rightCenter) * 0.5;
        m_lastSeenLineSide = LineSide::Both;
        decision.mode = QStringLiteral("2-LINE");
    } else {
        const double center = lineCenters.constFirst();
        if (center < 0.5) {
            targetCenter = qBound(0.0, center + halfRoad, 1.0);
            m_lastSeenLineSide = LineSide::Left;
            decision.mode = QStringLiteral("1-LINE-L");
        } else {
            targetCenter = qBound(0.0, center - halfRoad, 1.0);
            m_lastSeenLineSide = LineSide::Right;
            decision.mode = QStringLiteral("1-LINE-R");
        }
    }

    decision.valid = true;
    decision.error = qBound(-1.0, (targetCenter - 0.5) / 0.5, 1.0);
    return decision;
}

bool RaspiControlClient::dispatchAutonomousCommand(const QString &command, bool throttle)
{
    const qint64 nowMs = m_commandTimer.elapsed();
    if (command == m_lastAutonomousCommand && (nowMs - m_lastAutonomousCommandMs) < 100) {
        return true;
    }

    if (!sendRawCommand(command, throttle)) {
        return false;
    }

    m_lastAutonomousCommand = command;
    m_lastAutonomousCommandMs = nowMs;
    return true;
}

QString RaspiControlClient::currentAutonomyStatus() const
{
    if (!connected()) {
        return QStringLiteral("OFFLINE");
    }
    if (m_autonomousPending) {
        return QStringLiteral("ARMED");
    }
    if (m_autonomousMode) {
        return QStringLiteral("AUTONOMOUS");
    }
    return QStringLiteral("MANUAL");
}

double RaspiControlClient::pidCompute(double error, qint64 nowMs)
{
    double dt = (nowMs - m_pidLastMs) / 1000.0;
    if (dt <= 0.0) {
        dt = 0.01;
    }
    m_pidLastMs = nowMs;

    const double p = kPidKp * error;

    m_pidIntegral += error * dt;
    m_pidIntegral = qBound(-kPidIntegralLimit, m_pidIntegral, kPidIntegralLimit);
    const double i = kPidKi * m_pidIntegral;

    const double derivative = (error - m_pidPrevError) / dt;
    const double d = kPidKd * derivative;
    m_pidPrevError = error;

    return p + i + d;
}

double RaspiControlClient::applyDeadzone(double speedValue) const
{
    if (qAbs(speedValue) < 40.0) {
        if (qAbs(speedValue) < 15.0) {
            return 0.0;
        }
        return speedValue > 0.0 ? kAutoMinSpeed : -kAutoMinSpeed;
    }

    return speedValue;
}

bool RaspiControlClient::sendRawCommand(const QString &command, bool throttle)
{
    if (!connected()) {
        return false;
    }

    if (throttle) {
        const qint64 nowMs = m_commandTimer.elapsed();
        if (nowMs - m_lastCommandMs < kMinCommandIntervalMs) {
            return true;
        }
        m_lastCommandMs = nowMs;
    }

    const QByteArray payload = command.toUtf8() + '\n';
    if (m_socket.write(payload) == -1) {
        setLastError(m_socket.errorString());
        emit connectedChanged();
        emit autonomyStatusChanged();
        return false;
    }

    m_socket.flush();
    return true;
}
