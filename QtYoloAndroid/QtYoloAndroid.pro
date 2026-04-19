QT += quick quickcontrols2 multimedia concurrent network

CONFIG += c++17
TEMPLATE = app
TARGET = QtYoloAndroid

SOURCES += \
    main.cpp \
    cpp/CameraWorker.cpp \
    cpp/FrameWorker.cpp \
    cpp/HapticsManager.cpp \
    cpp/RaspiControlClient.cpp \
    cpp/TcpCameraClient.cpp \
    cpp/VideoItem.cpp \
    cpp/YoloEngine.cpp

HEADERS += \
    cpp/CameraWorker.h \
    cpp/FrameRingBuffer.h \
    cpp/FrameWorker.h \
    cpp/HapticsManager.h \
    cpp/RaspiControlClient.h \
    cpp/TcpCameraClient.h \
    cpp/VideoItem.h \
    cpp/YoloEngine.h

RESOURCES += qml.qrc

INCLUDEPATH += $$PWD/cpp

android {
    INCLUDEPATH += $$PWD/3rdparty/ncnn/include

    NCNN_LIBS_ROOT = $$PWD/3rdparty/ncnn/libs
    NCNN_ABI = $$ANDROID_TARGET_ARCH
    isEmpty(NCNN_ABI): NCNN_ABI = $$ANDROID_ABI
    isEmpty(NCNN_ABI): NCNN_ABI = $$QT_ARCH
    NCNN_LIB_DIR = $$NCNN_LIBS_ROOT/$$NCNN_ABI

    !exists($$NCNN_LIB_DIR/libncnn.a) {
        message(ncnn libs not found for ABI '$$NCNN_ABI', fallback to arm64-v8a)
        NCNN_ABI = arm64-v8a
        NCNN_LIB_DIR = $$NCNN_LIBS_ROOT/$$NCNN_ABI
    }

    LIBS += $$NCNN_LIB_DIR/libncnn.a \
            $$NCNN_LIB_DIR/libglslang.a \
            $$NCNN_LIB_DIR/libSPIRV.a \
            $$NCNN_LIB_DIR/libOSDependent.a \
            $$NCNN_LIB_DIR/libMachineIndependent.a \
            $$NCNN_LIB_DIR/libGenericCodeGen.a \
            $$NCNN_LIB_DIR/libglslang-default-resource-limits.a \
            -landroid \
            -lvulkan

    QMAKE_CFLAGS += -fopenmp
    QMAKE_CXXFLAGS += -fopenmp
    QMAKE_LFLAGS += -fopenmp -static-openmp

    ANDROID_PACKAGE_SOURCE_DIR = $$PWD/android
    ANDROID_MIN_SDK_VERSION = 24
    ANDROID_TARGET_SDK_VERSION = 33
}

DISTFILES += \
    android/AndroidManifest.xml \
    android/gradle.properties \
    android/gradle/wrapper/gradle-wrapper.jar \
    android/gradle/wrapper/gradle-wrapper.properties \
    android/gradlew \
    android/gradlew.bat \
    assets/yolo11.bin \
    assets/yolo11.param \
    icons/luxury-car.png \
    icons/MaterialIcons-Regular.ttf \
    icons/SpaceGrotesk-Bold.ttf \
    qml/Main.qml \
    qml/Joystick.qml \
    qml/MotorSpeedController.qml \
    qml/ModernButton.qml
