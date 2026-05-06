#include "YoloEngine.h"

#include <QFile>
#include <QDebug>
#include <QVariantMap>
#include <QtConcurrent/QtConcurrentRun>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <optional>
#include <limits>

// NCNN includes for all platforms with GPU support
#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
#include <ncnn/datareader.h>
#include <ncnn/gpu.h>
#include <ncnn/layer.h>
#endif

namespace {
constexpr float kMinThreshold = 0.001f;
constexpr float kMaxThreshold = 0.99f;
constexpr float kMaskThreshold = 0.50f;
constexpr double kRoiTopRatio = 0.35;
constexpr int kPolygonSampleBins = 24;

// NCNN constants for all platforms
#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
constexpr int kInputSize = 640;
constexpr float kNmsThreshold = 0.45f;
constexpr float kNormVals[3] = {1.f / 255.f, 1.f / 255.f, 1.f / 255.f};
constexpr int kModelRetryIntervalMs = 1500;
constexpr int kMaxModelRetryAttempts = 10;
constexpr int kMaxCandidateDetections = 4;
constexpr int kMaxOverlayDetections = 2;
constexpr float kMinLaneGapNorm = 0.08f;

inline float sigmoidf(float value)
{
    return 1.0f / (1.0f + std::exp(-value));
}

void populateMaskGeometry(
    YoloEngine::Detection &det,
    const QVector<float> &maskCoeffs,
    const ncnn::Mat &prototypes,
    int srcW,
    int srcH,
    int padLeft,
    int padTop,
    float scale)
{
    det.frameWidth = srcW;
    det.frameHeight = srcH;
    det.roiTopRatio = float(kRoiTopRatio);

    if (maskCoeffs.isEmpty() || prototypes.dims != 3 || prototypes.c <= 0 || prototypes.w <= 0 || prototypes.h <= 0) {
        return;
    }

    const int protoW = prototypes.w;
    const int protoH = prototypes.h;
    const int coeffCount = (std::min)(int(maskCoeffs.size()), prototypes.c);
    if (coeffCount <= 0) {
        return;
    }

    QVector<float> logits(protoW * protoH, 0.0f);
    for (int c = 0; c < coeffCount; ++c) {
        const float coeff = maskCoeffs[c];
        const ncnn::Mat channel = prototypes.channel(c);
        for (int y = 0; y < protoH; ++y) {
            const float *srcRow = channel.row(y);
            float *dstRow = logits.data() + (y * protoW);
            for (int x = 0; x < protoW; ++x) {
                dstRow[x] += coeff * srcRow[x];
            }
        }
    }

    const double roiTopPx = double(srcH) * kRoiTopRatio;

    const double boxLeft = (std::max)(0.0, det.rect.left() - 4.0);
    const double boxTop = (std::max)(0.0, det.rect.top() - 4.0);
    const double boxRight = (std::min)(double(srcW - 1), det.rect.right() + 4.0);
    const double boxBottom = (std::min)(double(srcH - 1), det.rect.bottom() + 4.0);
    if (boxRight <= boxLeft || boxBottom <= boxTop) {
        return;
    }

    QVector<double> minXs(kPolygonSampleBins, std::numeric_limits<double>::infinity());
    QVector<double> maxXs(kPolygonSampleBins, -std::numeric_limits<double>::infinity());
    QVector<double> xSums(kPolygonSampleBins, 0.0);
    QVector<double> ySums(kPolygonSampleBins, 0.0);
    QVector<int> sampleCounts(kPolygonSampleBins, 0);

    double sumX = 0.0;
    double sumY = 0.0;
    double sumXY = 0.0;
    double sumX2 = 0.0;
    int fitCount = 0;

    for (int y = 0; y < protoH; ++y) {
        for (int x = 0; x < protoW; ++x) {
            const float probability = sigmoidf(logits[y * protoW + x]);
            if (probability < kMaskThreshold) {
                continue;
            }

            const double inputX = (double(x) + 0.5) * double(kInputSize) / double(protoW);
            const double inputY = (double(y) + 0.5) * double(kInputSize) / double(protoH);
            const double srcX = (inputX - double(padLeft)) / double(scale);
            const double srcY = (inputY - double(padTop)) / double(scale);

            if (srcX < 0.0 || srcY < 0.0 || srcX >= double(srcW) || srcY >= double(srcH)) {
                continue;
            }
            if (srcX < boxLeft || srcX > boxRight || srcY < boxTop || srcY > boxBottom) {
                continue;
            }

            const double xNorm = srcX / double(srcW);
            const double yNorm = srcY / double(srcH);
            const int bin = (std::clamp)(int(yNorm * double(kPolygonSampleBins)), 0, kPolygonSampleBins - 1);
            minXs[bin] = (std::min)(minXs[bin], xNorm);
            maxXs[bin] = (std::max)(maxXs[bin], xNorm);
            xSums[bin] += xNorm;
            ySums[bin] += yNorm;
            sampleCounts[bin] += 1;

            if (srcY >= roiTopPx) {
                sumX += srcX;
                sumY += srcY;
                sumXY += srcX * srcY;
                sumX2 += srcX * srcX;
                ++fitCount;
            }
        }
    }

    QVector<QPointF> leftBoundary;
    QVector<QPointF> rightBoundary;
    leftBoundary.reserve(kPolygonSampleBins);
    rightBoundary.reserve(kPolygonSampleBins);
    const double minRibbonHalfWidth = 3.0 / double(srcW);
    const double maxRibbonHalfWidth = 14.0 / double(srcW);

    for (int bin = 0; bin < kPolygonSampleBins; ++bin) {
        if (sampleCounts[bin] == 0
            || !std::isfinite(minXs[bin])
            || !std::isfinite(maxXs[bin])
            || maxXs[bin] < minXs[bin]) {
            continue;
        }

        const double yNorm = ySums[bin] / double(sampleCounts[bin]);
        const double meanX = xSums[bin] / double(sampleCounts[bin]);
        const double spread = maxXs[bin] - minXs[bin];
        const double ribbonHalfWidth = (std::clamp)(spread * 0.35, minRibbonHalfWidth, maxRibbonHalfWidth);
        leftBoundary.push_back(QPointF((std::clamp)(meanX - ribbonHalfWidth, 0.0, 1.0), yNorm));
        rightBoundary.push_front(QPointF((std::clamp)(meanX + ribbonHalfWidth, 0.0, 1.0), yNorm));
    }

    if (leftBoundary.size() >= 2 && rightBoundary.size() >= 2) {
        det.polygon = leftBoundary;
        det.polygon += rightBoundary;
    }

    if (fitCount > 0) {
        det.lineCenterX = float((sumX / double(fitCount)) / double(srcW));
    } else if (srcW > 0) {
        det.lineCenterX = float(det.rect.center().x() / double(srcW));
    }

    if (fitCount > 10) {
        const double denom = double(fitCount) * sumX2 - sumX * sumX;
        if (std::abs(denom) > 1e-6) {
            const double slope = (double(fitCount) * sumXY - sumX * sumY) / denom;
            det.headingError = float(-std::atan(slope));
        }
    }
}

float detectionCenterX(const YoloEngine::Detection &det)
{
    if (std::isfinite(det.lineCenterX) && det.lineCenterX > 0.0f && det.lineCenterX < 1.0f) {
        return det.lineCenterX;
    }
    if (det.frameWidth > 0) {
        return float(det.rect.center().x() / double(det.frameWidth));
    }
    return -1.0f;
}

void populateCombinedLaneMetrics(QVector<YoloEngine::Detection> &detections)
{
    struct LineSample {
        int index = -1;
        float centerX = -1.0f;
        float heading = 0.0f;
        float score = 0.0f;
    };

    QVector<LineSample> leftSamples, rightSamples;
    leftSamples.reserve(detections.size());
    rightSamples.reserve(detections.size());

    for (int index = 0; index < detections.size(); ++index) {
        const YoloEngine::Detection &det = detections[index];
        const float centerX = detectionCenterX(det);
        if (!std::isfinite(centerX) || centerX <= 0.0f || centerX >= 1.0f) {
            continue;
        }

        LineSample sample;
        sample.index = index;
        sample.centerX = centerX;
        sample.heading = det.headingError;
        sample.score = det.score;

        if (centerX < 0.5f)
            leftSamples.push_back(sample);
        else
            rightSamples.push_back(sample);
    }

    // En iyi tespiti seç (en yüksek score, aynı taraftan birer tane)
    auto pickBest = [](QVector<LineSample> &samples) -> std::optional<LineSample> {
        if (samples.isEmpty()) return std::nullopt;
        auto best = std::max_element(samples.begin(), samples.end(),
            [](const LineSample &a, const LineSample &b) { return a.score < b.score; });
        return *best;
    };

    auto leftBest  = pickBest(leftSamples);
    auto rightBest = pickBest(rightSamples);

    float laneLeftX = -1.0f, laneRightX = -1.0f, laneCenter = 0.5f, combinedHeading = 0.0f;

    if (leftBest && rightBest) {
        // ✅ İKİ ÇİZGİ (her taraftan biri)
        laneLeftX  = leftBest->centerX;
        laneRightX = rightBest->centerX;

        if ((laneRightX - laneLeftX) < kMinLaneGapNorm) {
            // Çok yakınsa sanal genişlik ekle
            const float virtualLaneWidth = 0.25f;
            laneLeftX  = laneLeftX - virtualLaneWidth * 0.5f;
            laneRightX = laneRightX + virtualLaneWidth * 0.5f;
        }

        float headingSum = 0.0f;
        int headingCount = 0;
        if (std::isfinite(leftBest->heading)) {
            headingSum += leftBest->heading;
            ++headingCount;
        }
        if (std::isfinite(rightBest->heading)) {
            headingSum += rightBest->heading;
            ++headingCount;
        }
        combinedHeading = headingCount > 0 ? headingSum / float(headingCount) : 0.0f;
        laneCenter = (laneLeftX + laneRightX) * 0.5f;
    }
    else if (leftBest || rightBest) {
        // ✅ TEK ÇİZGİ: Sanal ikinci çizgi
        const LineSample &only = leftBest ? leftBest.value() : rightBest.value();
        const float virtualLaneWidth = 0.25f;

        if (only.centerX < 0.5f) {
            laneLeftX  = only.centerX;
            laneRightX = only.centerX + virtualLaneWidth;
        } else {
            laneRightX = only.centerX;
            laneLeftX  = only.centerX - virtualLaneWidth;
        }
        laneCenter = (laneLeftX + laneRightX) * 0.5f;
        combinedHeading = std::isfinite(only.heading) ? only.heading : 0.0f;
    }
    else {
        return;  // Hiç çizgi yok
    }

    // Tüm detection'lara metrics ata
    for (YoloEngine::Detection &det : detections) {
        det.laneLeftX = laneLeftX;
        det.laneRightX = laneRightX;
        det.laneCenterX = laneCenter;
        det.hasLaneMetrics = true;
        det.headingError = combinedHeading;
    }
}

QVector<YoloEngine::Detection> selectLaneDetections(const QVector<YoloEngine::Detection> &detections)
{
    if (detections.size() <= kMaxOverlayDetections) {
        return detections;
    }

    struct RankedDetection {
        int index = -1;
        float centerX = -1.0f;
        float score = 0.0f;
    };

    QVector<RankedDetection> left, right;
    left.reserve(detections.size());
    right.reserve(detections.size());

    for (int index = 0; index < detections.size(); ++index) {
        RankedDetection item;
        item.index = index;
        item.centerX = detectionCenterX(detections[index]);
        item.score = detections[index].score;
        if (item.centerX < 0.5f)
            left.push_back(item);
        else
            right.push_back(item);
    }

    auto pickBest = [](QVector<RankedDetection> &samples) -> std::optional<RankedDetection> {
        if (samples.isEmpty()) return std::nullopt;
        auto best = std::max_element(samples.begin(), samples.end(),
            [](const RankedDetection &a, const RankedDetection &b) { return a.score < b.score; });
        return *best;
    };

    QVector<YoloEngine::Detection> selected;
    selected.reserve(kMaxOverlayDetections);
    auto leftBest = pickBest(left);
    auto rightBest = pickBest(right);
    if (leftBest) selected.push_back(detections[leftBest->index]);
    if (rightBest) selected.push_back(detections[rightBest->index]);
    return selected;
}
#endif
} // namespace

