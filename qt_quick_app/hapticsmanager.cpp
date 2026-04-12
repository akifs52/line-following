#include "hapticsmanager.h"

#ifdef Q_OS_ANDROID
#include <QJniObject>
#include <jni.h>
#endif

HapticsManager::HapticsManager(QObject *parent)
    : QObject(parent)
{
}

void HapticsManager::vibrate(int ms)
{
#ifdef Q_OS_ANDROID
    QJniObject activity = QJniObject::callStaticObjectMethod(
        "org/qtproject/qt/android/QtNative",
        "activity",
        "()Landroid/app/Activity;"
    );

    if (!activity.isValid()) {
        qWarning("HapticsManager: Failed to get activity");
        return;
    }

    QJniObject vibrator = activity.callObjectMethod(
        "getSystemService",
        "(Ljava/lang/String;)Ljava/lang/Object;",
        QJniObject::fromString("vibrator").object<jstring>()
    );

    if (!vibrator.isValid()) {
        qWarning("HapticsManager: Failed to get vibrator service");
        return;
    }

    // Android 8+ (API 26+) için modern haptic feedback
    QJniObject vibrationEffect = QJniObject::callStaticObjectMethod(
        "android/os/VibrationEffect",
        "createOneShot",
        "(JI)Landroid/os/VibrationEffect;",
        (jlong)ms,
        -1 // DEFAULT_AMPLITUDE
    );

    if (vibrationEffect.isValid()) {
        vibrator.callMethod<void>(
            "vibrate",
            "(Landroid/os/VibrationEffect;)V",
            vibrationEffect.object<jobject>()
        );
    } else {
        // Fallback for older Android versions
        vibrator.callMethod<void>("vibrate", "(J)V", (jlong)ms);
    }
#else
    // Non-Android platforms: no-op
    Q_UNUSED(ms)
#endif
}

void HapticsManager::vibrateShort()
{
    vibrate(25);
}

void HapticsManager::vibrateMedium()
{
    vibrate(50);
}

void HapticsManager::vibrateLong()
{
    vibrate(100);
}
