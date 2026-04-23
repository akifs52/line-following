# -*- mode: python ; coding: utf-8 -*-

import sys
sys.setrecursionlimit(5000)

block_cipher = None

# Data files - (source, destination)
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icons', 'icons'),
        ('tools', 'tools'),
        ('modern_mainwindow.ui', '.'),
        ('loading_dialog.ui', '.'),
        ('icons.qrc', '.'),
        ('lines.pt', '.'),
        ('linem.pt', '.'),
        ('linen.pt', '.'),
    ],
    hiddenimports=[
        'torch',
        'torchvision',
        'cv2',
        'numpy',
        'ultralytics',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtUiTools',
        'CamDetection',
        'frame_saver',
        'socket_client',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['runtime_hook.py'],
    excludes=[
        'matplotlib.tests',
        'numpy.random._examples',
        'pandas.tests',
        'scipy.tests',
        'PIL._tkinter_finder',
        'tkinter',
        'test',
        'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OtonomCarUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/luxury-car.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OtonomCarUI',
)