YoloEngine::YoloEngine(QObject *parent)
    : QObject(parent)
{
    m_runtime.start();
    connect(&m_futureWatcher, &QFutureWatcher<InferenceResult>::finished, this, &YoloEngine::finishInference);
#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
    m_modelRetryTimer.setInterval(kModelRetryIntervalMs);
    m_modelRetryTimer.setSingleShot(false);
    connect(&m_modelRetryTimer, &QTimer::timeout, this, [this] {
        if (m_modelLoaded || m_modelRetryAttempts >= kMaxModelRetryAttempts) {
            m_modelRetryTimer.stop();
            return;
        }
        ++m_modelRetryAttempts;
        updateModelLoadedState();
    });
#endif
    updateModelLoadedState();
}

YoloEngine::~YoloEngine()
{
    disconnect(&m_futureWatcher, nullptr, this, nullptr);
    if (m_futureWatcher.isRunning()) {
        m_futureWatcher.waitForFinished();
    }
}

bool YoloEngine::enabled() const
{
    return m_enabled;
}

void YoloEngine::setEnabled(bool enabled)
{
    if (m_enabled == enabled) {
        return;
    }

    m_enabled = enabled;
    emit enabledChanged();

    if (!m_enabled) {
        m_pendingFrame = QImage();
        clearDetections();
    }
}

