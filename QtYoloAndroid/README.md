# QtYoloAndroid (qmake)

## Build
1. Open `QtYoloAndroid.pro` in Qt Creator.
2. Select an Android kit (Qt 6.8.1).
3. Export your trained `linen.pt` to NCNN assets:
   - `python QtYoloAndroid/scripts/export_linen_to_assets.py`
   - this updates `assets/yolo11.param` and `assets/yolo11.bin`
4. Copy NCNN headers and libs to:
   - `3rdparty/ncnn/include`
   - `3rdparty/ncnn/libs/<abi>`
5. Build and run on device.

## NCNN package included
- Source: `https://github.com/Tencent/ncnn/releases`
- Installed release tag: `20260113`
- Installed asset: `ncnn-20260113-android-vulkan.zip`

## Notes
- `YoloEngine` now runs real NCNN inference on Android (`out0` decode + NMS).
- Non-Android builds keep inference disabled by design.
