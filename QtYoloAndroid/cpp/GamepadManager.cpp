#include "GamepadManager.h"
#include <QDebug>
#include <cmath>
#include <QGuiApplication>

#ifdef Q_OS_ANDROID
#include <android/input.h>
#include <android/keycodes.h>
#endif

#ifdef Q_OS_WIN
#include <windows.h>
#include <xinput.h>

typedef DWORD (WINAPI *XInputGetStateFunc)(DWORD dwUserIndex, XINPUT_STATE* pState);
typedef DWORD (WINAPI *XInputSetStateFunc)(DWORD dwUserIndex, XINPUT_VIBRATION* pVibration);

static HMODULE xinputDll = nullptr;
static XInputGetStateFunc pXInputGetState = nullptr;
static XInputSetStateFunc pXInputSetState = nullptr;

static bool loadXInput()
{
    if (xinputDll) return true;

    xinputDll = LoadLibraryW(L"XInput1_4.dll");
    if (!xinputDll) {
        xinputDll = LoadLibraryW(L"XInput1_3.dll");
    }

    if (xinputDll) {
        pXInputGetState = (XInputGetStateFunc)GetProcAddress(xinputDll, "XInputGetState");
        pXInputSetState = (XInputSetStateFunc)GetProcAddress(xinputDll, "XInputSetState");
        return pXInputGetState != nullptr;
    }
    return false;
}

static void unloadXInput()
{
    if (xinputDll) {
        FreeLibrary(xinputDll);
        xinputDll = nullptr;
        pXInputGetState = nullptr;
        pXInputSetState = nullptr;
    }
}
#endif

GamepadManager::GamepadManager(QObject *parent)
    : QObject(parent)
{
    scanForGamepads();

    m_pollTimer = new QTimer(this);
    m_pollTimer->setInterval(50);
    connect(m_pollTimer, &QTimer::timeout, this, &GamepadManager::pollGamepad);
    m_pollTimer->start();

    m_vibrateTimer = new QTimer(this);
    m_vibrateTimer->setSingleShot(true);
    connect(m_vibrateTimer, &QTimer::timeout, this, [this]() {
        vibrate(0, 0);
    });

#ifdef Q_OS_ANDROID
    QGuiApplication::instance()->installNativeEventFilter(this);
    qDebug() << "[GAMEPAD] Native event filter installed for Android";
#endif
}

GamepadManager::~GamepadManager()
{
#ifdef Q_OS_WIN
    unloadXInput();
#endif
#ifdef Q_OS_ANDROID
    QGuiApplication::instance()->removeNativeEventFilter(this);
#endif
}

bool GamepadManager::gamepadConnected() const
{
    return m_connected;
}

QString GamepadManager::gamepadName() const
{
    return m_gamepadName;
}

QString GamepadManager::getControllerName(int id)
{
    switch (id) {
    case 0: return QStringLiteral("Controller 1");
    case 1: return QStringLiteral("Controller 2");
    case 2: return QStringLiteral("Controller 3");
    case 3: return QStringLiteral("Controller 4");
    default: return QStringLiteral("Unknown");
    }
}

void GamepadManager::scanForGamepads()
{
#ifdef Q_OS_WIN
    if (!loadXInput()) {
        qDebug() << "[GAMEPAD] XInput yüklenemedi";
        return;
    }

    for (int i = 0; i < 4; i++) {
        XINPUT_STATE state;
        ZeroMemory(&state, sizeof(XINPUT_STATE));

        if (pXInputGetState(i, &state) == ERROR_SUCCESS) {
            if (!m_connected || m_controllerId != i) {
                m_connected = true;
                m_controllerId = i;
                m_gamepadName = getControllerName(i);
                emit gamepadConnectedChanged();
                emit gamepadNameChanged();
                qDebug() << "[GAMEPAD] Controller bağlandı:" << m_gamepadName << "ID:" << i;
            }
            return;
        }
    }
#elif defined(Q_OS_ANDROID)
    if (!m_connected) {
        m_connected = true;
        m_gamepadName = QStringLiteral("Android Gamepad");
        emit gamepadConnectedChanged();
        emit gamepadNameChanged();
        qDebug() << "[GAMEPAD] Android gamepad hazır (native event filter)";
    }
#endif

    if (m_connected) {
        m_connected = false;
        m_controllerId = -1;
        m_deviceId = -1;
        m_gamepadName = QStringLiteral("Bağlı değil");
        emit gamepadConnectedChanged();
        emit gamepadNameChanged();
    }
}

