QT += quick quickcontrols2 websockets

CONFIG += c++17
CONFIG += qml_debug

SOURCES += \
    hapticsmanager.cpp \
    liveframeprovider.cpp \
    main.cpp \
    websocketclient.cpp

HEADERS += \
    hapticsmanager.h \
    liveframeprovider.h \
    websocketclient.h

RESOURCES += \
    qml.qrc

DISTFILES += \
    qml/Main.qml \
    qml/Joystick.qml \
    qml/MotorSpeedController.qml \
    qml/ModernButton.qml \
    android/AndroidManifest.xml \
    android/build.gradle \
    android/gradle.properties \
    android/gradle/wrapper/gradle-wrapper.jar \
    android/gradle/wrapper/gradle-wrapper.properties \
    android/gradlew \
    android/gradlew.bat \
    android/res/values/libs.xml \
    android/res/xml/qtprovider_paths.xml

TARGET = LineFollowingQuickUI
TEMPLATE = app

contains(ANDROID_TARGET_ARCH,arm64-v8a) {
    ANDROID_PACKAGE_SOURCE_DIR = \
        $$PWD/android
}
