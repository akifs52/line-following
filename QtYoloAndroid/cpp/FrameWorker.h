#pragma once

#include <QThread>
#include <QImage>
#include <QMutex>
#include <QWaitCondition>
#include "FrameRingBuffer.h"

class FrameWorker : public QThread
{
    Q_OBJECT

public:
    explicit FrameWorker(FrameRingBuffer *ringBuffer, QObject *parent = nullptr);
    ~FrameWorker();

    void stop();

signals:
    void frameReady(const QImage &image);

protected:
    void run() override;

private:
    FrameRingBuffer *m_ringBuffer;
    bool m_running = true;
    QMutex m_mutex;
    QWaitCondition m_condition;
};