void GamepadManager::pollGamepad()
{
    scanForGamepads();

    if (!m_connected) {
        if (m_currentDirection != "S") {
            m_currentDirection = "S";
            emit directionChanged("S");
        }
        return;
    }

#ifdef Q_OS_WIN
    if (!pXInputGetState) return;

    XINPUT_STATE state;
    ZeroMemory(&state, sizeof(XINPUT_STATE));

    if (pXInputGetState(m_controllerId, &state) != ERROR_SUCCESS) {
        m_connected = false;
        emit gamepadConnectedChanged();
        return;
    }

    double x = state.Gamepad.sThumbLX / 32767.0;
    double y = state.Gamepad.sThumbLY / 32767.0;

    const double DEADZONE = 0.15;
    if (std::abs(x) < DEADZONE) x = 0;
    if (std::abs(y) < DEADZONE) y = 0;

    m_leftX = x;
    m_leftY = -y;

    bool active = std::abs(x) > 0.05 || std::abs(y) > 0.05;
    if (active != m_gamepadActive) {
        m_gamepadActive = active;
        emit gamepadActiveChanged();
    }

    emit axisValuesChanged(m_leftX, m_leftY);
    emit joystickMoved(m_leftX, m_leftY); // Joystick'i oynat
    updateDirection();
    checkButtons(state);
#elif defined(Q_OS_ANDROID)
    emit axisValuesChanged(m_leftX, m_leftY);
#endif
}

#ifdef Q_OS_ANDROID
bool GamepadManager::nativeEventFilter(const QByteArray &eventType, void *message, qintptr *result)
{
    Q_UNUSED(result)

    if (eventType == "android" ||
        eventType == "application/x-qt-android-app" ||
        eventType == "android_input") {
        AInputEvent* event = static_cast<AInputEvent*>(message);
        if (!event) return false;

        int32_t deviceId = AInputEvent_getDeviceId(event);
        m_deviceId = deviceId;

        int32_t type = AInputEvent_getType(event);

        if (type == AINPUT_EVENT_TYPE_MOTION) {
            int32_t source = AInputEvent_getSource(event);
            if ((source & AINPUT_SOURCE_JOYSTICK) || (source & AINPUT_SOURCE_GAMEPAD)) {
                int32_t pointerIndex = 0;

                float x = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_X, pointerIndex);
                float y = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_Y, pointerIndex);

                if (x == 0 && y == 0) {
                    x = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_Z, pointerIndex);
                    y = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_RZ, pointerIndex);
                }

                float ltrigger = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_LTRIGGER, pointerIndex);
                float rtrigger = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_RTRIGGER, pointerIndex);
                float brake = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_BRAKE, pointerIndex);
                float gas = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_GAS, pointerIndex);

                if (ltrigger == 0 && brake > 0) ltrigger = brake;
                if (rtrigger == 0 && gas > 0) rtrigger = gas;

                const float DEADZONE = 0.15f;
                if (std::abs(x) < DEADZONE) x = 0;
                if (std::abs(y) < DEADZONE) y = 0;

                m_leftX = x;
                m_leftY = -y;

                bool active = std::abs(x) > 0.05 || std::abs(y) > 0.05;
                if (active != m_gamepadActive) {
                    m_gamepadActive = active;
                    emit gamepadActiveChanged();
                }

                // DPAD (hat values) - yön tuşları
                float hatX = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_HAT_X, pointerIndex);
                float hatY = AMotionEvent_getAxisValue(event, AMOTION_EVENT_AXIS_HAT_Y, pointerIndex);

                if (std::abs(hatX) > 0.5f || std::abs(hatY) > 0.5f) {
                    double joyX = 0, joyY = 0;
                    if (hatY < -0.5f) joyY = -1.0;
                    else if (hatY > 0.5f) joyY = 1.0;
                    if (hatX < -0.5f) joyX = -1.0;
                    else if (hatX > 0.5f) joyX = 1.0;
                    emit joystickMoved(joyX, joyY);
                }

                // L2 - Motor hızını azalt
                bool l2Pressed = m_wasL2 ? (ltrigger > 0.15f) : (ltrigger > 0.25f);
                if (l2Pressed && !m_wasL2) {
                    emit motorSpeedChangeRequested(-50);
                    qDebug() << "[GAMEPAD] L2 pressed - Motor Speed -50";
                }
                m_wasL2 = l2Pressed;

                // R2 - Motor hızını artır
                bool r2Pressed = m_wasR2 ? (rtrigger > 0.15f) : (rtrigger > 0.25f);
                if (r2Pressed && !m_wasR2) {
                    emit motorSpeedChangeRequested(50);
                    qDebug() << "[GAMEPAD] R2 pressed - Motor Speed +50";
                }
                m_wasR2 = r2Pressed;

                updateDirection();
                emit axisValuesChanged(m_leftX, m_leftY);
                emit joystickMoved(m_leftX, m_leftY);

                return true;
            }
        }
        else if (type == AINPUT_EVENT_TYPE_KEY) {
            int32_t keyCode = AKeyEvent_getKeyCode(event);
            int32_t action = AKeyEvent_getAction(event);
            bool pressed = (action == AKEY_EVENT_ACTION_DOWN);

            // DPAD yön tuşları - joystick'i oynat
            double joyX = 0, joyY = 0;
            bool isDpad = true;

            switch (keyCode) {
            case AKEYCODE_DPAD_UP:
                joyY = pressed ? -1.0 : 0.0;
                break;
            case AKEYCODE_DPAD_DOWN:
                joyY = pressed ? 1.0 : 0.0;
                break;
            case AKEYCODE_DPAD_LEFT:
                joyX = pressed ? -1.0 : 0.0;
                break;
            case AKEYCODE_DPAD_RIGHT:
                joyX = pressed ? 1.0 : 0.0;
                break;
            default:
                isDpad = false;
                break;
            }

            if (isDpad) {
                emit joystickMoved(joyX, joyY);
                return true;
            }
        }
    }

    return false;
}
#endif

