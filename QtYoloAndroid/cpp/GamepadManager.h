#ifndef GAMEPADMANAGER_H
#define GAMEPADMANAGER_H

#include <QObject>
#include <QTimer>
#include <QString>

#ifdef Q_OS_ANDROID
#include <QAbstractNativeEventFilter>
#endif

class GamepadManager : public QObject
#ifdef Q_OS_ANDROID
    , public QAbstractNativeEventFilter
#endif
{
    Q_OBJECT
    Q_PROPERTY(bool gamepadConnected READ gamepadConnected NOTIFY gamepadConnectedChanged)
    Q_PROPERTY(QString gamepadName READ gamepadName NOTIFY gamepadNameChanged)
    Q_PROPERTY(bool gamepadActive READ gamepadActive NOTIFY gamepadActiveChanged)

public:
    explicit GamepadManager(QObject *parent = nullptr);
    ~GamepadManager();

    bool gamepadConnected() const;
    QString gamepadName() const;
    bool gamepadActive() const { return m_gamepadActive; }

    double leftX() const { return m_leftX; }
    double leftY() const { return m_leftY; }

signals:
    void gamepadConnectedChanged();
    void gamepadNameChanged();
    void gamepadActiveChanged();
    void axisValuesChanged(double x, double y);
    void directionChanged(const QString &direction);
    void motorSpeedChangeRequested(int delta); // L2/R2 için
    void joystickMoved(double x, double y); // Yön tuşları için

public slots:
    void scanForGamepads();
    void vibrate(int leftMotor, int rightMotor);
    void vibrateTimed(int leftMotor, int rightMotor, int durationMs);

private slots:
    void pollGamepad();

private:
    void updateDirection();
    QString getControllerName(int id);

#ifdef Q_OS_ANDROID
    bool nativeEventFilter(const QByteArray &eventType, void *message, qintptr *result) override;
#endif

#ifdef Q_OS_WIN
    void checkButtons(const struct _XINPUT_STATE &state);
#else
    void checkButtons(quint32 buttons);
#endif

    QTimer *m_pollTimer = nullptr;
    QTimer *m_vibrateTimer = nullptr;

    bool m_connected = false;
    bool m_gamepadActive = false;
    int m_controllerId = -1;
    int m_deviceId = -1;
    QString m_gamepadName;
    QString m_currentDirection = "S";

    double m_leftX = 0.0;
    double m_leftY = 0.0;

#ifdef Q_OS_WIN
    quint16 m_lastButtons = 0;
    bool m_wasL2 = false;
    bool m_wasR2 = false;
#else
    bool m_wasL2 = false;
    bool m_wasR2 = false;
    bool m_wasL1 = false;
    bool m_wasR1 = false;
#endif
};

#endif // GAMEPADMANAGER_H
