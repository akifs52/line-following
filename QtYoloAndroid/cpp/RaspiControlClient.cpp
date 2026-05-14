#include "RaspiControlClient.h"

#include <QVariantMap>

#include <algorithm>
#include <cmath>  // ✅ std::tanh ve std::atan için gerekli

namespace {
// Temel zamanlama sabitleri
constexpr qint64 kAutonomousWatchdogIntervalMs = 80;
constexpr qint64 kDetectionFeedTimeoutMs = 350;
constexpr double kDetectionScoreThreshold = 0.30;
constexpr double kLineMergeThreshold = 0.30;

// ═══════════════════════════════════════════════════════════════
// ✅ LOCAL CONSTANTS (not in header)
// ═══════════════════════════════════════════════════════════════
// Wall-following: kWallTargetCm header'da tanımlı (12.5 cm)
double clampErrorCm(double e) { return qBound(-15.0, e, 15.0); } // ECM clamp
constexpr qint64 kNoLineTimeoutMs = 500;   // Çizgi kaybı timeout
constexpr double kSearchTurnSpeed = 35.0;  // Arama dönüş hızı
} // namespace

RaspiControlClient::RaspiControlClient(QObject *parent)
    : QObject(parent)
{
    connect(&m_socket, &QTcpSocket::connected, this, &RaspiControlClient::onConnected);
    connect(&m_socket, &QTcpSocket::disconnected, this, &RaspiControlClient::onDisconnected);
    connect(&m_socket, &QTcpSocket::errorOccurred, this, &RaspiControlClient::onErrorOccurred);
    connect(&m_autonomousWatchdog, &QTimer::timeout, this, &RaspiControlClient::onAutonomousWatchdog);
    connect(&m_commandBufferTimer, &QTimer::timeout, this, &RaspiControlClient::onCommandBufferTimeout);
    m_commandBufferTimer.setSingleShot(true);

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
        m_pixelPerCm = 0.0;  // Yeni oturumda yeniden tahmin edilecek
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
    // ✅ TEK ÇİZGİ TESPİTİ
    // ═══════════════════════════════════════════════════════════════
    const double frameWidth = std::max(1.0, primaryDetection.value(QStringLiteral("frameWidth")).toDouble());
    const double laneLeftX = primaryDetection.value(QStringLiteral("laneLeftX")).toDouble();
    const double laneRightX = primaryDetection.value(QStringLiteral("laneRightX")).toDouble();

    const bool leftDetected = (laneLeftX >= 0.0);
    const bool rightDetected = (laneRightX >= 0.0);

    // Hangi çizgiyi görüyorsak onu kullan (sol öncelikli)
    double lineX = -1.0;          // Normalize [0,1] çizgi pozisyonu
    bool lineIsLeft = false;      // Çizgi sol tarafta mı?

    if (leftDetected) {
        lineX = laneLeftX;
        lineIsLeft = true;
    } else if (rightDetected) {
        lineX = laneRightX;
        lineIsLeft = false;
    } else {
        handleSearchMode(nowMs);
        return;
    }

    // Geçerlilik kontrolü
    if (lineX <= 0.02 || lineX >= 0.98) {
        handleSearchMode(nowMs);
        return;
    }

    m_lastLineSeenMs = nowMs;
    m_lastSeenSide = lineIsLeft ? LineSide::Left : LineSide::Right;

    // ═══════════════════════════════════════════════════════════════
    // ✅ pixelPerCm TAHMİNİ (varsayılan: kamera ~1.4× yol genişliği görür)
    // Bloklama YOK - ilk frame'den itibaren çalışır
    // ═══════════════════════════════════════════════════════════════
    if (m_pixelPerCm <= 1e-6) {
        // Varsayılan tahmin: kamera ~38cm genişlik görüyor (27cm yol + kenarlar)
        constexpr double kCameraViewWidthCm = 31.0;
        m_pixelPerCm = frameWidth / kCameraViewWidthCm;
        if (m_debugEnabled) {
            qDebug().noquote() << QStringLiteral("[KALIB] Varsayılan px/cm: %1 (frame=%2)")
                .arg(m_pixelPerCm, 0, 'f', 2).arg(frameWidth, 0, 'f', 0);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ MESAFE ÖLÇÜMÜ (cm cinsinden)
    // ═══════════════════════════════════════════════════════════════
    const double robotCenterPx = 0.5 * frameWidth;
    const double linePx = lineX * frameWidth;
    double distanceCm;

    if (lineIsLeft) {
        distanceCm = (robotCenterPx - linePx) / m_pixelPerCm;  // Sol çizgiden uzaklık
    } else {
        distanceCm = (linePx - robotCenterPx) / m_pixelPerCm;  // Sağ çizgiden uzaklık
    }

    // Mesafe negatifse çizgiyi geçmişiz demek → acil kaç
    distanceCm = std::max(0.0, distanceCm);

    // ═══════════════════════════════════════════════════════════════
    // ✅ ORANTILI DİREKSİYON (PID YOK - saf reactive)
    // errorCm: hedeften sapma (pozitif = çok yakın, kaç)
    // distanceCm < 5cm → tehlike, sert dönüş
    // distanceCm ≈ 12.5cm → hata ≈ 0, düz git
    // distanceCm > 12.5cm → hafif çizgiye doğru gel
    // ═══════════════════════════════════════════════════════════════
    double errorCm = kWallTargetCm - distanceCm;
    // Pozitif error = çizgiye çok yakınız → kaç
    // Negatif error = çizgiden çok uzağız → yaklaş

    // Tehlike bölgesi: 5cm altında agresif boost
    double steerMultiplier = 1.0;
    if (distanceCm < kDangerZoneCm) {
        // 5cm→1.0x, 0cm→3.0x (lineer boost)
        steerMultiplier = 1.0 + 2.0 * (1.0 - distanceCm / kDangerZoneCm);
    }

    // Dönüş miktarı: mesafe hatası × gain × tehlike çarpanı
    double turn = kSteerGain * errorCm * steerMultiplier;

    // Sağ çizgi referanssa işareti ters çevir
    if (!lineIsLeft) {
        turn = -turn;
    }

    // tanh ile [-1, +1] arasına sınırla (yumuşak satürasyon)
    turn = std::tanh(turn);

    // ═══════════════════════════════════════════════════════════════
    // ✅ HIZ: Tehlike bölgesinde yavaşla
    // ═══════════════════════════════════════════════════════════════
    double baseSpeed = kBaseSpeed;
    if (distanceCm < kDangerZoneCm) {
        // 5cm→full speed, 0cm→%75 speed (eskiden %60'tı)
        double slowFactor = 0.75 + 0.25 * (distanceCm / kDangerZoneCm);
        baseSpeed *= slowFactor;
    }

    // 5. Dönüş hızını korumak için turn-based speed boost
    // turn değeri 0.5'ten büyükse hafif hız arttır
    double turnMagnitude = std::abs(turn);
    if (turnMagnitude > 0.3) {
        baseSpeed *= (1.0 + turnMagnitude * 0.15);  // %15'e kadar boost
    }

    // 6. Düz gidişlerde ekstra hız (turn < 0.15 ise)
    if (turnMagnitude < 0.15) {
        baseSpeed *= 1.1;  // %10 ekstra hız
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ PWM HESAPLAMA (Motor yönü ters çevrildi)
    // turn pozitif → sola dön (sol yavaş, sağ hızlı)
    // ═══════════════════════════════════════════════════════════════
    double leftPwm  = baseSpeed * (1.0 - turn);
    double rightPwm = baseSpeed * (1.0 + turn);

    leftPwm  = qBound(kMinPwm, leftPwm,  kMaxPwm);
    rightPwm = qBound(kMinPwm, rightPwm, kMaxPwm);

    // ═══════════════════════════════════════════════════════════════
    // ✅ KOMUT GÖNDER
    // ═══════════════════════════════════════════════════════════════
    if (m_autonomousMode) {
        QString cmd = QStringLiteral("DIFF,%1,%2").arg(leftPwm, 0, 'f', 1).arg(rightPwm, 0, 'f', 1);
        dispatchAutonomousCommand(cmd, true);
    }

    // Debug
    if (m_debugEnabled) {
        qDebug().noquote() << QStringLiteral(
            "[LINE-%1] Dist:%2cm | Err:%3 | Turn:%4 | L:%5 R:%6 | Spd:%7 | %8")
            .arg(lineIsLeft ? "L" : "R")
            .arg(distanceCm, 0, 'f', 1)
            .arg(errorCm, 0, 'f', 1)
            .arg(turn, 0, 'f', 3)
            .arg(leftPwm, 0, 'f', 1)
            .arg(rightPwm, 0, 'f', 1)
            .arg(baseSpeed, 0, 'f', 1)
            .arg(distanceCm < kDangerZoneCm ? "DANGER!" : "ok");
    }

    // ═══════════════════════════════════════════════════════════════
    // ✅ GÖRSELLEŞTİRME
    // ═══════════════════════════════════════════════════════════════
    m_currentPidError = errorCm;
    m_currentPidOutput = turn;
    m_currentBaseSpeed = baseSpeed;
    m_currentLeftSpeed = leftPwm;
    m_currentRightSpeed = rightPwm;
    m_currentLineCenterX = lineX;
    m_currentTargetCenter = 0.5;
    m_currentWallDistance = distanceCm;
    m_currentHeadingError = 0.0;
    m_currentTotalError = errorCm;
    m_currentTurnRatio = turn;

    if (m_autonomousMode) {
        m_currentMode = distanceCm < kDangerZoneCm ? "DANGER" : "TRACK";
        setGuidanceMode(QStringLiteral("LINE-") + (lineIsLeft ? "L" : "R"));
    } else {
        m_currentMode = "READY";
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
// ✅ ARAMA MODU (çizgi kaybolduğunda)
// ═══════════════════════════════════════════════════════════════
void RaspiControlClient::handleSearchMode(qint64 nowMs)
{
    qint64 elapsedMs = nowMs - m_lastLineSeenMs;
    QString cmd;
    QString mode;

    if (elapsedMs < kNoLineTimeoutMs) {
        // Kısa süre: düz git
        double slowSpeed = kBaseSpeed * 0.7;  // 0.5 → 0.7 (daha hızlı düz git)
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
    if (!sendRawCommand(command, throttle)) {
        return false;
    }

    const qint64 nowMs = m_commandTimer.elapsed();
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

void RaspiControlClient::onCommandBufferTimeout()
{
    if (!m_commandBuffer.isEmpty()) {
        sendRawCommandImpl(m_commandBuffer);
        m_commandBuffer.clear();
    }
}

bool RaspiControlClient::sendRawCommandImpl(const QString &command)
{
    if (!connected()) {
        return false;
    }
    const QByteArray data = (command + "\n").toUtf8();
    return m_socket.write(data) == data.size();
}

bool RaspiControlClient::sendRawCommand(const QString &command, bool throttle)
{
    if (!connected()) {
        return false;
    }

    const qint64 nowMs = m_commandTimer.elapsed();

    // 1️⃣ Buffer: rate-limit dolmadıysa son komutu biriktir
    if (throttle) {
        const qint64 elapsedSinceLast = nowMs - m_lastSentCommandMs;
        if (elapsedSinceLast < kMinCommandIntervalMs) {
            m_commandBuffer = command;
            if (!m_commandBufferTimer.isActive()) {
                m_commandBufferTimer.start(int(kMinCommandIntervalMs - elapsedSinceLast));
            }
            return true;
        }
    }

    // 2️⃣ Deduplication: aynı komutsa gönderme
    if (command == m_lastSentCommand && (nowMs - m_lastSentCommandMs) < 100) {
        if (m_debugEnabled)
            qDebug() << "[DEDUP] Komut atlandı:" << command;
        return true;
    }

    if (!sendRawCommandImpl(command))
        return false;

    m_lastSentCommand = command;
    m_lastSentCommandMs = nowMs;
    return true;
}

