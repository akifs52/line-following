#pragma once

#include <QImage>
#include <QMutex>
#include <QQuickImageProvider>

class LiveFrameProvider : public QQuickImageProvider
{
public:
    LiveFrameProvider();

    QImage requestImage(const QString &id, QSize *size, const QSize &requestedSize) override;
    void setFrame(const QImage &frame);

private:
    mutable QMutex m_mutex;
    QImage m_frame;
};
