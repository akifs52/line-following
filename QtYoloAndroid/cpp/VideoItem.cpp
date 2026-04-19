#include "VideoItem.h"
#include <QDebug>

VideoItem::VideoItem(QQuickItem *parent)
    : QQuickPaintedItem(parent)
{
    setRenderTarget(QQuickPaintedItem::FramebufferObject);
    setSmooth(false);
    setAntialiasing(false);
    qDebug() << "[VideoItem] Created";
}

QRectF VideoItem::contentRect() const
{
    return m_contentRect;
}

void VideoItem::setFrame(const QImage &img)
{
    if (img.isNull()) {
        qDebug() << "[VideoItem] setFrame called with null image";
        return;
    }
    
    QMutexLocker locker(&m_mutex);
    m_frame = img.copy();
    locker.unlock();
    update();
    
    qDebug() << "[VideoItem] Frame set:" << img.width() << "x" << img.height();
}

void VideoItem::paint(QPainter *painter)
{
    QMutexLocker locker(&m_mutex);
    if (!m_frame.isNull()) {
        QRectF targetRect = boundingRect();
        QRectF sourceRect(0, 0, m_frame.width(), m_frame.height());
        
        // Calculate aspect ratio preserving rect
        qreal scale = qMin(targetRect.width() / sourceRect.width(),
                          targetRect.height() / sourceRect.height());
        qreal w = sourceRect.width() * scale;
        qreal h = sourceRect.height() * scale;
        qreal x = targetRect.x() + (targetRect.width() - w) / 2;
        qreal y = targetRect.y() + (targetRect.height() - h) / 2;
        
        QRectF destRect(x, y, w, h);
        painter->drawImage(destRect, m_frame, sourceRect);
        
        // Update content rect for overlay alignment
        if (m_contentRect != destRect) {
            m_contentRect = destRect;
            locker.unlock();
            emit contentRectChanged();
        }
    } else {
        qDebug() << "[VideoItem] paint: frame is null";
    }
}
