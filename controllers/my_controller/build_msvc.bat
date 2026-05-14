@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" || exit /b 1

if "%WEBOTS_HOME%"=="" set "WEBOTS_HOME=C:\Program Files\Webots"
set "NCNN_ROOT=%SCRIPT_DIR%..\..\QtYoloAndroid\3rdparty\ncnn-20260113-windows-vs2022\ncnn-20260113-windows-vs2022"
if "%VULKAN_SDK%"=="" set "VULKAN_SDK=D:\VulkanSDK\1.4.341.1"

if not exist "%WEBOTS_HOME%\include\controller\c\webots\robot.h" (
  echo [ERROR] WEBOTS_HOME is invalid: %WEBOTS_HOME%
  popd
  exit /b 1
)

if not exist "%NCNN_ROOT%\x64\include\ncnn\net.h" (
  echo [ERROR] NCNN headers not found: %NCNN_ROOT%
  popd
  exit /b 1
)

if not exist "%VULKAN_SDK%\Lib\vulkan-1.lib" (
  echo [ERROR] Vulkan SDK not found: %VULKAN_SDK%
  popd
  exit /b 1
)

if not defined VSCMD_VER (
  call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 (
    echo [ERROR] Could not initialize Visual Studio x64 tools.
    popd
    exit /b 1
  )
)

cl /nologo /EHsc /std:c++17 /O2 /MD /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS ^
  /I"%WEBOTS_HOME%\include\controller\c" ^
  /I"%NCNN_ROOT%\x64\include" ^
  my_controller.cpp ^
  /link /OUT:my_controller.exe ^
  /LIBPATH:"%WEBOTS_HOME%\lib\controller" ^
  /LIBPATH:"%NCNN_ROOT%\x64\lib" ^
  /LIBPATH:"%VULKAN_SDK%\Lib" ^
  Controller.lib Ws2_32.lib ncnn.lib glslang.lib SPIRV.lib OSDependent.lib MachineIndependent.lib GenericCodeGen.lib glslang-default-resource-limits.lib vulkan-1.lib

set "BUILD_RESULT=%ERRORLEVEL%"
popd
exit /b %BUILD_RESULT%
