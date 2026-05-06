#include "RaspiControlClient.h"

#include <QVariantMap>

#include <algorithm>
#include <cmath>  // ✅ std::tanh ve std::atan için gerekli

namespace {
// Temel zamanlama sabitleri
constexpr qint64 kMinCommandIntervalMs = 50;
constexpr qint64 kAutonomousWatchdogIntervalMs = 80;
constexpr qint64 kDetectionFeedTimeoutMs = 350;
constexpr double kDetectionScoreThreshold = 0.30;
constexpr double kLineMergeThreshold = 0.30;

// ═══════════════════════════════════════════════════════════════
// ✅ LOCAL CONSTANTS (not in header)
// ═══════════════════════════════════════════════════════════════
constexpr double kSingleLineTargetCm = 8.0; // Tek çizgide sabit hedef mesafe
double clampErrorCm(double e) { return qBound(-20.0, e, 20.0); } // ECM clamp
constexpr qint64 kNoLineTimeoutMs = 500;   // Çizgi kaybı timeout
constexpr double kSearchTurnSpeed = 35.0;  // Arama dönüş hızı
constexpr double kPidIntegralMax = 10.0;   // Integral limit
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

    // Ölçümler her zaman yapılır (manuel modda da)
    // Motor komutları sadece otonom modda gönderilir

    if (m_autonomousPending) {
        resetAutonomousController();
        resetPidController();
        m_lastDetectionUpdateMs = nowMs;
        setAutonomousPendingInternal(false);
        setAutonomousModeInternal(true);
        m_calibrationDone = false;
        m_calibrationFrameCount = 0;
        m_calibrationSum = 0.0;
        m_referenceLaneWidth = 0.0;
        m_pixelPerCm = 0.0;
    }

    // Sol ve sağ çizgi merkezlerini çıkar
    QVariantMap primaryDetection;
    for (const QVariant &item : boxes) {
        const QVariantMap detection = item.toMap();
        if (detection.isEmpty()) {
            continue;
        }
        if (detection.value(QStringLiteral("score")).toDouble() < kDetectionScoreThreshold) {
            continue;
        }
        if (!detection.value(QStringLiteral("hasLaneMetrics")).toBool()) {
            continue;
        }
        primaryDetection = detection;
        break;
    }

    // Tüm merkezleri birleştir
    if (primaryDetection.isEmpty()) {
        handleSearchMode(nowMs);
        return;
    }

