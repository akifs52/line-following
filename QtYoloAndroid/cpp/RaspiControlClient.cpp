#include "RaspiControlClient.h"

#include <QVariantMap>

#include <algorithm>
// #include <cmath>  // Şu an kullanılmıyor (qBound Qt'ye ait)

namespace {
// Temel zamanlama sabitleri
constexpr qint64 kMinCommandIntervalMs = 40;
constexpr qint64 kAutonomousWatchdogIntervalMs = 80;
constexpr qint64 kDetectionFeedTimeoutMs = 350;
constexpr double kDetectionScoreThreshold = 0.40;

// ═══ PID PARAMETRELERİ (PI kontrol - merkezleme için) ═══
constexpr double kPidKp = 60.0;      // 90'dan 80'e (biraz daha yumuşak)
constexpr double kPidKi = 15.0;      // İNTEGRAL - merkeze oturtmak için
constexpr double kPidIntegralMax = 25.0;  // İntegral limiti

// ═══ MOTOR HIZLARI ═══
constexpr double kAutoBaseSpeed = 38.0;
constexpr double kAutoMaxSpeed = 55.0;
constexpr double kTurnSlowSpeed = 20.0;

// ═══ HAT TAKİP ═══
constexpr double kDefaultHalfRoadPct = 0.25;
constexpr qint64 kNoLineTimeoutMs = 800;
constexpr double kSearchTurnSpeed = 35.0;
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

bool RaspiControlClient::sendShutdown()
{
    return sendRawCommand(QStringLiteral("SHUTDOWN"), false);
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

    // Çizgi merkezlerini çıkar
    const QVector<double> lineCenters = extractLineCenters(boxes);



    // ═══════════════════════════════════════════════════════
    // BASİT HAT TAKİP MANTIĞI
    // ═══════════════════════════════════════════════════════

    double error = 0.0;
    QString mode;
    bool lineSeen = false;

    if (lineCenters.size() >= 2) {
        const double leftCx = lineCenters.constFirst();
        const double rightCx = lineCenters.constLast();
        const double roadWidth = rightCx - leftCx;

        // IKI CIZGI: ortalarini hedefle
        const double middle = (leftCx + rightCx) * 0.5;
        error = (middle - 0.5) * 2.0;
        mode = QStringLiteral("2-LINE");
        lineSeen = true;
        m_lastSeenLineSide = LineSide::Both;

        // Yol genisligini ogren
        m_estimatedHalfRoadWidth = roadWidth * 0.5;

        if (m_debugEnabled) {
            qDebug().noquote() << QStringLiteral(
                                      "[OK] 2-LINE: sol=%1 sag=%2 genislik=%3 orta=%4 hata=%5")
                                      .arg(leftCx, 0, 'f', 3)
                                      .arg(rightCx, 0, 'f', 3)
                                      .arg(roadWidth, 0, 'f', 3)
                                      .arg(middle, 0, 'f', 3)
                                      .arg(error, 0, 'f', 3);
        }
    }

    // Tek cizgi modu (veya duplicate'ten dusen)
    if (!lineSeen && lineCenters.size() >= 1) {
        const double cx = lineCenters.constFirst();
        const double halfRoad = (m_estimatedHalfRoadWidth > 0.0)
                                    ? m_estimatedHalfRoadWidth
                                    : kDefaultHalfRoadPct;

        if (cx < 0.5) {
            const double target = cx + halfRoad;
            error = (target - 0.5) * 2.0;
            mode = QStringLiteral("1-LINE-L");
            m_lastSeenLineSide = LineSide::Left;

            if (m_debugEnabled) {
                qDebug().noquote() << QStringLiteral(
                                          "<-- 1-LINE-L: cx=%1 target=%2 halfRoad=%3 hata=%4")
                                          .arg(cx, 0, 'f', 3)
                                          .arg(target, 0, 'f', 3)
                                          .arg(halfRoad, 0, 'f', 3)
                                          .arg(error, 0, 'f', 3);
            }
        } else {
            const double target = cx - halfRoad;
            error = (target - 0.5) * 2.0;
            mode = QStringLiteral("1-LINE-R");
            m_lastSeenLineSide = LineSide::Right;

            if (m_debugEnabled) {
                qDebug().noquote() << QStringLiteral(
                                          "--> 1-LINE-R: cx=%1 target=%2 halfRoad=%3 hata=%4")
                                          .arg(cx, 0, 'f', 3)
                                          .arg(target, 0, 'f', 3)
                                          .arg(halfRoad, 0, 'f', 3)
                                          .arg(error, 0, 'f', 3);
            }
        }
        lineSeen = true;
    }

    // ═══════════════════════════════════════════════════════
    // PI KONTROL (P + I)
    // ═══════════════════════════════════════════════════════
    if (lineSeen) {
        m_lastLineSeenMs = nowMs;

        // KULLANICI İSTEĞİ: Her 500ms'de bir sistemi taze (ilk açılış) haline döndür
        static qint64 lastSoftResetMs = 0;
        if (nowMs - lastSoftResetMs > 10) {
            lastSoftResetMs = nowMs;
            m_pidIntegral = 0.0;
            m_estimatedHalfRoadWidth = -1.0;
        }

        // dt hesapla (saniye cinsinden)
        double dt = (nowMs - m_pidLastMs) / 1000.0;
        if (dt < 0.01) dt = 0.01;   // min 10ms
        if (dt > 0.20) dt = 0.20;   // max 200ms
        m_pidLastMs = nowMs;

        // P terimi
        double pTerm = kPidKp * error;

        // I terimi (integral)
        m_pidIntegral += error * dt;
        m_pidIntegral = qBound(-kPidIntegralMax, m_pidIntegral, kPidIntegralMax);

        // Mod değişince integrali sıfırla
        if (mode != m_lastMode) {
            m_pidIntegral = 0.0;
            m_pidPrevError = error;
        }
        m_lastMode = mode;

        double iTerm = kPidKi * m_pidIntegral;

        // Toplam dönüş
        double turnAmount = pTerm + iTerm;

        // Motor hızları
        double speedLeft = kAutoBaseSpeed + turnAmount;
        double speedRight = kAutoBaseSpeed - turnAmount;

        speedLeft = qBound(kTurnSlowSpeed, speedLeft, kAutoMaxSpeed);
        speedRight = qBound(kTurnSlowSpeed, speedRight, kAutoMaxSpeed);

        m_pidPrevError = error;

        // Debug'a ekle
        if (m_debugEnabled && !lineCenters.isEmpty()) {
            static qint64 lastSummaryMs = 0;
            if (nowMs - lastSummaryMs > 1000) {
                lastSummaryMs = nowMs;

                qDebug().noquote() << QStringLiteral(
                    "===========================================");
                qDebug().noquote() << QStringLiteral(
                    "[DURUM OZETI] (her 1 sn)");
                qDebug().noquote() << QStringLiteral(
                                          "   Cizgi Sayisi : %1").arg(lineCenters.size());
                qDebug().noquote() << QStringLiteral(
                                          "   Mod          : %1").arg(mode);
                qDebug().noquote() << QStringLiteral(
                                          "   Hata (error) : %1").arg(error, 0, 'f', 3);
                qDebug().noquote() << QStringLiteral(
                                          "   P            : %1").arg(pTerm, 0, 'f', 1);
                qDebug().noquote() << QStringLiteral(
                                          "   I            : %1").arg(iTerm, 0, 'f', 1);
                qDebug().noquote() << QStringLiteral(
                                          "   Integral     : %1").arg(m_pidIntegral, 0, 'f', 2);
                qDebug().noquote() << QStringLiteral(
                                          "   Donus Miktar : %1").arg(turnAmount, 0, 'f', 1);
                qDebug().noquote() << QStringLiteral(
                                          "   Sol Teker    : %1").arg(speedLeft, 0, 'f', 1);
                qDebug().noquote() << QStringLiteral(
                                          "   Sag Teker    : %1").arg(speedRight, 0, 'f', 1);
                qDebug().noquote() << QStringLiteral(
                                          "   Yol Genisligi: %1").arg(m_estimatedHalfRoadWidth * 2, 0, 'f', 3);

                double centerPos = 0.5 + (error * 0.5);
                int barPos = qBound(0, int(centerPos * 40), 39);
                QString bar(40, QLatin1Char('-'));
                bar[19] = QLatin1Char('|');
                if (qAbs(error) < 0.02) {
                    bar[19] = QLatin1Char('O');  // Tam ortada
                } else if (barPos < 19) {
                    bar[barPos] = QLatin1Char('#');
                } else if (barPos > 19) {
                    bar[barPos] = QLatin1Char('#');
                }
                qDebug().noquote() << QStringLiteral(
                    "   [----------------------------------------]");
                qDebug().noquote() << QStringLiteral(
                                          "   [%1]").arg(bar);
                qDebug().noquote() << QStringLiteral(
                    "   [----------------------------------------]");
                qDebug().noquote() << QStringLiteral(
                    "   < SOL                        SAG >");
                qDebug().noquote() << QStringLiteral(
                    "===========================================");
            }

            QString lineInfo;
            for (int i = 0; i < lineCenters.size(); ++i) {
                lineInfo += QStringLiteral(" C%1=%2").arg(i+1).arg(lineCenters[i], 0, 'f', 2);
            }
            qDebug().noquote() << QStringLiteral(
                                      "> %1 | Hata:%2 | P:%3 I:%4 | %5")
                                      .arg(mode)
                                      .arg(error, 0, 'f', 3)
                                      .arg(pTerm, 0, 'f', 1)
                                      .arg(iTerm, 0, 'f', 1)
                                      .arg(lineInfo);
        }

        m_currentPidError = error;
        m_currentPidOutput = turnAmount;
        m_currentBaseSpeed = kAutoBaseSpeed;
        m_currentLeftSpeed = speedLeft;
        m_currentRightSpeed = speedRight;
        m_currentLineCenterX = 0.5 + (error * 0.5);
        m_currentTargetCenter = 0.5 + (error * 0.5);
        m_currentDynamicCenter = 0.5 + (m_pidIntegral * 0.05);

        emit pidDataChanged();

        setGuidanceMode(mode);
        dispatchAutonomousCommand(
            QStringLiteral("DIFF,%1,%2")
                .arg(speedLeft, 0, 'f', 1)
                .arg(speedRight, 0, 'f', 1),
            true);
        return;
    }

    // ═══════════════════════════════════════════════════════
    // ÇİZGİ YOKSA: ARAMA MODU
    // ═══════════════════════════════════════════════════════
    const qint64 elapsedMs = nowMs - m_lastLineSeenMs;
    QString command;

    // Çizgi kaybı uyarısı
    if (m_debugEnabled && lineCenters.isEmpty()) {
        if (elapsedMs > 100) {  // 100ms'den fazla çizgi yoksa uyar
            qDebug().noquote() << QStringLiteral(
                                      "! CIZGI YOK ! (%1 ms) - %2")
                                      .arg(elapsedMs)
                                      .arg(elapsedMs < kNoLineTimeoutMs ? "DÜZ GİDİYOR" :
                                               elapsedMs < kNoLineTimeoutMs * 3 ? "ARIYOR" : "DURDU");
        }
    }

    if (elapsedMs < kNoLineTimeoutMs) {
        // Kısa süre çizgi yok → düz git
        command = QStringLiteral("DIFF,%1,%2")
                      .arg(kAutoBaseSpeed, 0, 'f', 1)
                      .arg(kAutoBaseSpeed, 0, 'f', 1);
        setGuidanceMode(QStringLiteral("FWD"));
    }
    else if (elapsedMs < (kNoLineTimeoutMs * 3)) {
        // Orta süre çizgi yok → son görülen çizgi yönünde ara
        bool searchLeft = false;
        if (m_lastSeenLineSide == LineSide::Left) {
            searchLeft = true;  // Sol çizgi gördüysen sola dön (çizgiyi kaybettin)
        } else if (m_lastSeenLineSide == LineSide::Right) {
            searchLeft = false; // Sağ çizgi gördüysen sağa dön
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
        setGuidanceMode(QStringLiteral("SEARCH"));
    }
    else {
        // Uzun süre çizgi yok → dur
        command = QStringLiteral("S");
        setGuidanceMode(QStringLiteral("STOP"));
    }

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
    m_lastLineSeenMs = nowMs;
    m_lastDetectionUpdateMs = 0;
    m_lastAutonomousCommand.clear();
    m_lastAutonomousCommandMs = 0;
    m_estimatedHalfRoadWidth = -1.0;
    m_lastSeenLineSide = LineSide::Unknown;
    m_searchDir = QStringLiteral("left");
    m_lastMode.clear();
    m_pidIntegral = 0.0;      // EKLENDİ
    m_pidLastMs = nowMs;      // EKLENDİ
    m_pidPrevError = 0.0;     // EKLENDİ
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

    // YAKIN TESPİTLERİ BİRLEŞTİR (aynı çizginin duplicate)
    if (centers.size() > 1) {
        QVector<double> merged;
        merged.reserve(centers.size());

        double currentGroup = centers.constFirst();
        int groupCount = 1;

        for (int i = 1; i < centers.size(); ++i) {
            if (centers[i] - currentGroup < 0.30) {  // %10'dan yakınsa aynı çizgi
                // Aynı gruba ekle (ortalama al)
                currentGroup = (currentGroup * groupCount + centers[i]) / (groupCount + 1);
                groupCount++;
            } else {
                // Grubu kaydet, yeni gruba başla
                merged.push_back(currentGroup);
                currentGroup = centers[i];
                groupCount = 1;
            }
        }
        // Son grubu ekle
        merged.push_back(currentGroup);

        if (m_debugEnabled && merged.size() != centers.size()) {
            qDebug().noquote() << QStringLiteral(
                                      "[BIRLESTIRME] %1 tespit -> %2 cizgi")
                                      .arg(centers.size()).arg(merged.size());
        }

        return merged;
    }

    return centers;
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
