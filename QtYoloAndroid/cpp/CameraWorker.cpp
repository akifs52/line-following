#include "CameraWorker.h"

#include <QVideoFrame>

CameraWorker::CameraWorker(QObject *parent)
    : QObject(parent)
{
}

void CameraWorker::setInferenceBusy(bool busy)
{
    m_inferenceBusy = busy;
}

void CameraWorker::attachVideoSink(QVideoSink *videoSink)
{
    if (m_videoSink == videoSink) {
        return;
    }

    if (m_videoFrameConnection) {
        disconnect(m_videoFrameConnection);
    }

    m_videoSink = videoSink;
    if (!m_videoSink) {
        return;
    }

    m_videoFrameConnection = connect(
        m_videoSink,
        &QVideoSink::videoFrameChanged,
        this,
        &CameraWorker::onVideoFrameChanged);
}

void CameraWorker::onVideoFrameChanged(const QVideoFrame &frame)
{
    if (m_inferenceBusy || !frame.isValid()) {
        return;
    }

    const QImage image = frame.toImage();
    if (image.isNull()) {
        return;
    }

    emit frameReady(image);
}
