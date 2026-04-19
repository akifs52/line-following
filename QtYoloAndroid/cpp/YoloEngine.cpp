#include "YoloEngine.h"

#include <QFile>
#include <QDebug>
#include <QVariantMap>
#include <QtConcurrent/QtConcurrentRun>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdint>

#if defined(Q_OS_ANDROID)
#include <ncnn/datareader.h>
#include <ncnn/gpu.h>
#include <ncnn/layer.h>
#endif

namespace {
constexpr float kMinThreshold = 0.001f;
constexpr float kMaxThreshold = 0.99f;

#if defined(Q_OS_ANDROID)
constexpr int kInputSize = 640;
constexpr float kNmsThreshold = 0.45f;
constexpr float kNormVals[3] = {1.f / 255.f, 1.f / 255.f, 1.f / 255.f};
constexpr int kModelRetryIntervalMs = 1500;
constexpr int kMaxModelRetryAttempts = 10;
#endif
} // namespace

YoloEngine::YoloEngine(QObject *parent)
    : QObject(parent)
{
    m_runtime.start();
    connect(&m_futureWatcher, &QFutureWatcher<InferenceResult>::finished, this, &YoloEngine::finishInference);
#if defined(Q_OS_ANDROID)
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

#if defined(Q_OS_ANDROID)
    const bool loaded = hasAssets && ensureModelLoaded();
#else
    // Desktop: Check if assets exist but skip NCNN loading (desktop testing mode)
    const bool loaded = hasAssets; // Desktop'ta model var ama NCNN yok, sadece kamera göster
    if (hasAssets) {
        qInfo() << "Desktop mode: Assets found, NCNN inference disabled (Android only)";
    }
#endif

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
#if !defined(Q_OS_ANDROID)
    else {
        qInfo() << "Desktop testing mode: Camera stream only, YOLO detection disabled";
    }
#endif

#if defined(Q_OS_ANDROID)
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

#if defined(Q_OS_ANDROID)
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

#if defined(Q_OS_ANDROID)
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

    const float scale = std::min(float(kInputSize) / float(srcW), float(kInputSize) / float(srcH));
    const int resizedW = std::max(1, int(std::round(float(srcW) * scale)));
    const int resizedH = std::max(1, int(std::round(float(srcH) * scale)));

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

    if (out0.dims != 2 || out0.h < 5 || out0.w <= 0) {
        return detections;
    }

    const float *xPtr = out0.row(0);
    const float *yPtr = out0.row(1);
    const float *wPtr = out0.row(2);
    const float *hPtr = out0.row(3);
    const float *scorePtr = out0.row(4);

    QVector<Detection> proposals;
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

        x0 = std::clamp(x0, 0.0f, float(srcW - 1));
        y0 = std::clamp(y0, 0.0f, float(srcH - 1));
        x1 = std::clamp(x1, 0.0f, float(srcW - 1));
        y1 = std::clamp(y1, 0.0f, float(srcH - 1));

        const float boxW = x1 - x0;
        const float boxH = y1 - y0;
        if (boxW < 2.0f || boxH < 2.0f) {
            continue;
        }

        Detection det;
        det.rect = QRectF(x0, y0, boxW, boxH);
        det.score = score;
        det.label = 0;
        proposals.push_back(det);
    }

    std::sort(proposals.begin(), proposals.end(), [](const Detection &a, const Detection &b) {
        return a.score > b.score;
    });

    QVector<int> picked;
    nmsSortedBboxes(proposals, picked, kNmsThreshold);

    const qsizetype maxDetections = 100;
    const qsizetype keepCount = std::min<qsizetype>(picked.size(), maxDetections);
    detections.reserve(keepCount);
    for (qsizetype i = 0; i < keepCount; ++i) {
        detections.push_back(proposals[picked[i]]);
    }

    return detections;
}

float YoloEngine::intersectionArea(const Detection &a, const Detection &b)
{
    const float x1 = std::max(float(a.rect.left()), float(b.rect.left()));
    const float y1 = std::max(float(a.rect.top()), float(b.rect.top()));
    const float x2 = std::min(float(a.rect.right()), float(b.rect.right()));
    const float y2 = std::min(float(a.rect.bottom()), float(b.rect.bottom()));

    const float w = std::max(0.0f, x2 - x1);
    const float h = std::max(0.0f, y2 - y1);
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
