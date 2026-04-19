#pragma once

#include <QMutex>
#include <QQueue>
#include <QByteArray>

class FrameRingBuffer
{
public:
    explicit FrameRingBuffer(int maxSize = 3)
        : m_maxSize(maxSize) {}

    void push(const QByteArray &frame) {
        QMutexLocker locker(&m_mutex);

        // Aggressive drop: always keep only latest for real-time
        if (m_queue.size() >= m_maxSize) {
            m_queue.dequeue();
        }
        m_queue.enqueue(frame);
    }

    QByteArray takeNewest() {
        QMutexLocker locker(&m_mutex);

        if (m_queue.isEmpty())
            return QByteArray();

        QByteArray frame = m_queue.last();
        m_queue.clear(); // consume all - we only want latest
        return frame;
    }

    bool hasFrame() {
        QMutexLocker locker(&m_mutex);
        return !m_queue.isEmpty();
    }

    void clear() {
        QMutexLocker locker(&m_mutex);
        m_queue.clear();
    }

    int size() {
        QMutexLocker locker(&m_mutex);
        return m_queue.size();
    }

private:
    QQueue<QByteArray> m_queue;
    QMutex m_mutex;
    int m_maxSize;
};
