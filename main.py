from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                              QStatusBar, QLineEdit, QVBoxLayout, QWidget, 
                              QMessageBox, QDialog, QVBoxLayout, QHBoxLayout)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt, QUrl, QThread, Signal, QSize, QEvent, QMutex
from PySide6.QtGui import QImage, QPixmap, QColor, QMovie, QKeySequence
from PySide6.QtQuickWidgets import QQuickWidget
import sys
import torch
import cv2
import numpy as np
import time
import subprocess
from ultralytics import YOLO
from CamDetection import CameraThread, ObjectDetector, process_frame, draw_bounding_boxes
from frame_saver import FrameSaver

# ═══════════════════════════════════════════════════════════════
# YOLO DETECTION THREAD - Ayrı thread'te çalıştır
# ═══════════════════════════════════════════════════════════════
class YOLODetectionThread(QThread):
    """YOLO inference'ı ayrı thread'te çalıştır (UI'yi free tut)"""
    results_ready = Signal(object)  # (results)
    
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.current_frame = None
        self.running = True
        self.mutex = QMutex()
    
    def set_frame(self, frame):
        """Set current frame for processing"""
        self.mutex.lock()
        self.current_frame = frame.copy() if frame is not None else None
        self.mutex.unlock()
    
    def run(self):
        """Process frames continuously"""
        while self.running:
            self.mutex.lock()
            frame = self.current_frame
            self.mutex.unlock()
            
            if frame is not None:
                try:
                    results = self.detector.detect(frame)
                    self.results_ready.emit(results)
                except Exception as e:
                    print(f"[YOLO] Error: {e}")
            
            time.sleep(0.001)  # Prevent CPU spinning
    
    def stop(self):
        """Stop the thread"""
        self.running = False
        self.wait()

from socket_client import SocketClient

LABEL_TO_CMD = {
            "left": "L",
            "right": "R",
            "straight": "F",
        }

