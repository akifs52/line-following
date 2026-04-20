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

# NCNN paths for all platforms (using actual 3rdparty folder names)
NCNN_VERSION = 20260113

# Android NCNN with GPU/Vulkan support
android {
    NCNN_ANDROID_ROOT = $$PWD/3rdparty/ncnn-$$NCNN_VERSION-android-vulkan/ncnn-$$NCNN_VERSION-android-vulkan

    NCNN_ABI = $$ANDROID_TARGET_ARCH
    isEmpty(NCNN_ABI): NCNN_ABI = $$ANDROID_ABI
    isEmpty(NCNN_ABI): NCNN_ABI = $$QT_ARCH
    NCNN_LIB_DIR = $$NCNN_ANDROID_ROOT/$$NCNN_ABI/lib
    NCNN_INCLUDE_DIR = $$NCNN_ANDROID_ROOT/$$NCNN_ABI/include

    !exists($$NCNN_LIB_DIR/libncnn.a) {
        message(ncnn libs not found for ABI '$$NCNN_ABI', fallback to arm64-v8a)
        NCNN_ABI = arm64-v8a
        NCNN_LIB_DIR = $$NCNN_ANDROID_ROOT/$$NCNN_ABI/lib
        NCNN_INCLUDE_DIR = $$NCNN_ANDROID_ROOT/$$NCNN_ABI/include
    }

    INCLUDEPATH += $$NCNN_INCLUDE_DIR

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

# iOS NCNN with GPU/Metal support
ios {
    NCNN_IOS_ROOT = $$PWD/3rdparty/ncnn-$$NCNN_VERSION-ios-vulkan

    # iOS framework paths
    LIBS += -F$$NCNN_IOS_ROOT \
            -framework ncnn \
            -framework openmp \
            -framework Metal \
            -framework MetalPerformanceShaders \
            -framework Foundation

    INCLUDEPATH += $$NCNN_IOS_ROOT/ncnn.framework/Headers

    QMAKE_LFLAGS += -Wl,-rpath,@executable_path/Frameworks
}

# macOS NCNN with GPU/Metal support
macx {
    NCNN_MACOS_ROOT = $$PWD/3rdparty/ncnn-$$NCNN_VERSION-macos-vulkan

    # macOS framework paths
    LIBS += -F$$NCNN_MACOS_ROOT \
            -framework ncnn \
            -framework openmp \
            -framework Metal \
            -framework MetalPerformanceShaders \
            -framework Foundation

    INCLUDEPATH += $$NCNN_MACOS_ROOT/ncnn.framework/Headers

    QMAKE_LFLAGS += -Wl,-rpath,@executable_path/../Frameworks
}

# Windows NCNN with GPU/Vulkan support
win32 {
    NCNN_WINDOWS_ROOT = $$PWD/3rdparty/ncnn-$$NCNN_VERSION-windows-vs2022/ncnn-$$NCNN_VERSION-windows-vs2022

    # Windows x64 library paths
    NCNN_LIB_DIR = $$NCNN_WINDOWS_ROOT/x64/lib
    NCNN_INCLUDE_DIR = $$NCNN_WINDOWS_ROOT/x64/include

    INCLUDEPATH += $$NCNN_INCLUDE_DIR

    LIBS += -L$$NCNN_LIB_DIR \
            -lncnn \
            -lglslang \
            -lSPIRV \
            -lOSDependent \
            -lMachineIndependent \
            -lGenericCodeGen \
            -lglslang-default-resource-limits


    # Vulkan SDK library path for MinGW
    LIBS += -LD:/VulkanSDK/1.4.341.1/Lib -lvulkan-1
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
