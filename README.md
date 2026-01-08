# Line Following Robot Project

## Overview
This project implements a line-following robot using computer vision techniques. It utilizes YOLO (You Only Look Once) for object detection and tracking.

## Author
[akifs52](https://github.com/akifs52)

## TCP Streaming Commands

The following commands are used for TCP video streaming using FFmpeg:

### Basic TCP Stream
```bash
ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -preset ultrafast -b:v 2M -f mpegts tcp://xxx.xxx.xxx.xxx:2002?listen=1
```

### Optimized Low Latency Stream
```bash
ffmpeg -f v4l2 -framerate 30 -video_size 640x480 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 500k -fflags nobuffer -flags low_delay -an -f mpegts tcp://xxx.xxx.xxx.xxx:2002?listen=1
```

### List Video Devices
```bash
v4l2-ctl --list-devices
```

### Test Recording (5 seconds)
```bash
ffmpeg -f v4l2 -t 5 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -b:v 500k -an output.mp4
```

### HTTP Stream URL
```
http://xxx.xxx.xxx.xxx:8080?action=stream
```

## MJPG-Streamer Setup

### Clone and Build MJPG-Streamer
```bash
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
make
sudo make install
```

### Run MJPG-Streamer
```bash
mjpg_streamer -i "input_uvc.so -d /dev/video0 -r 640x480 -f 30" \
              -o "output_http.so -p 8080 -w ./www"
```

## Project Files

- `CamDetection.py` - Camera detection module
- `main.py` - Main application entry point
- `path_angle_detector.py` - Path and angle detection logic
- `test_track_detector.py` - Testing module for tracking
- `train_yolov8n.py` - Training script for YOLOv8n
- `socket_client.py` - Socket communication client
- `frame_saver.py` - Frame saving utility
- `qt_angle_detector_gui.py` - Qt-based GUI application
- `raspiconfig.py` - Raspberry Pi configuration
- `best.pt` - Best trained model weights
- `yolo11n.pt` - YOLO11n model weights
- `yolov8n.pt` - YOLOv8n model weights

## Dataset
The project includes a custom dataset located in `my_dataset/` with:
- Training images and labels
- Test images and labels
- Dataset configuration files

## Installation

Install required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the main application:
```bash
python main.py
```

Or use the GUI version:
```bash
python qt_angle_detector_gui.py
```

## License
This project is open source and available for educational purposes.
