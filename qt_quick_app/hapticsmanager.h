#ifndef HAPTICSMANAGER_H
#define HAPTICSMANAGER_H

#include <QObject>

class HapticsManager : public QObject
{
    Q_OBJECT

public:
    explicit HapticsManager(QObject *parent = nullptr);

    Q_INVOKABLE void vibrate(int ms);
    Q_INVOKABLE void vibrateShort();
    Q_INVOKABLE void vibrateMedium();
    Q_INVOKABLE void vibrateLong();
};

#endif // HAPTICSMANAGER_H