    // Çizgi yoksa arama modu
    if (primaryDetection.isEmpty()) {
        handleSearchMode(nowMs);
        return;
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ 2 ÇİZGİ TESPİTİ VE KALİBRASYON
    // ═══════════════════════════════════════════════════════════════
    const double frameWidth = std::max(1.0, primaryDetection.value(QStringLiteral("frameWidth")).toDouble());
    const double laneLeftX = primaryDetection.value(QStringLiteral("laneLeftX")).toDouble();
    const double laneRightX = primaryDetection.value(QStringLiteral("laneRightX")).toDouble();
    double laneCenter = primaryDetection.value(QStringLiteral("laneCenterX")).toDouble();
    const double headingError = primaryDetection.value(QStringLiteral("headingError")).toDouble();

    // Tek çizgi durumunu kontrol et
    const bool leftDetected = (laneLeftX >= 0.0);
    const bool rightDetected = (laneRightX >= 0.0);

    double laneWidthPixel = 0.0;
    QString lineStatus;

    if (leftDetected && rightDetected) {
        // ✅ 2 çizgi var - normal ortalama
        laneWidthPixel = (laneRightX - laneLeftX) * frameWidth;
        if (laneCenter <= 0.0 || laneCenter >= 1.0) {
            laneCenter = (laneLeftX + laneRightX) * 0.5;
        }
        lineStatus = QStringLiteral("DUAL");
    } else if (leftDetected && !rightDetected) {
        // ✅ Sadece SOL çizgi var → çizgiden 10cm sağa git
        const double laneLeftPx = laneLeftX * frameWidth;
        double targetOffsetPx = (m_pixelPerCm > 1e-6)
                                    ? (m_pixelPerCm * kSingleLineTargetCm)
                                    : (frameWidth * 0.08); // fallback ~8% genişlik
        const double virtualCenterPx = laneLeftPx + targetOffsetPx;
        laneCenter = virtualCenterPx / frameWidth;
        laneWidthPixel = 0.0; // Tek çizgi: kalibrasyona katkı yok
        lineStatus = QStringLiteral("LEFT_ONLY");
    } else if (!leftDetected && rightDetected) {
        // ✅ Sadece SAĞ çizgi var → çizgiden 10cm sola git
        const double laneRightPx = laneRightX * frameWidth;
        double targetOffsetPx = (m_pixelPerCm > 1e-6)
                                    ? (m_pixelPerCm * kSingleLineTargetCm)
                                    : (frameWidth * 0.08); // fallback
        const double virtualCenterPx = laneRightPx - targetOffsetPx;
        laneCenter = virtualCenterPx / frameWidth;
        laneWidthPixel = 0.0; // Tek çizgi: kalibrasyona katkı yok
        lineStatus = QStringLiteral("RIGHT_ONLY");
    } else {    
        // ❌ Hiç çizgi yok
        handleSearchMode(nowMs);
        return;
    }

    // Lane center geçerlilik kontrolü
    if (laneCenter <= 0.05 || laneCenter >= 0.95) {
        handleSearchMode(nowMs);
        return;
    }

    m_lastLineSeenMs = nowMs;

    // ═══════════════════════════════════════════════════════════════
    // ✅ KALİBRASYON (ilk 10 frame)
    // ═══════════════════════════════════════════════════════════════
    if (!m_calibrationDone) {
        // Kalibrasyon SADECE iki gerçek çizgi varken yapılır
        if (leftDetected && rightDetected) {
            // Gerçekçi genişlik kontrolü: sanal/yanlış eşleşmeleri reddet
            if (laneWidthPixel > 100.0) {
                // İlk geçerli frame referans olsun
                if (m_calibrationFrameCount == 0) {
                    m_referenceLaneWidth = laneWidthPixel;
                }

                // %20 tolerans ile outlier reddet
                const double minAllowed = m_referenceLaneWidth * 0.8;
                const double maxAllowed = m_referenceLaneWidth * 1.2;

                if (laneWidthPixel < minAllowed || laneWidthPixel > maxAllowed) {
                    if (m_debugEnabled) {
                        qDebug().noquote() << QStringLiteral("[KALIBRASYON] OUTLIER REDDEDILDI: %1 (ref: %2)").arg(laneWidthPixel, 0, 'f', 1).arg(m_referenceLaneWidth, 0, 'f', 1);
                    }
                } else {
                    m_calibrationFrameCount++;
                    m_calibrationSum += laneWidthPixel / kLaneWidthCm;

                    if (m_debugEnabled) {
                        qDebug().noquote() << QStringLiteral("[KALIBRASYON] %1/%2").arg(m_calibrationFrameCount).arg(kCalibrationFrames);
                    }

                    if (m_calibrationFrameCount >= kCalibrationFrames) {
                        m_pixelPerCm = m_calibrationSum / kCalibrationFrames;
                        m_calibrationDone = true;
                        if (m_debugEnabled) {
                            qDebug().noquote() << QStringLiteral("[KALIBRASYON] Tamamlandi: %1 pixel/cm").arg(m_pixelPerCm, 0, 'f', 2);
                        }
                    }
                }

                // Debug: kalibrasyon değerleri
                if (m_debugEnabled) {
                    qDebug() << "[DEBUG] laneWidthPx:" << laneWidthPixel
                             << "pixelPerCm:" << m_pixelPerCm
                             << "virtualWidthPx:" << (kLaneWidthCm * m_pixelPerCm)
                             << "frame:" << m_calibrationFrameCount;
                }
            } else if (m_debugEnabled) {
                qDebug().noquote() << QStringLiteral("[KALIBRASYON] COK DAR REDDEDILDI: %1 px").arg(laneWidthPixel, 0, 'f', 1);
            }
        } else if (m_debugEnabled) {
            qDebug().noquote() << QStringLiteral("[KALIBRASYON] TEK CIZGI - BEKLIYOR");
        }

        // � Geçici: kalibrasyon bitmeden önce default 20 px/cm kullan
        if (m_pixelPerCm <= 0.0) {
            m_pixelPerCm = 20.0;
        }

        // �� Kalibrasyon bitmeden MOTOR DUR
        if (m_autonomousMode) {
            dispatchAutonomousCommand(QStringLiteral("DIFF,0,0"), false);
            setGuidanceMode(QStringLiteral("CALIBRATING"));
        } else {
            setGuidanceMode(QStringLiteral("READY"));
        }

        // PID state sıfırla (kalibrasyon sırasında integrator dolmasın)
        resetPidController();
        m_pidLastMs = nowMs;

        m_currentPidError = 0.0;
        m_currentPidOutput = 0.0;
        m_currentBaseSpeed = 0.0;
        m_currentLeftSpeed = 0.0;
        m_currentRightSpeed = 0.0;
        m_currentLineCenterX = laneCenter;
        m_currentTargetCenter = laneCenter;
        m_currentDynamicCenter = 0.5;
        m_currentHeadingError = headingError;
        m_currentTotalError = 0.0;
        m_currentTurnRatio = 0.0;
        m_currentMode = "CALIBRATING";
        emit pidDataChanged();
        return;
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ HATA HESAPLAMA (İKİ ÇİZGİ vs TEK ÇİZGİ)
    // ═══════════════════════════════════════════════════════════════
    if (m_pixelPerCm <= 1e-6) {
        handleSearchMode(nowMs);
        return;
    }

    double errorCm = 0.0;

    if (lineStatus == QStringLiteral("LEFT_ONLY")) {
        // 🎯 DUVAR TAKİP: sol çizgiden ~8cm sağda kal
        const double laneLeftPx = laneLeftX * frameWidth;
        const double robotCenterPx = 0.5 * frameWidth;
        const double currentDistanceCm = (robotCenterPx - laneLeftPx) / m_pixelPerCm;
        constexpr double targetDistanceCm = 8.0;
        errorCm = clampErrorCm(targetDistanceCm - currentDistanceCm); // Pozitif = çok yakın, sola git
        m_lastSeenSide = LineSide::Left;
    } else if (lineStatus == QStringLiteral("RIGHT_ONLY")) {
        // 🎯 DUVAR TAKİP: sağ çizgiden ~8cm solda kal
        const double laneRightPx = laneRightX * frameWidth;
        const double robotCenterPx = 0.5 * frameWidth;
        const double currentDistanceCm = (laneRightPx - robotCenterPx) / m_pixelPerCm;
        constexpr double targetDistanceCm = 8.0;
        errorCm = -clampErrorCm(targetDistanceCm - currentDistanceCm); // Negatif = çok yakın, sağa git
        m_lastSeenSide = LineSide::Right;
    } else {
        // ✅ İKİ ÇİZGİ: Normal lane center hatası
        const double errorPx = (0.5 - laneCenter) * frameWidth;
        const double errorRawCm = errorPx / m_pixelPerCm;
        errorCm = clampErrorCm(errorRawCm);
        m_lastSeenSide = (errorCm > 0) ? LineSide::Left : LineSide::Right;
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ TOPLAM HATA = Pozisyon + Heading
    // Düzde heading minimal (salınım önle), virajda agresif (proaktif dönüş)
    // Tek çizgide (virajda) heading kritik → full gain
    // ═══════════════════════════════════════════════════════════════
    const double clampedHeading = qBound(-0.30, headingError, 0.30);

    double headingGain;
    if (lineStatus == QStringLiteral("DUAL")) {
        // Düzde |heading| < 0.03 ise neredeyse düz → heading etkisini baskıla
        headingGain = (std::abs(clampedHeading) < 0.03) ? 1.0 : kKHeading;
    } else {
        // Tek çizgide viraj ortasındayız: heading yüksekse agresif, düşükse minimal
        headingGain = (std::abs(clampedHeading) > 0.12) ? 2.5 : 1.0;
    }

    double totalError = errorCm + headingGain * clampedHeading;

    m_lastLineSeenMs = nowMs;

    // ═══════════════════════════════════════════════════════════════
    // ✅ PID HESAPLAMA (main.py birebir)
    // ═══════════════════════════════════════════════════════════════
    double dt = (nowMs - m_pidLastMs) / 1000.0;
    if (dt <= 0) dt = 0.001;
    if (dt > 0.2) dt = 0.2;
    m_pidLastMs = nowMs;

    double derivative = (totalError - m_pidLastError) / dt;
    m_pidIntegral += totalError * dt;
    m_pidIntegral = qBound(-kPidIntegralMax, m_pidIntegral, kPidIntegralMax);

    double pidOut = kPidKp * totalError + kPidKd * derivative + kPidKi * m_pidIntegral;
    
    // Yumuşatma (tanh)
    double turn = std::tanh(pidOut);
    m_pidLastError = totalError;

    // ═══════════════════════════════════════════════════════════════
    // ✅ ARC MOTOR HESABI (Tank dönüş YOK)
    // ═══════════════════════════════════════════════════════════════
    // turn pozitif = sağa dön (sağ motor hızlı, sol yavaş) - TERSİ
    double leftRatio = 1.0 - turn;
    double rightRatio = 1.0 + turn;

    // ═══════════════════════════════════════════════════════════════
    // ✅ ADAPTIVE SPEED: 2 çizgide %30 yavaş, tek çizgide tam hız
    // ═══════════════════════════════════════════════════════════════
    const double baseSpeed = (lineStatus == QStringLiteral("DUAL"))
                             ? kBaseSpeed * 0.7
                             : kBaseSpeed;

    // ═══════════════════════════════════════════════════════════════
    // ✅ PWM HESAPLAMA (gerçek diferansiyel, normalize YOK)
    // Dış teker hızlanır, iç teker yavaşlar → agresif dönüş
    // ═══════════════════════════════════════════════════════════════
    double leftPwm  = baseSpeed * (1.0 - turn);
    double rightPwm = baseSpeed * (1.0 + turn);

    // Sadece fiziksel limitlere clip et
    leftPwm  = qBound(kMinPwm, leftPwm,  kMaxPwm);
    rightPwm = qBound(kMinPwm, rightPwm, kMaxPwm);

    // ═══════════════════════════════════════════════════════════════
    // ✅ KOMUT GÖNDER (sadece otonom modda)
    // ═══════════════════════════════════════════════════════════════
    if (m_autonomousMode) {
        QString cmd = QStringLiteral("DIFF,%1,%2").arg(leftPwm, 0, 'f', 1).arg(rightPwm, 0, 'f', 1);
        dispatchAutonomousCommand(cmd, true);
    }

    // Debug (her zaman göster, motor durumunu da belirt)
    if (m_debugEnabled) {
        QString motorStatus = m_autonomousMode ? "AUTO" : "MANUAL";
        qDebug().noquote() << QStringLiteral(
            "[ARC-%10] %1 | L:%2 R:%3 | Spd:%4 | Left:%5 Right:%6 | ErrCM:%7 | Head:%8 | Turn:%9 | PID:%11")
            .arg(lineStatus)
            .arg(leftPwm, 0, 'f', 1)
            .arg(rightPwm, 0, 'f', 1)
            .arg(baseSpeed, 0, 'f', 1)
            .arg(laneLeftX, 0, 'f', 3)
            .arg(laneRightX, 0, 'f', 3)
            .arg(errorCm, 0, 'f', 2)
            .arg(headingError, 0, 'f', 3)
            .arg(turn, 0, 'f', 3)
            .arg(pidOut, 0, 'f', 3)
            .arg(motorStatus);
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ GÖRSELLEŞTİRME VERİLERİNİ GÜNCELLE (her zaman)
    // ═══════════════════════════════════════════════════════════════
    m_currentPidError = errorCm;
    m_currentPidOutput = pidOut;
    m_currentBaseSpeed = baseSpeed;
    m_currentLeftSpeed = leftPwm;  // Hesaplanan değer (motor çalışmasa da göster)
    m_currentRightSpeed = rightPwm;
    m_currentLineCenterX = laneCenter;
    m_currentTargetCenter = laneCenter;
    m_currentDynamicCenter = 0.5;
    m_currentHeadingError = headingError;
    m_currentTotalError = totalError;
    m_currentTurnRatio = turn;
    // Mode: tek çizgi durumunu da göster (otonom değilse READY ekle)
    QString baseMode;
    if (lineStatus == QStringLiteral("LEFT_ONLY")) {
        baseMode = "LEFT";
    } else if (lineStatus == QStringLiteral("RIGHT_ONLY")) {
        baseMode = "RIGHT";
    } else {
        baseMode = "DUAL";
    }
    if (m_autonomousMode) {
        m_currentMode = "ARC-" + baseMode;
        setGuidanceMode(QStringLiteral("ARC-") + baseMode);
    } else {
        m_currentMode = "READY-" + baseMode;  // Manuel modda hazır
        setGuidanceMode(QStringLiteral("READY"));
    }
    emit pidDataChanged();
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
    m_lastSeenSide = LineSide::Unknown;
    m_searchDir = QStringLiteral("left");
    m_lastMode.clear();
    m_pidIntegral = 0.0;
    m_pidLastMs = nowMs;
    m_pidPrevError = 0.0;
    m_calibrationDone = false;
    m_calibrationFrameCount = 0;
    m_calibrationSum = 0.0;
    m_referenceLaneWidth = 0.0;
    m_pixelPerCm = 0.0;
}

void RaspiControlClient::resetPidController()
{
    m_pidLastError = 0.0;
    m_pidIntegral = 0.0;
    m_pidLastMs = m_commandTimer.elapsed();
}

// ═══════════════════════════════════════════════════════════════
// ✅ YOLO MASK'DEN LANE CENTERS HESAPLAMA (main.py'deki gibi)
// ═══════════════════════════════════════════════════════════════
void RaspiControlClient::extractLaneCentersFromMask(
    const QVariantList &masks,
    QVector<double> &leftCenters,
    QVector<double> &rightCenters)
{
    leftCenters.clear();
    rightCenters.clear();

    for (const QVariant &item : masks) {
        const QVariantMap mask = item.toMap();
        if (mask.isEmpty()) continue;

        double x = mask.value(QStringLiteral("x")).toDouble();
        double w = mask.value(QStringLiteral("w")).toDouble();
        double centerX = x + w * 0.5;
        double score = mask.value(QStringLiteral("score")).toDouble();

        if (score < kDetectionScoreThreshold) continue;

        // Sol/Sağ ayrımı (0.5 merkez)
        if (centerX < 0.5) {
            leftCenters.append(centerX);
        } else {
            rightCenters.append(centerX);
        }
    }

    std::sort(leftCenters.begin(), leftCenters.end());
    std::sort(rightCenters.begin(), rightCenters.end());
}

// ═══════════════════════════════════════════════════════════════
// ✅ HEADING ERROR HESAPLAMA (çizgi eğimi)
// ═══════════════════════════════════════════════════════════════
double RaspiControlClient::computeHeadingError(
    const QVariantList &masks,
    int imageWidth,
    int imageHeight)
{
    // ROI bölgesindeki noktaları topla
    QVector<double> xs, ys;

    for (const QVariant &item : masks) {
        const QVariantMap mask = item.toMap();
        if (mask.isEmpty()) continue;

        double x = mask.value(QStringLiteral("x")).toDouble();
        double y = mask.value(QStringLiteral("y")).toDouble();
        double w = mask.value(QStringLiteral("w")).toDouble();
        double h = mask.value(QStringLiteral("h")).toDouble();
        double score = mask.value(QStringLiteral("score")).toDouble();

        if (score < kDetectionScoreThreshold) continue;

        // ROI kontrol (alt %50)
        double pixelY = y * imageHeight;
        if (pixelY < imageHeight * kRoiTopRatio) continue;

        xs.append((x + w * 0.5) * imageWidth);
        ys.append((y + h * 0.5) * imageHeight);
    }

    if (xs.size() < 10) return 0.0;

    // Linear fit (en az kareler)
    double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
    int n = xs.size();

    for (int i = 0; i < n; ++i) {
        sumX += xs[i];
        sumY += ys[i];
        sumXY += xs[i] * ys[i];
        sumX2 += xs[i] * xs[i];
    }

    double denom = n * sumX2 - sumX * sumX;
    if (qAbs(denom) < 1e-10) return 0.0;

    double slope = (n * sumXY - sumX * sumY) / denom;
    return -std::atan(slope);  // Radyan cinsinden heading error
}

// ═══════════════════════════════════════════════════════════════
// ✅ ARAMA MODU (çizgi kaybolduğunda)
// ═══════════════════════════════════════════════════════════════
void RaspiControlClient::handleSearchMode(qint64 nowMs)
{
    qint64 elapsedMs = nowMs - m_lastLineSeenMs;
    QString cmd;
    QString mode;

    if (elapsedMs < kNoLineTimeoutMs) {
        // Kısa süre: düz git
        double slowSpeed = kBaseSpeed * 0.5;
        cmd = QStringLiteral("DIFF,%1,%2").arg(slowSpeed, 0, 'f', 1).arg(slowSpeed, 0, 'f', 1);
        mode = QStringLiteral("SEARCH-FWD");
    } else if (elapsedMs < kNoLineTimeoutMs * 3) {
        // Arama: son görülen yöne dön
        bool searchLeft = (m_lastSeenSide == LineSide::Left);

        if (searchLeft) {
            cmd = QStringLiteral("DIFF,%1,%2").arg(kSearchTurnSpeed).arg(-kSearchTurnSpeed);
        } else {
            cmd = QStringLiteral("DIFF,%1,%2").arg(-kSearchTurnSpeed).arg(kSearchTurnSpeed);
        }
        mode = QStringLiteral("SEARCH-TURN");
    } else {
        // Uzun süre: dur
        cmd = QStringLiteral("S");
        mode = QStringLiteral("STOP");
    }

    // Sadece otonom modda motor komutu gönder
    if (m_autonomousMode) {
        dispatchAutonomousCommand(cmd, cmd != QLatin1String("S"));
        setGuidanceMode(mode);
    } else {
        setGuidanceMode(QStringLiteral("NO-LINE"));  // Manuel modda çizgi yok
    }

    m_currentMode = (m_lastSeenSide == LineSide::Left) ? "SEARCH-LEFT" : "SEARCH-RIGHT";
    emit pidDataChanged();

    if (m_debugEnabled) {
        QString motorStatus = m_autonomousMode ? "AUTO" : "MANUAL";
        qDebug().noquote() << QStringLiteral("[SEARCH-%4] %1ms | Last: %2 | Cmd: %3")
            .arg(elapsedMs)
            .arg(m_lastSeenSide == LineSide::Left ? "L" : "R")
            .arg(cmd)
            .arg(motorStatus);
    }
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
    // Tüm tespitleri topla (cx, score)
    QVector<QPair<double, double>> detections; // (cx, score)
    detections.reserve(boxes.size());

    for (const QVariant &item : boxes) {
        const QVariantMap box = item.toMap();
        if (box.isEmpty()) continue;

        const double score = box.value(QStringLiteral("score")).toDouble();
        if (score < kDetectionScoreThreshold) continue;

        const double x = box.value(QStringLiteral("x")).toDouble();
        const double w = box.value(QStringLiteral("w")).toDouble();
        const double cx = qBound(0.0, x + (w * 0.5), 1.0);
        detections.append(qMakePair(cx, score));
    }

    if (detections.isEmpty())
        return {};

    // cx'e göre sırala
    std::sort(detections.begin(), detections.end(),
        [](const QPair<double,double> &a, const QPair<double,double> &b) {
            return a.first < b.first;
        });

    // Yakın tespitleri birleştir (clustering)
    QVector<QPair<double, double>> clusters; // (weightedCx, totalScore)
    double curCx    = detections[0].first;
    double curScore = detections[0].second;
    double sumWeight = curScore;
    double sumCx   = curCx * curScore;

    for (int i = 1; i < detections.size(); ++i) {
        const double cx = detections[i].first;
        const double sc = detections[i].second;

        if (cx - curCx < kLineMergeThreshold) {
            // Aynı cluster
            sumWeight += sc;
            sumCx     += cx * sc;
            curCx      = cx;  // sonraki karşılaştırma için
        } else {
            // Yeni cluster
            clusters.append(qMakePair(sumCx / sumWeight, sumWeight));
            curCx    = cx;
            curScore = sc;
            sumWeight = sc;
            sumCx     = cx * sc;
        }
    }
    clusters.append(qMakePair(sumCx / sumWeight, sumWeight));

    // En fazla 2 cluster (sol ve sağ)
    if (clusters.size() > 2) {
        // En yüksek score'a sahip 2 cluster'ı tut
        std::sort(clusters.begin(), clusters.end(),
            [](const QPair<double,double> &a, const QPair<double,double> &b) {
                return a.second > b.second;
            });
        clusters.resize(2);
    }

    QVector<double> centers;
    centers.reserve(clusters.size());
    for (const auto &c : clusters)
        centers.append(c.first);

    std::sort(centers.begin(), centers.end());
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
        return QStringLiteral("AUTO");
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
