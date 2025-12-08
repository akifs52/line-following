import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, QMutex
from ultralytics import YOLO
import torch
import time

class CameraThread(QThread):
    frame_ready = Signal(np.ndarray)
    error_occurred = Signal(str)
    
    def __init__(self, camera_url):
        super().__init__()
        self.camera_url = camera_url
        self.running = True
        self.cap = None
        self.frame = None
        self.mutex = QMutex()
        
    def run(self):
        try:
            self.cap = cv2.VideoCapture(self.camera_url)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer size
            if not self.cap.isOpened():
                raise RuntimeError("Kamera bağlantısı kurulamadı")
                
            while self.running:
                ret, frame = self.cap.read()
                if ret:
                    self.mutex.lock()
                    self.frame = frame.copy()
                    self.mutex.unlock()
                    self.frame_ready.emit(frame)
                else:
                    raise RuntimeError("Kameradan görüntü alınamadı")
                self.msleep(10)  # ~100 FPS max
                
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.release()
            
    def get_frame(self):
        self.mutex.lock()
        frame = self.frame.copy() if self.frame is not None else None
        self.mutex.unlock()
        return frame
            
    def release(self):
        self.running = False
        if hasattr(self, 'cap') and self.cap is not None:
            self.cap.release()
            self.cap = None

class ObjectDetector:
    def __init__(self, model_path="yolov8n.pt", device=None):
        if device is None:
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        self.model = YOLO(model_path)
        self.model.verbose = False
        self.names = self.model.names
        
    def detect(self, frame, conf=0.5, iou=0.45):
        """Run YOLO model inference on the input frame"""
        results = self.model(frame, conf=conf, iou=iou, device=self.device, verbose=False)
        return results[0] if results else None

def draw_bounding_boxes(frame, results, names, conf_threshold=0.5):
    """Draw bounding boxes and labels on the frame"""
    if results is None or not hasattr(results, 'boxes'):
        return frame
    
    # Process detections
    for box in results.boxes:
        conf = box.conf.item()
        if conf < conf_threshold:
            continue
            
        # Get box coordinates
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls_id = int(box.cls.item())
        label = names.get(cls_id, f"Class {cls_id}")
        
        # Draw rectangle and label
        color = (0, 255, 0)  # Green
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Create label with confidence
        label = f"{label} {conf:.2f}"
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
        cv2.putText(frame, label, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    
    return frame

def process_frame(frame, detector, frame_counter=0, show_fps=True):
    """Process a single frame with object detection"""
    if frame is None:
        return None, 0, 0, 0, None
    
    # Run object detection
    results = detector.detect(frame)
    
    # Draw bounding boxes
    if results is not None:
        frame = draw_bounding_boxes(frame, results, detector.names)
    
    # Calculate and display FPS
    fps = 0
    if show_fps and hasattr(process_frame, 'prev_time'):
        current_time = time.time()
        fps = 1 / (current_time - process_frame.prev_time)
        process_frame.prev_time = current_time
        #cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
         #          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    elif show_fps:
        process_frame.prev_time = time.time()
    
    return frame, fps, 0, 0, results

# For testing
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPixmap

    class CameraApp(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Camera Feed")
            self.setGeometry(100, 100, 800, 600)
            
            self.label = QLabel(self)
            self.label.setAlignment(Qt.AlignCenter)
            
            layout = QVBoxLayout()
            layout.addWidget(self.label)
            self.setLayout(layout)
            
            self.camera_thread = CameraThread(0)  # 0 for default camera
            self.camera_thread.frame_ready.connect(self.update_frame)
            self.camera_thread.error_occurred.connect(self.handle_error)
            self.camera_thread.start()
            
            self.detector = ObjectDetector()
            
        def update_frame(self, frame):
            # Process frame with object detection
            processed_frame, _, _, _, _ = process_frame(frame, self.detector)
            
            # Convert to QImage
            h, w, ch = processed_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(processed_frame.data, w, h, bytes_per_line, QImage.Format_BGR888)
            
            # Display image
            self.label.setPixmap(QPixmap.fromImage(qt_image).scaled(
                self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
        def handle_error(self, error_msg):
            print(f"Error: {error_msg}")
            self.close()
            
        def closeEvent(self, event):
            self.camera_thread.release()
            self.camera_thread.wait()
            event.accept()

    app = QApplication(sys.argv)
    window = CameraApp()
    window.show()
    sys.exit(app.exec())