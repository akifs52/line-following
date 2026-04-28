#include "FrameWorker.h"
#include <QDebug>

FrameWorker::FrameWorker(FrameRingBuffer *ringBuffer, QObject *parent)
    : QThread(parent)
    , m_ringBuffer(ringBuffer)
{
}

FrameWorker::~FrameWorker()
{
    stop();
    wait();
}

void FrameWorker::stop()
{
    QMutexLocker locker(&m_mutex);
    m_running = false;
    m_condition.wakeAll();
}

void FrameWorker::run()
{
    qDebug() << "[FrameWorker] Thread started";

    while (true) {
        {
            QMutexLocker locker(&m_mutex);
            if (!m_running)
                break;
        }

        // Get newest frame (drops old frames automatically)
        QByteArray jpeg = m_ringBuffer->takeNewest();

        if (jpeg.isEmpty()) {
            // No frame available, wait a bit
            QThread::msleep(5);
            continue;
        }

        // Decode JPEG to QImage
        QImage image = QImage::fromData(jpeg, "JPEG");

        if (!image.isNull()) {
            emit frameReady(image);
        } else {
            qDebug() << "[FrameWorker] Failed to decode JPEG frame, size:" << jpeg.size();
        }
    }

    qDebug() << "[FrameWorker] Thread stopped";
}