void GamepadManager::updateDirection()
{
    double x = m_leftX;
    double y = m_leftY;

    QString newDirection = "S";

    if (std::abs(x) > std::abs(y)) {
        if (x > 0.3) {
            newDirection = "R";
        } else if (x < -0.3) {
            newDirection = "L";
        }
    } else {
        if (y > 0.3) {
            newDirection = "B";
        } else if (y < -0.3) {
            newDirection = "F";
        }
    }

    if (newDirection != m_currentDirection) {
        m_currentDirection = newDirection;
        emit directionChanged(newDirection);

        if (newDirection != "S") {
            vibrateTimed(12000, 12000, 80);
        }
    }
}

void GamepadManager::vibrate(int leftMotor, int rightMotor)
{
    Q_UNUSED(leftMotor)
    Q_UNUSED(rightMotor)
#ifdef Q_OS_WIN
    if (!pXInputSetState || m_controllerId < 0) return;

    XINPUT_VIBRATION vibration;
    vibration.wLeftMotorSpeed = leftMotor;
    vibration.wRightMotorSpeed = rightMotor;
    pXInputSetState(m_controllerId, &vibration);
#endif
}

void GamepadManager::vibrateTimed(int leftMotor, int rightMotor, int durationMs)
{
    vibrate(leftMotor, rightMotor);
    if (m_vibrateTimer) {
        m_vibrateTimer->stop();
        m_vibrateTimer->start(durationMs);
    }
}

#ifdef Q_OS_WIN
void GamepadManager::checkButtons(const XINPUT_STATE &state)
{
    // L2 ve R2 trigger'ları analog değer olarak işleniyor
    BYTE lt = state.Gamepad.bLeftTrigger;
    BYTE rt = state.Gamepad.bRightTrigger;

    const int PRESS_THRESHOLD = 180;
    const int RELEASE_THRESHOLD = 150;

    // L2 - Motor hızını azalt
    bool l2Pressed = m_wasL2 ? (lt > RELEASE_THRESHOLD) : (lt > PRESS_THRESHOLD);
    if (l2Pressed && !m_wasL2) {
        emit motorSpeedChangeRequested(-50);
        qDebug() << "[GAMEPAD] L2 pressed - Motor Speed -50";
        vibrateTimed(16000, 0, 50);
    }
    m_wasL2 = l2Pressed;

    // R2 - Motor hızını artır
    bool r2Pressed = m_wasR2 ? (rt > RELEASE_THRESHOLD) : (rt > PRESS_THRESHOLD);
    if (r2Pressed && !m_wasR2) {
        emit motorSpeedChangeRequested(50);
        qDebug() << "[GAMEPAD] R2 pressed - Motor Speed +50";
        vibrateTimed(0, 16000, 50);
    }
    m_wasR2 = r2Pressed;
}
#else
void GamepadManager::checkButtons(quint32 buttons)
{
    Q_UNUSED(buttons)
}
#endif
