#pragma once

#include <QObject>
#include <QByteArray>
#include <QElapsedTimer>
#include <QFutureWatcher>
#include <QImage>
#include <QMutex>
#include <QRectF>
#include <QSize>
#include <QStringList>
#include <QTimer>
#include <QVariantList>
#include <QVector>

// NCNN includes for all platforms with GPU support
#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
#include <ncnn/net.h>
#endif

class YoloEngine : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool enabled READ enabled WRITE setEnabled NOTIFY enabledChanged)
    Q_PROPERTY(float scoreThreshold READ scoreThreshold WRITE setScoreThreshold NOTIFY scoreThresholdChanged)
    Q_PROPERTY(double fps READ fps NOTIFY fpsChanged)
    Q_PROPERTY(bool modelLoaded READ modelLoaded NOTIFY modelLoadedChanged)
    Q_PROPERTY(QString modelStatus READ modelStatus NOTIFY modelStatusChanged)

public:
    explicit YoloEngine(QObject *parent = nullptr);
    ~YoloEngine() override;

    bool enabled() const;
    void setEnabled(bool enabled);

    float scoreThreshold() const;
    void setScoreThreshold(float threshold);

    double fps() const;
    bool modelLoaded() const;
    QString modelStatus() const;

    Q_INVOKABLE void clearDetections();

public slots:
    void processFrame(const QImage &frame);

signals:
    void detectionsReady(const QVariantList &boxes);
    void enabledChanged();
    void inferenceBusyChanged(bool busy);
    void scoreThresholdChanged();
    void fpsChanged();
    void modelLoadedChanged();
    void modelStatusChanged();

private:
    struct Detection {
        QRectF rect;
        float score = 0.0f;
        int label = 0;
    };

    struct InferenceResult {
        QVector<Detection> detections;
        QSize frameSize;
    };

    void updateModelLoadedState();
    void setModelStatus(const QString &status);
    void setInferenceBusy(bool busy);
    void startInference(const QImage &frame);
    void finishInference();
    QVariantList toVariantList(const QVector<Detection> &detections, const QSize &frameSize) const;

#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
    bool ensureModelLoaded();
    QVector<Detection> runNcnnInference(const QImage &frame, float scoreThreshold) const;
    static float intersectionArea(const Detection &a, const Detection &b);
    static void nmsSortedBboxes(const QVector<Detection> &detections, QVector<int> &picked, float nmsThreshold);
#endif

    bool m_enabled = true;
    float m_scoreThreshold = 0.35f; // Minimum 30% confidence for detections
    double m_fps = 0.0;
    bool m_modelLoaded = false;
    QString m_modelStatus = QStringLiteral("Model assets: checking");
    QStringList m_classNames{QStringLiteral("line")};

    qint64 m_lastFrameMs = 0;
    QElapsedTimer m_runtime;
    bool m_inferenceBusy = false;
    QImage m_pendingFrame;
    QFutureWatcher<InferenceResult> m_futureWatcher;
    bool m_usingVulkan = false;
    QString m_lastLoadError;

#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS) || defined(Q_OS_MAC) || defined(Q_OS_WIN)
    mutable ncnn::Net m_net;
    mutable QMutex m_inferenceMutex;
    bool m_netInitialized = false;
    QByteArray m_paramData;
    QByteArray m_modelData;
    QByteArray m_modelDataAligned;
    QTimer m_modelRetryTimer;
    int m_modelRetryAttempts = 0;
#endif
};