class MainWindow (QMainWindow):
    def __init__(self):
        super().__init__()

        loader = QUiLoader()
        ui_file = QFile("modern_mainwindow.ui")
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        
        # UI'yi göstermek için
        self.setCentralWidget(self.ui)

        # Widget erişimi (objectName ile)
        self.tcpCamBtn: QPushButton = self.ui.findChild(QPushButton, "tcpCamBtn")
        self.otonoumBtn: QPushButton = self.ui.findChild(QPushButton, "otonoumBtn")
        self.CamLabel: QLabel = self.ui.findChild(QLabel, "CamLabel")
        self.ipLineEdit : QLineEdit = self.ui.findChild(QLineEdit , "ipLineEdit")
        self.closeCam : QPushButton = self.ui.findChild(QPushButton, "closeCam")
        self.camPortLine : QLineEdit = self.ui.findChild(QLineEdit, "camPortLine")
        self.raspiPortLine : QLineEdit = self.ui.findChild(QLineEdit, "raspiPortLine")
        self.quickWidgetSlider1 = self.ui.findChild(QQuickWidget, "quickWidgetSlider1")
        self.quickWidgetJoystick = self.ui.findChild(QQuickWidget, "quickWidgetJoystick")
        self.settingsButton: QPushButton = self.ui.findChild(QPushButton, "settingsButton")
        
        # Son frame'i saklamak için (kaydetme butonu için)
        self.current_frame = None
        
        # Footer frame içindeki label'lar
        self.cudaLabel: QLabel = self.ui.findChild(QLabel, "cudaLabel")
        self.vramLabel: QLabel = self.ui.findChild(QLabel, "vramLabel")
        self.fpsLabel: QLabel = self.ui.findChild(QLabel, "fpsLabel")
        self.statusLabel: QLabel = self.ui.findChild(QLabel, "statusLabel")
        self.statusDot: QLabel = self.ui.findChild(QLabel, "statusDot")
        self.steeringStatusValue: QLabel = self.ui.findChild(QLabel, "steeringStatusValue")
        self.joystick_root = None
        self.joystick_active = False  # Track if joystick is being held
        self.last_command_time = 0
        
        if self.quickWidgetJoystick:
            try:
                self.quickWidgetJoystick.setResizeMode(QQuickWidget.SizeRootObjectToView)
                self.quickWidgetJoystick.setSource(QUrl.fromLocalFile("tools/ModernAnalogJoystick.qml"))
                self.joystick_root = self.quickWidgetJoystick.rootObject()
                
                # Connect joystick signals
                if hasattr(self.joystick_root, 'positionChanged'):
                    self.joystick_root.positionChanged.connect(self.on_joystick_moved)
                if hasattr(self.joystick_root, 'released'):
                    self.joystick_root.released.connect(self.on_joystick_released)
                    
                    # Initially enable joystick
                    self.quickWidgetJoystick.setEnabled(True)
                else:
                    print("Warning: Failed to get joystick root object")
                    
            except Exception as e:
                print(f"Error initializing joystick: {e}")
        else:
            print("Warning: quickWidgetJoystick not found in UI")

        self.closeCam.hide()

        # Kamera Thread
        self.camera_thread = None
        self.frame_saver = FrameSaver(interval=0.30)
        self.socket_client = None
        self.last_label = None


       
        self.quickWidgetSlider1.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.quickWidgetSlider1.setClearColor(QColor("#19243d"))
        self.quickWidgetSlider1.setAttribute(Qt.WA_TranslucentBackground)
        self.quickWidgetSlider1.setStyleSheet("background: #19243d; border: none;")
        self.quickWidgetSlider1.setSource(QUrl.fromLocalFile("tools/ModernCircularSlider.qml"))
        

         #slider renk ayarları

        self.rootSlider1 = self.quickWidgetSlider1.rootObject()
        
        self.rootSlider1.valueChanged.connect(self.on_slider_changed)

    
        self.setGeometry(self.ui.geometry())
        
        self.setWindowTitle("Otonoum Car UI")

         #Yolo Model

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print ("[INFO] Using:", device)
      
        # Load model with verbose=False to reduce output
        self.detector = ObjectDetector(model_path="lines.pt", device=device)
        self.device = device
        self.verbose = False  # Flag to control our own debug output

        # ✅ YOLO Detection Thread'i başlat
        self.yolo_thread = YOLODetectionThread(self.detector)
        self.yolo_thread.results_ready.connect(self.on_detection_results)
        self.yolo_thread.start()
        self.last_detection_results = None

        # Update device info in footer
        self.gpu_util_percent = None
        self.vram_usage_percent = None

        if device == "cuda:0":
            self.cudaLabel.setText("CUDA")
            self.cudaLabel.setStyleSheet("color: #10B981; border-radius: 4px;")
            self.vramLabel.setStyleSheet("color: #10B981; border-radius: 4px;")
        else:
            self.cudaLabel.setText("CPU")
            self.cudaLabel.setStyleSheet("color: #F59E0B; border-radius: 4px;")
            self.vramLabel.setText("N/A")
            self.vramLabel.setStyleSheet("color: #6B7280; border-radius: 4px;")

         #timer update frame
        self.timer = QTimer()
       

         #FPS için

        self.prev_time = time.time()
        self.fps_smooth = None
        
        # Initialize FPS label
        self.fpsLabel.setText("FPS: --")
        self.fpsLabel.setStyleSheet("color: #6B7280; border-radius: 4px;")

        # Refresh GPU stats every second
        self.gpu_timer = QTimer(self)
        self.gpu_timer.setInterval(1000)
        self.gpu_timer.timeout.connect(self.update_gpu_stats)
        self.gpu_timer.start()
        self.update_gpu_stats()

        self.tcpCamBtn.clicked.connect(self.start_camera)

        self.closeCam.clicked.connect(self.closeEvent)
        
        # Settings button -> frame capture
        if self.settingsButton:
            self.settingsButton.clicked.connect(self.capture_frame)
        
        # Autonomous mode flag
        self.autonomous_mode = False
        self.otonoumBtn.clicked.connect(self.toggle_autonomous_mode)
        
        # ══════════════════════════════════════════════════
        # ✅ OPTIMIZED PID PARAMETERS
        # ══════════════════════════════════════════════════
        self.pid_kp = 25.0
        self.pid_ki = 0.05
        self.pid_kd = 10.0
        self.pid_integral_limit = 30.0
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = time.time()
        
        # Motor hızları - çok hızlı başlamıyacak
        self.auto_base_speed = 40
        self.auto_min_speed = 35
        self.auto_max_speed = 50
        self.smoothed_speed = self.auto_base_speed
        
        # ROI
        self.roi_top_ratio = 0.55
        self.roi_bottom_ratio = 1.0
        
        # Adaptive Road Width
        self.estimated_half_road_width = None
        self.road_width_alpha = 0.1
        self.default_half_road_pct = 0.20
        
        # Yol kaybolma & Arama
        self.last_line_seen = time.time()
        self.no_line_timeout = 0.8
        self.search_turn_speed = 20     # ✅ DÜŞÜRÜLDÜ: 25 → 20
        self.search_dir = "left"
        self.last_seen_line_side = None
        
        # ✅ Socket spam kontrolü
        self.last_sent_cmd = None
        self.last_cmd_send_time = 0
        self.cmd_send_interval = 0.05   # ✅ Min 50ms ara aç (socket spam azalt)
        
        # Initialize status displays
        self.steeringStatusValue.setText("INACTIVE")
        self.steeringStatusValue.setStyleSheet("color: #FFFFFF; font-size: 10px; text-transform: uppercase;")
        self.update_status_display()
        
        # Enable keyboard focus for WASD controls
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Install event filter to capture keyboard events before QML widgets
        self.installEventFilter(self)
        
        # WASD key states
        self.wasd_pressed = {'W': False, 'A': False, 'S': False, 'D': False}
        
        # Timer for continuous movement
        self.wasd_timer = QTimer()
        self.wasd_timer.timeout.connect(self.process_wasd_movement)
        self.wasd_timer.start(50)  # 20Hz movement update
    
    def eventFilter(self, obj, event):
        """Event filter to capture keyboard events for joystick only"""
        if event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
            if self.autonomous_mode:
                return super().eventFilter(obj, event)

            # Ignore auto-repeat to prevent fake release/press spam
            if event.isAutoRepeat():
                return True

            key_map = {
                Qt.Key_W: "W",
                Qt.Key_A: "A",
                Qt.Key_S: "S",
                Qt.Key_D: "D",
            }
            key = key_map.get(event.key())
            if not key:
                return super().eventFilter(obj, event)

            is_press = (event.type() == QEvent.KeyPress)
            if is_press:
                print(f"Key pressed: {key}")  # Debug print
            else:
                print(f"Key released: {key}")  # Debug print

            self.wasd_pressed[key] = is_press
            print(f"WASD state updated: {self.wasd_pressed}")  # Debug print

            # Update QML joystick properties
            if hasattr(self, 'joystick_root') and self.joystick_root:
                if key == 'W':
                    self.joystick_root.setProperty("wPressed", is_press)
                elif key == 'A':
                    self.joystick_root.setProperty("aPressed", is_press)
                elif key == 'S':
                    self.joystick_root.setProperty("sPressed", is_press)
                elif key == 'D':
                    self.joystick_root.setProperty("dPressed", is_press)

            return True  # Event handled

        return super().eventFilter(obj, event)
    
    def update_status_display(self):
        """Update all status displays based on current system state"""
        # Check camera and socket status
        camera_ready = (hasattr(self, 'camera_thread') and 
                    self.camera_thread and 
                    self.camera_thread.isRunning())
        
        socket_ready = (hasattr(self, 'socket_client') and 
                    self.socket_client and 
                    self.socket_client.connected)
        
        # Update main status
        if camera_ready and socket_ready:
            self.statusLabel.setText("SYSTEM READY")
            self.statusLabel.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 500;")
            self.statusDot.setStyleSheet("background-color: #10B981; border-radius: 3px; min-width: 6px; min-height: 6px;")
        else:
            self.statusLabel.setText("SYSTEM WAITING")
            self.statusLabel.setStyleSheet("color: #F59E0B; font-size: 12px; font-weight: 500;")
            self.statusDot.setStyleSheet("background-color: #F59E0B; border-radius: 3px; min-width: 6px; min-height: 6px;")
        
        # Update steering status
        print(f"DEBUG: autonomous_mode = {self.autonomous_mode}")  # Debug print
        if not self.autonomous_mode:  # Manual mode = ACTIVE
            print("DEBUG: Setting steering to ACTIVE")  # Debug print
            self.steeringStatusValue.setText("ACTIVE")
            self.steeringStatusValue.setStyleSheet("color: #10B981; font-size: 10px; text-transform: uppercase;")
        else:  # Autonomous mode = INACTIVE
            print("DEBUG: Setting steering to INACTIVE")  # Debug print
            self.steeringStatusValue.setText("INACTIVE")
            self.steeringStatusValue.setStyleSheet("color: #FFFFFF; font-size: 10px; text-transform: uppercase;")
    
    def process_wasd_movement(self):
        """Process WASD movement when keys are pressed"""
        if self.autonomous_mode:
            return  # Disable WASD in autonomous mode
            
        if not hasattr(self, 'socket_client') or not self.socket_client:
            return
            
        # Check which keys are pressed and send appropriate commands
        if self.wasd_pressed['W']:
            print("Sending command: F (Forward)")  # Debug print
            self.socket_client.send_command("F")  # Forward
        elif self.wasd_pressed['S']:
            print("Sending command: B (Backward)")  # Debug print
            self.socket_client.send_command("B")  # Backward
        elif self.wasd_pressed['A']:
            print("Sending command: L (Left)")  # Debug print
            self.socket_client.send_command("L")  # Left
        elif self.wasd_pressed['D']:
            print("Sending command: R (Right)")  # Debug print
            self.socket_client.send_command("R")  # Right
        else:
            print("Sending command: S (Stop)")  # Debug print
            self.socket_client.send_command("S")  # Stop
    
    def show_loading_dialog(self, message):
        """Show a loading dialog with the given message"""
        from PySide6 import QtWidgets, QtCore
        from PySide6.QtQuickWidgets import QQuickWidget
        from loading_dialog_ui import Ui_LoadingDialog
        
        self.loading_dialog = QtWidgets.QDialog(self)
        self.loading_ui = Ui_LoadingDialog()
        self.loading_ui.setupUi(self.loading_dialog)
        
        # Set custom message if provided
        if message:
            self.loading_ui.message_label.setText(message)
        
        # Add QML loading animation
        self.loading_widget = QQuickWidget(self.loading_dialog)
        self.loading_widget.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.loading_widget.setSource(QtCore.QUrl.fromLocalFile("tools/LoadingCircle.qml"))
        self.loading_widget.setFixedSize(48, 48)
        
        # Make QQuickWidget background transparent
        from PySide6.QtGui import QColor
        self.loading_widget.setClearColor(QColor("#111827"))
        self.loading_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.loading_widget.setStyleSheet("background: transparent;")
        
        # Replace the loading label with the QML widget
        self.loading_ui.loading_label.setParent(None)
        self.loading_ui.loading_label.deleteLater()
        
        # Add QML widget to the layout
        layout = self.loading_ui.contentLayout
        layout.insertWidget(0, self.loading_widget)
        layout.setAlignment(self.loading_widget, QtCore.Qt.AlignCenter)
        
        self.loading_dialog.show()
    
    def close_loading_dialog(self):
        """Close the loading dialog if it's open"""
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.loading_dialog.accept()
            self.loading_dialog = None
    
    def check_connections(self):
        
        # Check camera status
        camera_ready = (hasattr(self, 'camera_thread') and 
                    self.camera_thread and 
                    self.camera_thread.isRunning())
        
        socket_ready = (hasattr(self, 'socket_client') and 
                    self.socket_client and 
                    self.socket_client.connected)
        
        # Update status display
        self.update_status_display()
        
        # If both are ready, start the timer and close loading dialog
        if camera_ready and socket_ready:
            self.close_loading_dialog()
            if not self.timer.isActive():
                self.timer.start(30)
            return
        
        # If camera is not ready but socket is, show camera error
        if not camera_ready and socket_ready:
            if not hasattr(self, '_camera_error_shown'):
                self._camera_error_shown = True
                QMessageBox.critical(self, "Kamera Hatası", "Kamera başlatılamadı!")
            if not self.timer.isActive():
                self.timer.start(30)  # Start timer anyway to show error on screen
            QTimer.singleShot(100, self.check_connections)
            return
        
        # If socket is not ready but camera is, show socket error
        if camera_ready and not socket_ready:
            if not hasattr(self, '_socket_error_shown'):
                self._socket_error_shown = True
                QMessageBox.critical(self, "Bağlantı Hatası", "Sunucuya bağlanılamadı!")
            if not self.timer.isActive():
                self.timer.start(30)  # Start timer anyway to show camera feed
            QTimer.singleShot(100, self.check_connections)
            return
        
        # If neither is ready, keep checking
        QTimer.singleShot(100, self.check_connections)

    def start_camera(self):
        if not self.ipLineEdit.text():
            QMessageBox.warning(self, "Hata", "IP adresi boş olamaz!")
            return

        try:
            ip = self.ipLineEdit.text()
            camport = self.camPortLine.text()
            raspiport = int(self.raspiPortLine.text())
            fullipCam = "tcp://"+ ip + f":" + camport 
            
            # Show loading dialog
            self.show_loading_dialog("Kamera ve bağlantılar başlatılıyor...")
            
            print("[INFO] Starting Camera Thread...")
            
            # Stop previous camera thread if exists
            if hasattr(self, 'camera_thread') and self.camera_thread:
                self.camera_thread.release()
                self.camera_thread.wait()
            
            # Start new camera thread
            self.camera_thread = CameraThread(fullipCam)
            self.camera_thread.frame_ready.connect(self.on_frame_received)
            self.camera_thread.error_occurred.connect(self.handle_camera_error)
            self.camera_thread.start()
            
            # Start socket client
            if not hasattr(self, 'socket_client') or not self.socket_client:
                self.socket_client = SocketClient(ip, raspiport)
                self.socket_client.connect()
            
            # Start checking connections
            QTimer.singleShot(1000, self.check_connections)
            
        except Exception as e:
            self.close_loading_dialog()
            QMessageBox.critical(self, "Hata", f"Başlatma hatası: {str(e)}")
    
    # ─── PID Hesaplama ────────────────────────────────────────
    def pid_compute(self, error):
        """PID hesapla → (output, p, i, d)"""
        now = time.time()
        dt = now - self.pid_last_time
        if dt <= 0:
            dt = 0.01
        self.pid_last_time = now

        p = self.pid_kp * error

        self.pid_integral += error * dt
        self.pid_integral = max(-self.pid_integral_limit,
                                min(self.pid_integral_limit, self.pid_integral))
        i = self.pid_ki * self.pid_integral

        derivative = (error - self.pid_prev_error) / dt
        d = self.pid_kd * derivative
        self.pid_prev_error = error

        return p + i + d, p, i, d

    def pid_reset(self):
        """PID durumunu sıfırla"""
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = time.time()

    # ─── Dual-Line: Tüm Çizgi Merkezlerini Bul ─────────────────
    def find_line_centers(self, masks, boxes, frame_shape):
        """
        YOLO'dan gelen tüm 'line' maskelerini ayrı ayrı işle.
        Her maskenin ROI bölgesindeki x-center'ını bul.
        
        Return: [(cx1, cy1, mask1), (cx2, cy2, mask2), ...]
                Sol → Sağ sıralı (cx'e göre)
                Boş liste → hiçbir çizgi bulunamadı
        """
        if masks is None or len(masks.data) == 0:
            return []

        h, w = frame_shape[:2]
        roi_top = int(h * self.roi_top_ratio)
        roi_bottom = int(h * self.roi_bottom_ratio)
        
        line_data = []
        
        for idx, mask_tensor in enumerate(masks.data):
            # Güven kontrolü — eşleşen box varsa conf kontrol et
            if boxes is not None and idx < len(boxes):
                conf = boxes[idx].conf.item()
                if conf < 0.40:
                    continue
            
            mask_np = mask_tensor.cpu().numpy()
            mask_resized = cv2.resize(mask_np, (w, h),
                                      interpolation=cv2.INTER_NEAREST)
            mask_binary = (mask_resized > 0.5).astype(np.uint8)
            
            # Genel alan kontrolü
            if np.sum(mask_binary) < 50:
                continue
            
            # ROI uygula
            roi_mask = mask_binary.copy()
            roi_mask[:roi_top, :] = 0
            roi_mask[roi_bottom:, :] = 0
            
            if np.sum(roi_mask) < 30:
                continue
            
            M = cv2.moments(roi_mask, binaryImage=True)
            if M["m00"] == 0:
                continue
            
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            line_data.append((cx, cy, mask_binary))
        
        # Sol → Sağ sırala (cx'e göre)
        line_data.sort(key=lambda item: item[0])
        return line_data

    def compute_steering_error(self, line_centers, frame_shape):
        """
        Çizgi merkezlerinden direksiyon hatasını hesapla.
        
        3 Senaryo:
          2 çizgi: error = midpoint(sol, sağ) - frame_center
          1 çizgi (sol): error = (cx + offset) - frame_center
          1 çizgi (sağ): error = (cx - offset) - frame_center
          0 çizgi: None (arama modu)
        
        Return: (error_normalized, target_cx, mode_str) veya (None, None, mode_str)
                error_normalized: -1.0 ... +1.0
                target_cx: hedef piksel x-koordinatı
                mode_str: "2-LINE" / "1-LINE-L" / "1-LINE-R" / "SEARCH"
        """
        h, w = frame_shape[:2]
        center_x = w // 2
        half_w = w / 2
        
        # Fallback half road width
        half_road = self.estimated_half_road_width
        if half_road is None:
            half_road = w * self.default_half_road_pct
        
        if len(line_centers) == 0:
            return None, None, "SEARCH"
        
        elif len(line_centers) >= 2:
            # 2+ çizgi: en sol ve en sağ al
            left_cx = line_centers[0][0]
            right_cx = line_centers[-1][0]
            
            # Adaptive road width güncelleme (EMA)
            gap = right_cx - left_cx
            if gap > 20:  # Minimum anlamlı mesafe
                new_half = gap / 2.0
                if self.estimated_half_road_width is None:
                    self.estimated_half_road_width = new_half
                else:
                    self.estimated_half_road_width = (
                        (1 - self.road_width_alpha) * self.estimated_half_road_width +
                        self.road_width_alpha * new_half
                    )
            
            target_cx = (left_cx + right_cx) // 2
            error = (target_cx - center_x) / half_w
            
            self.last_seen_line_side = "both"
            return error, target_cx, "2-LINE"
        
        else:  # 1 çizgi
            cx = line_centers[0][0]
            
            if cx < center_x:
                # Sol çizgi → hedef sağa kaydır
                target_cx = int(cx + half_road)
                self.last_seen_line_side = "left"
                mode_str = "1-LINE-L"
            else:
                # Sağ çizgi → hedef sola kaydır
                target_cx = int(cx - half_road)
                self.last_seen_line_side = "right"
                mode_str = "1-LINE-R"
            
            error = (target_cx - center_x) / half_w
            return error, target_cx, mode_str

    def get_dual_row_centers(self, line_centers, frame_shape, num_rows=5):
        """
        Look-ahead: Maskeleri yatay dilimlere böl → curvature tahmini.
        Her dilimde 2 çizgi varsa midpoint, 1 çizgi varsa offset hesapla.
        """
        h, w = frame_shape[:2]
        center_x = w // 2
        roi_top = int(h * self.roi_top_ratio)
        roi_bottom = int(h * self.roi_bottom_ratio)
        roi_height = roi_bottom - roi_top
        if roi_height <= 0:
            return []
        
        half_road = self.estimated_half_road_width
        if half_road is None:
            half_road = w * self.default_half_road_pct
        
        # Tüm maskeleri topla
        all_masks = [item[2] for item in line_centers if item[2] is not None]
        if not all_masks:
            return []
        
        row_height = roi_height // num_rows
        centers = []
        
        for i in range(num_rows):
            y_start = roi_top + i * row_height
            y_end = y_start + row_height
            
            # Bu dilimde her maskenin centroid'ini bul
            slice_cxs = []
            for mask in all_masks:
                row_slice = mask[y_start:y_end, :]
                if np.sum(row_slice) < 10:
                    continue
                M = cv2.moments(row_slice, binaryImage=True)
                if M["m00"] == 0:
                    continue
                slice_cx = int(M["m10"] / M["m00"])
                slice_cxs.append(slice_cx)
            
            if not slice_cxs:
                continue
            
            cy = y_start + row_height // 2
            
            if len(slice_cxs) >= 2:
                # 2+ çizgi → midpoint
                slice_cxs.sort()
                target = (slice_cxs[0] + slice_cxs[-1]) // 2
            else:
                # 1 çizgi → offset uygula
                cx_single = slice_cxs[0]
                if cx_single < center_x:
                    target = int(cx_single + half_road)
                else:
                    target = int(cx_single - half_road)
            
            centers.append((target, cy))
        
        return centers

    def apply_deadzone(self, speed):
        """Uygulanan PID deadzone yumuşatması"""
        if abs(speed) < 40:
            return 0 if abs(speed) < 15 else (self.auto_min_speed if speed > 0 else -self.auto_min_speed)
        return speed

    # ═══════════════════════════════════════════════════════════
    # ✅ DETECTION RESULTS HANDLER - Separation of concerns
    # ═══════════════════════════════════════════════════════════
    def on_detection_results(self, results):
        """Handle YOLO detection results (from separate thread)"""
        self.last_detection_results = results

    # ─── Görüntü İşleme + Otonom/Manuel ───────────────────────
    def on_frame_received(self, frame):
        """Handle frame received from camera thread"""
        try:
            self.current_frame = frame.copy()
            
            # Feed frame to YOLO thread (non-blocking)
            self.yolo_thread.set_frame(frame)
            
            # Use last detection results
            results = self.last_detection_results

            # Kendimiz FPS hesaplayalım (bloklamamak için process_frame çağırmıyoruz)
            fps = 0
            if hasattr(self, 'prev_time'):
                current_time = time.time()
                fps = 1 / (current_time - self.prev_time)
                self.prev_time = current_time
            else:
                self.prev_time = time.time()

            processed_frame = frame.copy()
            if results is not None:
                processed_frame = draw_bounding_boxes(processed_frame, results, self.detector.names)

            h, w = frame.shape[:2]
            center_x = w // 2

            # ── Otonom Mod: Dual-Line PID → DIFF komutu gönder ──
            if self.autonomous_mode and results is not None:
                masks = results.masks if hasattr(results, 'masks') and results.masks is not None else None
                boxes = results.boxes if hasattr(results, 'boxes') and results.boxes is not None else None

                # En yüksek güven değerini bul (debug amaçlı)
                best_conf = 0.0
                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        conf = box.conf.item()
                        if conf > best_conf:
                            best_conf = conf

                # ── Tüm çizgi merkezlerini bul ──
                line_centers = self.find_line_centers(masks, boxes, frame.shape)
                
                # ── Direksiyon hatasını hesapla ──
                error, target_cx, mode_str = self.compute_steering_error(
                    line_centers, frame.shape
                )

                debug_text = []
                num_lines = len(line_centers)

                if error is not None and target_cx is not None:
                    # ── Çizgi(ler) bulundu ──
                    self.last_line_seen = time.time()

                    # Look-ahead curvature analizi
                    curvature = 0.0
                    if line_centers:
                        row_centers = self.get_dual_row_centers(
                            line_centers, frame.shape, 5
                        )
                        if len(row_centers) >= 3:
                            curvature = (row_centers[-1][0] - row_centers[0][0]) / w
                            error += curvature * 0.15

                    # PID hesapla
                    pid_out, p_val, i_val, d_val = self.pid_compute(error)
                    pid_out = max(-100, min(100, pid_out))
                    pid_out = float(np.tanh(pid_out / 90.0)) * 100.0

                    # Curvature hız kontrolü (İptal edildi, düz hız ile dönüş hızı aynı)
                    curvature_abs = abs(curvature)
                    slow_factor = 1.0  # Düz hız ile aynı
                    dynamic_base = self.auto_base_speed * slow_factor
                    
                    alpha_spd = 0.1
                    self.smoothed_speed = (1 - alpha_spd) * self.smoothed_speed + alpha_spd * dynamic_base
                    dynamic_base = self.smoothed_speed
                    
                    # Motor hızları (Yönler terslendi)
                    speed_l = dynamic_base - pid_out
                    speed_r = dynamic_base + pid_out
                    
                    speed_l = max(-self.auto_max_speed, min(self.auto_max_speed, speed_l))
                    speed_r = max(-self.auto_max_speed, min(self.auto_max_speed, speed_r))

                    speed_l = self.apply_deadzone(speed_l)
                    speed_r = self.apply_deadzone(speed_r)

                    # Arama yönünü güncelle (fallback)
                    if error > 0.1:
                        self.search_dir = "right"
                    elif error < -0.1:
                        self.search_dir = "left"

                    # ✅ Socket spam kontrolü - en az 50ms ara
                    now = time.time()
                    cmd = f"DIFF,{round(speed_l)},{round(speed_r)}"
                    if cmd != self.last_sent_cmd and (now - self.last_cmd_send_time) > self.cmd_send_interval:
                        self.last_sent_cmd = cmd
                        self.last_cmd_send_time = now
                        if self.socket_client and self.socket_client.connected:
                            self.socket_client.send_command(f"DIFF,{speed_l:.1f},{speed_r:.1f}")

                    # ─── VİZÜELİZASYON ───
                    # Frame merkez çizgisi (beyaz)
                    cv2.line(processed_frame, (center_x, 0), (center_x, h),
                             (255, 255, 255), 1)
                    
                    # Çizgi merkezlerini çiz
                    for idx, (lcx, lcy, _) in enumerate(line_centers):
                        if idx == 0 and num_lines >= 2:
                            # Sol çizgi → Mavi
                            cv2.circle(processed_frame, (lcx, lcy), 8,
                                       (255, 0, 0), -1)
                            cv2.putText(processed_frame, "L",
                                        (lcx - 5, lcy - 12),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                        (255, 0, 0), 2)
                        elif idx == num_lines - 1 and num_lines >= 2:
                            # Sağ çizgi → Yeşil
                            cv2.circle(processed_frame, (lcx, lcy), 8,
                                       (0, 255, 0), -1)
                            cv2.putText(processed_frame, "R",
                                        (lcx - 5, lcy - 12),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                        (0, 255, 0), 2)
                        else:
                            # Tek çizgi veya ekstra → Cyan
                            cv2.circle(processed_frame, (lcx, lcy), 8,
                                       (0, 255, 255), -1)
                    
                    # Hesaplanan hedef merkez (sarı)
                    target_cy = line_centers[0][1] if line_centers else h // 2
                    cv2.circle(processed_frame, (target_cx, target_cy), 12,
                               (0, 255, 255), 3)
                    cv2.drawMarker(processed_frame, (target_cx, target_cy),
                                   (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
                    
                    # Offset oku (hedef → merkez)
                    cv2.arrowedLine(processed_frame, (center_x, target_cy),
                                    (target_cx, target_cy), (0, 0, 255), 2)
                    
                    # 1-çizgi modunda tahmini yol sınırı (kesikli çizgi)
                    if num_lines == 1 and self.estimated_half_road_width is not None:
                        lcx_single = line_centers[0][0]
                        lcy_single = line_centers[0][1]
                        half_r = int(self.estimated_half_road_width)
                        # Tahmini karşı çizgi konumu
                        if mode_str == "1-LINE-L":
                            est_x = lcx_single + half_r * 2
                        else:
                            est_x = lcx_single - half_r * 2
                        # Kesikli dikey çizgi
                        for dy in range(0, h, 12):
                            y1d = dy
                            y2d = min(dy + 6, h)
                            cv2.line(processed_frame, (est_x, y1d),
                                     (est_x, y2d), (0, 200, 200), 1)

                    # Mod göstergesi
                    mode_color = {
                        "2-LINE": (0, 255, 0),
                        "1-LINE-L": (255, 165, 0),
                        "1-LINE-R": (0, 165, 255),
                    }.get(mode_str, (200, 200, 200))
                    cv2.putText(processed_frame, mode_str, (w - 150, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, mode_color, 2)
                    
                    # Estimated half road width bilgisi
                    hrw_text = f"HRW: {self.estimated_half_road_width:.0f}px" if self.estimated_half_road_width else "HRW: ---"
                    
                    debug_text = [
                        f"MODE: {mode_str} | LINES: {num_lines}",
                        f"TARGET: {target_cx:3d} | CENTER: {center_x:3d} | OFFSET: {target_cx-center_x:+4d}",
                        f"ERROR: {error:+.3f} | CURVE: {curvature:+.3f}",
                        f"PID: {pid_out:+.1f} (P:{p_val:+.2f} I:{i_val:+.2f} D:{d_val:+.2f})",
                        f"MOTOR L: {speed_l:+6.1f} | MOTOR R: {speed_r:+6.1f}",
                        f"BASE: {self.smoothed_speed:.1f} | CONF: {best_conf:.2f} | {hrw_text}",
                    ]

                else:
                    # ── Arama Modu (0 çizgi) ──
                    elapsed = time.time() - self.last_line_seen
                    now = time.time()
                    if self.socket_client and self.socket_client.connected:
                        if elapsed < self.no_line_timeout:
                            # Kısa süre: düz devam et
                            cmd = f"DIFF,{self.auto_min_speed},{self.auto_min_speed}"
                        elif elapsed < self.no_line_timeout * 3:
                            # Arama: son görülen çizgiye doğru dön
                            if self.last_seen_line_side == "left":
                                # Sol çizgi kaybolduysa sola dön (çizgiyi bulmak için)
                                cmd = f"DIFF,{-self.search_turn_speed},{self.search_turn_speed}"
                            elif self.last_seen_line_side == "right":
                                # Sağ çizgi kaybolduysa sağa dön
                                cmd = f"DIFF,{self.search_turn_speed},{-self.search_turn_speed}"
                            else:
                                # Fallback: eski search_dir kullan
                                if self.search_dir == "left":
                                    cmd = f"DIFF,{-self.search_turn_speed},{self.search_turn_speed}"
                                else:
                                    cmd = f"DIFF,{self.search_turn_speed},{-self.search_turn_speed}"
                        else:
                            cmd = "S"
                        
                        if cmd != self.last_sent_cmd and (now - self.last_cmd_send_time) > self.cmd_send_interval:
                            self.last_sent_cmd = cmd
                            self.last_cmd_send_time = now
                            self.socket_client.send_command(cmd)

                    # Arama modu vizüelizasyonu
                    search_side = self.last_seen_line_side or self.search_dir
                    cv2.putText(processed_frame, f"SEARCH ({search_side})",
                                (w - 220, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 0, 255), 2)
                    cv2.putText(processed_frame, "ARAMA MODU", (20, h - 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    debug_text = [
                        f"SEARCH | CONF: {best_conf:.2f} | SIDE: {search_side}",
                        f"Elapsed: {elapsed:.1f}s / timeout: {self.no_line_timeout:.1f}s",
                    ]

                # ROI çizgisi
                roi_y = int(h * self.roi_top_ratio)
                cv2.line(processed_frame, (0, roi_y), (w, roi_y),
                         (255, 255, 0), 1)
                
                # DEBUG YAZISI
                y_offset = 30
                for i, text in enumerate(debug_text):
                    cv2.putText(processed_frame, text, (10, y_offset + i * 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                (200, 200, 200), 1)
                
                # Merkez çizgisi (ROI'den alta)
                cv2.line(processed_frame, (center_x, roi_y), (center_x, h),
                         (0, 165, 255), 1)

            elif self.autonomous_mode and results is None:
                # Otonom ama algılama yok
                if self.socket_client and self.socket_client.connected:
                    self.socket_client.send_command("S")

            # Update FPS display
            gpu_memory_percent = f"{self.vram_usage_percent:.0f}%" if self.vram_usage_percent is not None else "--%"
            mode_text = "AUTO" if self.autonomous_mode else "MANUAL"
            if fps > 0:
                self.fpsLabel.setText(f"FPS: {fps:.0f} | Mode: {mode_text} | VRAM: {gpu_memory_percent}")
                self.fpsLabel.setStyleSheet("color: #10B981; border-radius: 4px;")
            else:
                self.fpsLabel.setText(f"FPS: -- | Mode: {mode_text} | VRAM: --%")
                self.fpsLabel.setStyleSheet("color: #6B7280; border-radius: 4px;")

            # Convert frame to QImage
            h, w, ch = processed_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(processed_frame.data, w, h, bytes_per_line, QImage.Format_BGR888)

            # Display image
            self.CamLabel.setPixmap(QPixmap.fromImage(qt_image).scaled(
                self.CamLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))

        except Exception as e:
            print(f"Error in on_frame_received: {str(e)}")


    def update_gpu_stats(self):
        """Update GPU utilization + VRAM usage every second."""
        if not torch.cuda.is_available():
            self.gpu_util_percent = None
            self.vram_usage_percent = None
            self.vramLabel.setText("N/A")
            self.vramLabel.setStyleSheet("color: #6B7280; border-radius: 4px;")
            return

        # Preferred: query driver metrics (matches Task Manager behavior better).
        try:
            result = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                    "-i",
                    "0",
                ],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.5,
            ).strip()

            util_str, mem_used_str, mem_total_str = [x.strip() for x in result.split(",")]
            util = float(util_str)
            mem_used = float(mem_used_str)
            mem_total = float(mem_total_str)
            mem_percent = (mem_used / mem_total * 100.0) if mem_total > 0 else 0.0

            self.gpu_util_percent = util
            self.vram_usage_percent = mem_percent
            self.vramLabel.setText(f"GPU: {util:.0f}% | VRAM: {mem_used/1024:.1f}/{mem_total/1024:.1f} GB")
            self.vramLabel.setStyleSheet("color: #10B981; border-radius: 4px;")
            return
        except Exception:
            pass

        # Fallback: Torch memory-only stats.
        try:
            mem_total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            mem_used_gb = torch.cuda.memory_allocated() / 1024**3
            mem_percent = (mem_used_gb / mem_total_gb * 100.0) if mem_total_gb > 0 else 0.0

            self.gpu_util_percent = None
            self.vram_usage_percent = mem_percent
            self.vramLabel.setText(f"VRAM: {mem_used_gb:.1f}/{mem_total_gb:.1f} GB ({mem_percent:.0f}%)")
            self.vramLabel.setStyleSheet("color: #10B981; border-radius: 4px;")
        except Exception:
            self.gpu_util_percent = None
            self.vram_usage_percent = None
            self.vramLabel.setText("GPU not recognized")
            self.vramLabel.setStyleSheet("color: #F59E0B; border-radius: 4px;")
    
    
    
    def handle_camera_error(self, error_msg):
        """Handle camera thread errors"""
        self.close_loading_dialog()
        QMessageBox.critical(self, "Kamera Hatası", error_msg)
        self.close_camera()
    
    
    
    def close_camera(self):
        """Close camera thread and related resources"""
        if hasattr(self, 'camera_thread') and self.camera_thread:
            self.camera_thread.release()
            self.camera_thread.wait()
            self.camera_thread = None
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        self.close_loading_dialog()
    

    def capture_frame(self):
        """Manuel frame kaydetme - settings butonuna basıldığında çağrılır"""
        if self.current_frame is not None:
            path = self.frame_saver.save_now(self.current_frame)
            if path:
                print(f"[CAPTURE] Frame kaydedildi: {path}")
        else:
            print("[CAPTURE] Kaydedilecek frame yok!")
    
    def on_slider_changed(self):
        """Handle circular slider changes - only sends PWM speed commands"""
        v = int(self.rootSlider1.property("value"))
        
        # Update slider color based on value
        if v < 85:
            self.rootSlider1.setProperty("progressColor", QColor("#ff5252"))
        elif v < 170:
            self.rootSlider1.setProperty("progressColor", QColor("#ffca28"))
        else:
            self.rootSlider1.setProperty("progressColor", QColor("#66bb6a"))
            
        # Send ONLY PWM value through socket if connected
        # This slider should NOT send movement commands, only speed
        if hasattr(self, 'socket_client') and self.socket_client and self.socket_client.connected:
            # Send value in format "PWM{value}" where value is 0-255
            self.socket_client.send_command(f"PWM{v}")
            print(f"[SLIDER] Speed changed to PWM{v} ({int(v/255*100)}%)")

    def toggle_autonomous_mode(self):
        """Toggle autonomous mode (PID runs on PC, DIFF commands sent to Pi)"""
        self.autonomous_mode = not self.autonomous_mode
        
        if self.autonomous_mode:
            # Otonom başlıyor → her şeyi sıfırla
            self.pid_reset()
            self.last_line_seen = time.time()
            self.last_sent_cmd = None
            self.last_seen_line_side = None
            self.estimated_half_road_width = None
            
            # Disable manual control when in autonomous mode
            if hasattr(self, 'quickWidgetJoystick'):
                self.quickWidgetJoystick.setEnabled(False)
            self.otonoumBtn.setStyleSheet("background-color: green; color: white;")
            # Clear WASD states when entering autonomous mode
            for key in self.wasd_pressed:
                self.wasd_pressed[key] = False
            print("[MOD] ═══ OTONOM BAŞLADI (Dual-Line PID on PC) ═══")
        else:
            # Manuel moda dön → dur + sıfırla
            self.last_sent_cmd = None
            if hasattr(self, 'socket_client') and self.socket_client and self.socket_client.connected:
                self.socket_client.send_command("S")
            
            # Enable manual control
            if hasattr(self, 'quickWidgetJoystick'):
                self.quickWidgetJoystick.setEnabled(True)
            self.otonoumBtn.setStyleSheet("")
            print("[MOD] ═══ MANUEL MODA GEÇİLDİ ═══")
        
        # Update status display
        self.update_status_display()
        
    
    def on_joystick_moved(self, x, y):
        """Handle joystick movement in manual mode"""
        import time
        current_time = time.time()
        
        if not self.autonomous_mode and hasattr(self, 'socket_client') and self.socket_client:
            deadzone = 0.1
            
            # Check if joystick is in deadzone
            if abs(x) < deadzone and abs(y) < deadzone:
                if self.joystick_active:  # Only send stop if joystick was previously active
                    cmd = "S"
                    self.socket_client.send_command(cmd)
                    print(f"[JOYSTICK] Entering deadzone, sending: {cmd}")
                self.joystick_active = False
            else:
                # Joystick is outside deadzone
                if abs(y) >= abs(x):
                    cmd = "F" if y > 0 else "B"
                else:
                    cmd = "R" if x > 0 else "L"
                
                # Only send command if it's different or enough time has passed
                if not self.joystick_active or (current_time - self.last_command_time > 0.1):
                    self.socket_client.send_command(cmd)
                    print(f"[JOYSTICK] Movement: {cmd} (x={x:.2f}, y={y:.2f})")
                    self.last_command_time = current_time
                
                self.joystick_active = True
    
    def on_joystick_released(self):
        """Handle joystick release - stop the vehicle"""
        if hasattr(self, 'socket_client') and self.socket_client:
            self.socket_client.send_command("S")
            self.joystick_active = False
            print("[JOYSTICK] Released, sending STOP")
    
    def closeEvent(self, event):
        # Stop YOLO thread
        if hasattr(self, 'yolo_thread') and self.yolo_thread:
            self.yolo_thread.stop()
            
        # Close camera thread if running
        self.close_camera()

        if hasattr(self, 'gpu_timer') and self.gpu_timer.isActive():
            self.gpu_timer.stop()
            
        # Stop WASD timer
        if hasattr(self, 'wasd_timer') and self.wasd_timer.isActive():
            self.wasd_timer.stop()
        
        # Close socket connection if exists
        if hasattr(self, 'socket_client') and self.socket_client:
            self.socket_client.close()
            
        # Close loading dialog if open
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.close_loading_dialog()
            
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
