#include <QCoreApplication>
#include <QDebug>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QTimer>
#include <QVideoSink>

#include "cpp/CameraWorker.h"
#include "cpp/HapticsManager.h"
#include "cpp/RaspiControlClient.h"
#include "cpp/TcpCameraClient.h"
#include "cpp/VideoItem.h"
#include "cpp/YoloEngine.h"

#if defined(Q_OS_ANDROID)
#include <ncnn/gpu.h>
#endif

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    int exitCode = -1;

#if defined(Q_OS_ANDROID)
    const int gpuInitRet = ncnn::create_gpu_instance();
    if (gpuInitRet != 0) {
        qWarning() << "ncnn create_gpu_instance failed:" << gpuInitRet;
    }
#endif

    {
        QQmlApplicationEngine engine;

        CameraWorker cameraWorker;
        HapticsManager hapticsManager;
        RaspiControlClient controlClient;
        TcpCameraClient tcpCameraClient;
        YoloEngine yoloEngine;
        
        // Register VideoItem type for QML
        qmlRegisterType<VideoItem>("Camera", 1, 0, "VideoItem");

        // Connect TCP camera to YOLO engine
        QObject::connect(
            &tcpCameraClient,
            &TcpCameraClient::frameReady,
            &yoloEngine,
            &YoloEngine::processFrame);

        engine.rootContext()->setContextProperty(QStringLiteral("cameraWorker"), &cameraWorker);
        engine.rootContext()->setContextProperty(QStringLiteral("haptics"), &hapticsManager);
        engine.rootContext()->setContextProperty(QStringLiteral("controlClient"), &controlClient);
        engine.rootContext()->setContextProperty(QStringLiteral("tcpCameraClient"), &tcpCameraClient);
        engine.rootContext()->setContextProperty(QStringLiteral("yoloEngine"), &yoloEngine);

        const QUrl url(QStringLiteral("qrc:/qml/Main.qml"));
        QObject::connect(
            &engine,
            &QQmlApplicationEngine::objectCreated,
            &app,
            [url](QObject *object, const QUrl &objectUrl) {
                if (!object && objectUrl == url) {
                    QCoreApplication::exit(-1);
                }
            },
            Qt::QueuedConnection);

        engine.load(url);
        if (engine.rootObjects().isEmpty()) {
            exitCode = -1;
        } else {
            // Connect VideoItem to TcpCameraClient for frame display
            const auto bindVideoItem = [&engine, &tcpCameraClient]() {
                QObject *rootObject = engine.rootObjects().isEmpty() ? nullptr : engine.rootObjects().constFirst();
                if (!rootObject) {
                    return;
                }

                VideoItem *liveVideo = rootObject->findChild<VideoItem *>(QStringLiteral("liveVideo"));
                if (!liveVideo) {
                    qWarning() << "[Main] liveVideo VideoItem not found";
                    return;
                }

                tcpCameraClient.setVideoItem(liveVideo);
                qDebug() << "[Main] VideoItem connected to TcpCameraClient";
            };

            bindVideoItem();
            QTimer::singleShot(100, &app, bindVideoItem); // Retry after 100ms to ensure QML is fully loaded
            
            exitCode = app.exec();
        }
    }

#if defined(Q_OS_ANDROID)
    ncnn::destroy_gpu_instance();
#endif

    return exitCode;
}
