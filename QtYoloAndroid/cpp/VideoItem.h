#pragma once

#include <QQuickPaintedItem>
#include <QPainter>
#include <QImage>
#include <QMutex>

class VideoItem : public QQuickPaintedItem
{
    Q_OBJECT
    Q_PROPERTY(QRectF contentRect READ contentRect NOTIFY contentRectChanged)

public:
    explicit VideoItem(QQuickItem *parent = nullptr);

    void setFrame(const QImage &img);
    QRectF contentRect() const;

protected:
    void paint(QPainter *painter) override;
    void geometryChange(const QRectF &newGeometry, const QRectF &oldGeometry) override;

signals:
    void contentRectChanged();

private:
    void updateContentRect();
    QImage m_frame;
    QMutex m_mutex;
    QRectF m_contentRect;
};
