#include <QCoreApplication>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "liveframeprovider.h"
#include "websocketclient.h"
#include "hapticsmanager.h"

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);

    QQmlApplicationEngine engine;
    auto *frameProvider = new LiveFrameProvider();
    engine.addImageProvider(QStringLiteral("live"), frameProvider);

    WebSocketClient wsClient(frameProvider);
    engine.rootContext()->setContextProperty(QStringLiteral("wsClient"), &wsClient);

    HapticsManager hapticsManager;
    engine.rootContext()->setContextProperty(QStringLiteral("haptics"), &hapticsManager);

    const QUrl url(QStringLiteral("qrc:/qml/qml/Main.qml"));
    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreated,
        &app,
        [url](QObject *obj, const QUrl &objUrl) {
            if (!obj && url == objUrl) {
                QCoreApplication::exit(-1);
            }
        },
        Qt::QueuedConnection);

    engine.load(url);
    return app.exec();
}