float YoloEngine::scoreThreshold() const
{
    return m_scoreThreshold;
}

void YoloEngine::setScoreThreshold(float threshold)
{
    const float clamped = qBound(kMinThreshold, threshold, kMaxThreshold);
    if (qFuzzyCompare(clamped, m_scoreThreshold)) {
        return;
    }

    m_scoreThreshold = clamped;
    emit scoreThresholdChanged();
}

double YoloEngine::fps() const
{
    return m_fps;
}

bool YoloEngine::modelLoaded() const
{
    return m_modelLoaded;
}

QString YoloEngine::modelStatus() const
{
    return m_modelStatus;
}

void YoloEngine::setModelStatus(const QString &status)
{
    if (status == m_modelStatus) {
        return;
    }
    m_modelStatus = status;
    emit modelStatusChanged();
}

void YoloEngine::clearDetections()
{
    emit detectionsReady(QVariantList());
}

void YoloEngine::processFrame(const QImage &frame)
{
    if (!m_enabled || frame.isNull()) {
        return;
    }

    if (!m_modelLoaded) {
        return;
    }

    if (m_inferenceBusy) {
        m_pendingFrame = frame;
        return;
    }

    startInference(frame);
}

QVariantList YoloEngine::toVariantList(const QVector<Detection> &detections, const QSize &frameSize) const
{
    QVariantList boxes;
    if (frameSize.width() <= 0 || frameSize.height() <= 0) {
        return boxes;
    }

    const qreal fw = qreal(frameSize.width());
    const qreal fh = qreal(frameSize.height());

    boxes.reserve(detections.size());
    for (const Detection &det : detections) {
        QVariantMap box;
        box.insert(QStringLiteral("x"), det.rect.x() / fw);
        box.insert(QStringLiteral("y"), det.rect.y() / fh);
        box.insert(QStringLiteral("w"), det.rect.width() / fw);
        box.insert(QStringLiteral("h"), det.rect.height() / fh);
        box.insert(QStringLiteral("score"), det.score);
        box.insert(QStringLiteral("label"), m_classNames.value(det.label, QStringLiteral("line")));
        box.insert(QStringLiteral("color"), QStringLiteral("#4ade80"));
        box.insert(QStringLiteral("lineCenterX"), det.lineCenterX);

        QVariantList points;
        points.reserve(det.polygon.size());
        for (const QPointF &point : det.polygon) {
            QVariantMap pointMap;
            pointMap.insert(QStringLiteral("x"), qBound(0.0, point.x(), 1.0));
            pointMap.insert(QStringLiteral("y"), qBound(0.0, point.y(), 1.0));
            points.push_back(pointMap);
        }

        box.insert(QStringLiteral("points"), points);
        box.insert(QStringLiteral("laneLeftX"), det.laneLeftX);
        box.insert(QStringLiteral("laneRightX"), det.laneRightX);
        box.insert(QStringLiteral("laneCenterX"), det.laneCenterX);
        box.insert(QStringLiteral("headingError"), det.headingError);
        box.insert(QStringLiteral("roiTopRatio"), det.roiTopRatio);
        box.insert(QStringLiteral("hasLaneMetrics"), det.hasLaneMetrics);
        box.insert(QStringLiteral("frameWidth"), det.frameWidth > 0 ? det.frameWidth : frameSize.width());
        box.insert(QStringLiteral("frameHeight"), det.frameHeight > 0 ? det.frameHeight : frameSize.height());
        boxes.push_back(box);
    }

    return boxes;
}

