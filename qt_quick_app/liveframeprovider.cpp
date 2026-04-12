#include "liveframeprovider.h"

#include <QColor>
#include <QMutexLocker>
#include <QPainter>

LiveFrameProvider::LiveFrameProvider()
    : QQuickImageProvider(QQuickImageProvider::Image)
{
    m_frame = QImage(640, 360, QImage::Format_RGB32);
    m_frame.fill(QColor("#0b1220"));

    QPainter p(&m_frame);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setPen(QColor("#64748b"));
    p.setFont(QFont("Segoe UI", 24, QFont::Bold));
    p.drawText(m_frame.rect(), Qt::AlignCenter, QStringLiteral("Camera Feed"));
}

QImage LiveFrameProvider::requestImage(const QString &id, QSize *size, const QSize &requestedSize)
{
    Q_UNUSED(id);

    QMutexLocker lock(&m_mutex);
    QImage out = m_frame;
    if (requestedSize.isValid()) {
        out = out.scaled(requestedSize, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    }
    if (size) {
        *size = out.size();
    }
    return out;
}

void LiveFrameProvider::setFrame(const QImage &frame)
{
    if (frame.isNull()) {
        return;
    }
    QMutexLocker lock(&m_mutex);
    m_frame = frame.convertToFormat(QImage::Format_RGB32);
}
