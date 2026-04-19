#pragma once

#include <QObject>
#include <QImage>
#include <QMetaObject>
#include <QPointer>
#include <QVideoSink>

class QVideoFrame;

class CameraWorker : public QObject
{
    Q_OBJECT

public:
    explicit CameraWorker(QObject *parent = nullptr);
    void attachVideoSink(QVideoSink *videoSink);

public slots:
    void setInferenceBusy(bool busy);

signals:
    void frameReady(const QImage &frame);

private slots:
    void onVideoFrameChanged(const QVideoFrame &frame);

private:
    bool m_inferenceBusy = false;
    QPointer<QVideoSink> m_videoSink;
    QMetaObject::Connection m_videoFrameConnection;
};