void YoloEngine::updateModelLoadedState()
{
    auto hasPayload = [](const QString &resourcePath) {
        QFile file(resourcePath);
        if (!file.open(QIODevice::ReadOnly)) {
            qWarning() << "asset open failed:" << resourcePath << file.errorString();
            return false;
        }
        const bool ok = !file.peek(1).isEmpty();
        if (!ok) {
            qWarning() << "asset empty:" << resourcePath;
        }
        return ok;
    };

    const bool hasAssets = hasPayload(QStringLiteral(":/assets/yolo11.param"))
        && hasPayload(QStringLiteral(":/assets/yolo11.bin"));

// Load NCNN model on all platforms (Android, iOS, macOS, Windows with GPU support)
    const bool loaded = hasAssets && ensureModelLoaded();
    if (!loaded && hasAssets) {
        qWarning() << "Model assets found but NCNN loading failed:" << m_lastLoadError;
    }

    if (!hasAssets) {
        setModelStatus(QStringLiteral("Model assets: missing"));
    } else if (loaded) {
        setModelStatus(QStringLiteral("Model assets: ready (%1)")
                           .arg(m_usingVulkan ? QStringLiteral("GPU") : QStringLiteral("CPU")));
    } else {
        const QString errorSuffix = m_lastLoadError.isEmpty()
            ? QString()
            : QStringLiteral(" (%1)").arg(m_lastLoadError);
        setModelStatus(QStringLiteral("Model load failed%1").arg(errorSuffix));
    }

    if (!loaded) {
        qWarning() << "model not ready; hasAssets=" << hasAssets << m_lastLoadError;
    }

#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
    if (loaded) {
        m_modelRetryTimer.stop();
    } else if (!m_modelRetryTimer.isActive() && m_modelRetryAttempts < kMaxModelRetryAttempts) {
        m_modelRetryTimer.start();
    }
#endif

    if (loaded == m_modelLoaded) {
        return;
    }

    m_modelLoaded = loaded;
    emit modelLoadedChanged();
}

void YoloEngine::setInferenceBusy(bool busy)
{
    if (m_inferenceBusy == busy) {
        return;
    }

    m_inferenceBusy = busy;
    emit inferenceBusyChanged(busy);
}

void YoloEngine::startInference(const QImage &frame)
{
    if (frame.isNull() || m_futureWatcher.isRunning()) {
        return;
    }

    const QImage frameCopy = frame;
    const float scoreThreshold = m_scoreThreshold;

    setInferenceBusy(true);
    m_futureWatcher.setFuture(QtConcurrent::run([this, frameCopy, scoreThreshold]() {
        InferenceResult result;
        result.frameSize = frameCopy.size();

#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
        result.detections = runNcnnInference(frameCopy, scoreThreshold);
#else
        Q_UNUSED(scoreThreshold);
#endif

        return result;
    }));
}

void YoloEngine::finishInference()
{
    const InferenceResult result = m_futureWatcher.result();
    setInferenceBusy(false);

    if (m_enabled) {
        emit detectionsReady(toVariantList(result.detections, result.frameSize));
    }

    const qint64 nowMs = m_runtime.elapsed();
    if (m_lastFrameMs > 0) {
        const qreal deltaMs = qreal(nowMs - m_lastFrameMs);
        if (deltaMs > 0.0) {
            const qreal instantFps = 1000.0 / deltaMs;
            const qreal nextFps = m_fps <= 0.0 ? instantFps : (m_fps * 0.85 + instantFps * 0.15);
            if (!qFuzzyCompare(nextFps + 1.0, m_fps + 1.0)) {
                m_fps = nextFps;
                emit fpsChanged();
            }
        }
    }
    m_lastFrameMs = nowMs;

    if (!m_enabled || m_pendingFrame.isNull()) {
        return;
    }

    const QImage nextFrame = m_pendingFrame;
    m_pendingFrame = QImage();
    startInference(nextFrame);
}

#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
bool YoloEngine::ensureModelLoaded()
{
    if (m_netInitialized) {
        return true;
    }

    QFile paramFile(QStringLiteral(":/assets/yolo11.param"));
    QFile binFile(QStringLiteral(":/assets/yolo11.bin"));
    if (!paramFile.open(QIODevice::ReadOnly) || !binFile.open(QIODevice::ReadOnly)) {
        m_lastLoadError = QStringLiteral("cannot open resource files");
        return false;
    }

    m_paramData = paramFile.readAll();
    m_modelData = binFile.readAll();
    if (m_paramData.isEmpty() || m_modelData.isEmpty()) {
        m_lastLoadError = QStringLiteral("resource files are empty");
        return false;
    }
    m_modelDataAligned.resize(m_modelData.size() + 4);
    m_usingVulkan = false;

    if (!m_paramData.endsWith('\0')) {
        m_paramData.push_back('\0');
    }

    auto tryLoad = [&](bool useVulkan, bool useFp16) {
        m_net.clear();
        m_net.opt.use_vulkan_compute = useVulkan;
        m_net.opt.use_fp16_packed = useFp16;
        m_net.opt.use_fp16_storage = useFp16;
        m_net.opt.use_fp16_arithmetic = useFp16;
        m_net.opt.num_threads = 4;

        const int paramRet = m_net.load_param_mem(m_paramData.constData());
        int modelRet = -1;
        if (paramRet == 0) {
            unsigned char *rawPtr = reinterpret_cast<unsigned char *>(m_modelDataAligned.data());
            const uintptr_t alignedAddr = (reinterpret_cast<uintptr_t>(rawPtr) + 3u) & ~uintptr_t(3u);
            unsigned char *alignedPtr = reinterpret_cast<unsigned char *>(alignedAddr);
            std::memcpy(alignedPtr, m_modelData.constData(), size_t(m_modelData.size()));
            const unsigned char *modelPtr = alignedPtr;
            ncnn::DataReaderFromMemory modelReader(modelPtr);
            modelRet = m_net.load_model(modelReader);
        }
        if (paramRet != 0 || modelRet != 0) {
            m_lastLoadError = QStringLiteral("ncnn load failed (vulkan=%1 fp16=%2 param=%3 model=%4)")
                                  .arg(useVulkan ? 1 : 0)
                                  .arg(useFp16 ? 1 : 0)
                                  .arg(paramRet)
                                  .arg(modelRet);
            qWarning() << "ncnn model load failed"
                       << "useVulkan=" << useVulkan
                       << "useFp16=" << useFp16
                       << "paramRet=" << paramRet
                       << "modelRet=" << modelRet;
            return false;
        }
        m_lastLoadError.clear();
        m_usingVulkan = useVulkan;
        qInfo() << "ncnn model loaded successfully"
                << "useVulkan=" << useVulkan
                << "useFp16=" << useFp16;
        return true;
    };

    const bool hasGpu = ncnn::get_gpu_count() > 0;
    m_netInitialized = (hasGpu && tryLoad(true, true)) || tryLoad(false, false);
    return m_netInitialized;
}

QVector<YoloEngine::Detection> YoloEngine::runNcnnInference(const QImage &frame, float scoreThreshold) const
{
    QMutexLocker locker(&m_inferenceMutex);

    QVector<Detection> detections;
    if (!m_netInitialized) {
        return detections;
    }

    const QImage rgbFrame = frame.convertToFormat(QImage::Format_RGB888);
    if (rgbFrame.isNull()) {
        return detections;
    }

    const int srcW = rgbFrame.width();
    const int srcH = rgbFrame.height();
    if (srcW <= 0 || srcH <= 0) {
        return detections;
    }

    const float scale = (std::min)(float(kInputSize) / float(srcW), float(kInputSize) / float(srcH));
    const int resizedW = (std::max)(1, int(std::round(float(srcW) * scale)));
    const int resizedH = (std::max)(1, int(std::round(float(srcH) * scale)));

    ncnn::Mat resized = ncnn::Mat::from_pixels_resize(
        rgbFrame.constBits(),
        ncnn::Mat::PIXEL_RGB,
        srcW,
        srcH,
        resizedW,
        resizedH);

    const int wpad = kInputSize - resizedW;
    const int hpad = kInputSize - resizedH;
    const int left = wpad / 2;
    const int right = wpad - left;
    const int top = hpad / 2;
    const int bottom = hpad - top;

    ncnn::Mat input;
    ncnn::copy_make_border(resized, input, top, bottom, left, right, ncnn::BORDER_CONSTANT, 114.f);
    input.substract_mean_normalize(nullptr, kNormVals);

    ncnn::Extractor ex = m_net.create_extractor();
    ex.set_light_mode(true);

    if (ex.input("in0", input) != 0) {
        return detections;
    }

    ncnn::Mat out0;
    if (ex.extract("out0", out0) != 0) {
        return detections;
    }

    ncnn::Mat out1;
    const bool hasMaskOutput = (ex.extract("out1", out1) == 0);

    if (out0.dims != 2 || out0.h < 5 || out0.w <= 0) {
        return detections;
    }

    const int maskCoeffOffset = 5;
    const int maskCoeffCount = (hasMaskOutput && out1.dims == 3)
        ? (std::max)(0, (std::min)(out1.c, out0.h - maskCoeffOffset))
        : 0;

    const float *xPtr = out0.row(0);
    const float *yPtr = out0.row(1);
    const float *wPtr = out0.row(2);
    const float *hPtr = out0.row(3);
    const float *scorePtr = out0.row(4);

    struct Proposal {
        Detection detection;
        QVector<float> maskCoeffs;
    };

    QVector<Proposal> proposals;
    proposals.reserve(128);

    for (int i = 0; i < out0.w; ++i) {
        const float score = scorePtr[i];
        if (!std::isfinite(score) || score < scoreThreshold) {
            continue;
        }

        const float cx = xPtr[i];
        const float cy = yPtr[i];
        const float bw = wPtr[i];
        const float bh = hPtr[i];
        if (!std::isfinite(cx) || !std::isfinite(cy) || !std::isfinite(bw) || !std::isfinite(bh)) {
            continue;
        }

        float x0 = (cx - bw * 0.5f - float(left)) / scale;
        float y0 = (cy - bh * 0.5f - float(top)) / scale;
        float x1 = (cx + bw * 0.5f - float(left)) / scale;
        float y1 = (cy + bh * 0.5f - float(top)) / scale;

        x0 = (std::clamp)(x0, 0.0f, float(srcW - 1));
        y0 = (std::clamp)(y0, 0.0f, float(srcH - 1));
        x1 = (std::clamp)(x1, 0.0f, float(srcW - 1));
        y1 = (std::clamp)(y1, 0.0f, float(srcH - 1));

        const float boxW = x1 - x0;
        const float boxH = y1 - y0;
        if (boxW < 2.0f || boxH < 2.0f) {
            continue;
        }

        Proposal proposal;
        proposal.detection.rect = QRectF(x0, y0, boxW, boxH);
        proposal.detection.score = score;
        proposal.detection.label = 0;
        proposal.detection.frameWidth = srcW;
        proposal.detection.frameHeight = srcH;
        if (maskCoeffCount > 0) {
            proposal.maskCoeffs.reserve(maskCoeffCount);
            for (int coeffIndex = 0; coeffIndex < maskCoeffCount; ++coeffIndex) {
                proposal.maskCoeffs.push_back(out0.row(maskCoeffOffset + coeffIndex)[i]);
            }
        }
        proposals.push_back(std::move(proposal));
    }

    std::sort(proposals.begin(), proposals.end(), [](const Proposal &a, const Proposal &b) {
        return a.detection.score > b.detection.score;
    });

    QVector<Detection> proposalDetections;
    proposalDetections.reserve(proposals.size());
    for (const Proposal &proposal : proposals) {
        proposalDetections.push_back(proposal.detection);
    }

    QVector<int> picked;
    nmsSortedBboxes(proposalDetections, picked, kNmsThreshold);

    const qsizetype candidateCount = (std::min)(picked.size(), qsizetype(kMaxCandidateDetections));
    QVector<Detection> candidates;
    candidates.reserve(candidateCount);
    for (qsizetype i = 0; i < candidateCount; ++i) {
        const Proposal &proposal = proposals[picked[i]];
        Detection det = proposal.detection;
        if (maskCoeffCount > 0 && proposal.maskCoeffs.size() == maskCoeffCount) {
            populateMaskGeometry(det, proposal.maskCoeffs, out1, srcW, srcH, left, top, scale);
        }
        candidates.push_back(std::move(det));
    }

    populateCombinedLaneMetrics(candidates);
    detections = selectLaneDetections(candidates);
    populateCombinedLaneMetrics(detections);
    return detections;
}

float YoloEngine::intersectionArea(const Detection &a, const Detection &b)
{
    const float x1 = (std::max)(float(a.rect.left()), float(b.rect.left()));
    const float y1 = (std::max)(float(a.rect.top()), float(b.rect.top()));
    const float x2 = (std::min)(float(a.rect.right()), float(b.rect.right()));
    const float y2 = (std::min)(float(a.rect.bottom()), float(b.rect.bottom()));

    const float w = (std::max)(0.0f, x2 - x1);
    const float h = (std::max)(0.0f, y2 - y1);
    return w * h;
}

void YoloEngine::nmsSortedBboxes(const QVector<Detection> &detections, QVector<int> &picked, float nmsThreshold)
{
    picked.clear();
    const int n = detections.size();
    if (n == 0) {
        return;
    }

    QVector<float> areas;
    areas.reserve(n);
    for (const Detection &det : detections) {
        areas.push_back(float(det.rect.width() * det.rect.height()));
    }

    for (int i = 0; i < n; ++i) {
        const Detection &a = detections[i];
        bool keep = true;
        for (int pickedIndex : picked) {
            const Detection &b = detections[pickedIndex];
            const float inter = intersectionArea(a, b);
            const float uni = areas[i] + areas[pickedIndex] - inter;
            const float iou = uni > 0.0f ? inter / uni : 0.0f;
            if (iou > nmsThreshold) {
                keep = false;
                break;
            }
        }
        if (keep) {
            picked.push_back(i);
        }
    }
}
#endif
