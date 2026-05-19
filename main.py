from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                              QStatusBar, QLineEdit, QVBoxLayout, QWidget, 
                              QMessageBox, QDialog, QVBoxLayout, QHBoxLayout)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt, QUrl, QThread, Signal, QSize, QEvent, QMutex
from PySide6.QtGui import QImage, QPixmap, QColor, QMovie, QKeySequence, QIcon
from PySide6.QtQuickWidgets import QQuickWidget
import sys
import os
import ctypes
import torch

# PyInstaller veya kaynak kod için resource yolunu al
def get_resource_path(relative_path):
    """PyInstaller _MEIPASS veya kaynak dizin için yol döndür"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller paketlenmiş uygulama
        return os.path.join(sys._MEIPASS, relative_path)
    # Kaynak kod
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

import cv2
import numpy as np
import time
import subprocess
import collections
from ultralytics import YOLO
from CamDetection import CameraThread, ObjectDetector, process_frame, draw_bounding_boxes
from frame_saver import FrameSaver

# ═══════════════════════════════════════════════════════════════
# DEBUG LOGGING SYSTEM
# ═══════════════════════════════════════════════════════════════
DEBUG_ENABLED = True          # Master switch for console debug
DEBUG_LOG_TO_FILE = True      # Write CSV log for graph analysis
DEBUG_LOG_PATH = "debug_log.txt"
DEBUG_VERBOSE = True          # Extra detailed prints (1-line, PID, motor)

def debug_print(tag, msg):
    """Conditional debug print with tag"""
    if DEBUG_ENABLED:
        print(f"[{tag}] {msg}")

def debug_log_csv(error, pid_out, speed_l, speed_r, mode, num_lines, slope=None):
    """Append one row to CSV log file for later graphing"""
    if not DEBUG_LOG_TO_FILE:
        return
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            ts = time.time()
            slope_str = f"{slope:.3f}" if slope is not None else "None"
            f.write(f"{ts:.3f},{error:.4f},{pid_out:.2f},{speed_l:.1f},{speed_r:.1f},{mode},{num_lines},{slope_str}\n")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# YOLO DETECTION THREAD - Ayrı thread'te çalıştır
# ═══════════════════════════════════════════════════════════════
class YOLODetectionThread(QThread):
    """YOLO inference'ı ayrı thread'te çalıştır (UI'yi free tut)"""
    results_ready = Signal(object, object)  # frame, results
    
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.current_frame = None
        self.running = True
        self.mutex = QMutex()
        self.new_frame = False   # ✅ yeni frame flag
    
    def set_frame(self, frame):
        """Set current frame for processing"""
        self.mutex.lock()
        self.current_frame = frame.copy() if frame is not None else None
        self.new_frame = True     # ✅ sadece yeni frame
        self.mutex.unlock()
    
    def run(self):
        """Process frames continuously"""
        while self.running:
            self.mutex.lock()
            if not self.new_frame:
                self.mutex.unlock()
                time.sleep(0.002)
                continue
            
            frame = self.current_frame
            self.new_frame = False
            self.mutex.unlock()
            
            if frame is not None:
                try:
                    results = self.detector.detect(frame)
                    self.results_ready.emit(frame, results)
                except Exception as e:
                    print(f"[YOLO] Error: {e}")
    
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

        # Uygulama ikonunu ayarla
        icon_path = get_resource_path("icons/luxury-car.ico")
        app_icon = QIcon(icon_path)
        self.setWindowIcon(app_icon)

        loader = QUiLoader()
        ui_path = get_resource_path("modern_mainwindow.ui")
        ui_file = QFile(ui_path)
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
        
        # Debug: Widget'ların bulunup bulunmadığını kontrol et
        if self.quickWidgetSlider1 is None:
            print("[WARNING] quickWidgetSlider1 bulunamadı!")
        if self.quickWidgetJoystick is None:
            print("[WARNING] quickWidgetJoystick bulunamadı!")
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


       
        if self.quickWidgetSlider1:
            self.quickWidgetSlider1.setResizeMode(QQuickWidget.SizeRootObjectToView)
            self.quickWidgetSlider1.setClearColor(QColor("#19243d"))
            self.quickWidgetSlider1.setAttribute(Qt.WA_TranslucentBackground)
            self.quickWidgetSlider1.setStyleSheet("background: #19243d; border: none;")
            qml_path = get_resource_path("tools/ModernCircularSlider.qml")
            self.quickWidgetSlider1.setSource(QUrl.fromLocalFile(qml_path))
        

        #slider renk ayarları
        if self.quickWidgetSlider1:
            self.rootSlider1 = self.quickWidgetSlider1.rootObject()
            if self.rootSlider1:
                self.rootSlider1.valueChanged.connect(self.on_slider_changed)
            else:
                print("[WARNING] rootSlider1 (root object) bulunamadı!")

    
        self.setGeometry(self.ui.geometry())
        
        self.setWindowTitle("Otonom Car UI")

         #Yolo Model

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print ("[INFO] Using:", device)
      
        # Load model - birden çok yerde ara
        possible_paths = [
            get_resource_path("linen.pt"),
            get_resource_path("controllerspy/linen.pt"),
            get_resource_path("controllers/my_controller/linen.pt"),
        ]
        model_path = next((p for p in possible_paths if os.path.exists(p)), possible_paths[0])
        print(f"[INFO] Model path: {model_path} (exists: {os.path.exists(model_path)})")
        self.detector = ObjectDetector(model_path=model_path, device=device)
        self.device = device
        self.verbose = False  # Flag to control our own debug output

        # ✅ YOLO Detection Thread'i başlat
        self.yolo_thread = YOLODetectionThread(self.detector)
        self.yolo_thread.results_ready.connect(self.on_frame_processed)
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

         #timer update frame silindi
        # self.timer = QTimer()
       

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

        self.closeCam.clicked.connect(self.close)
        
        # Settings button -> frame capture
        if self.settingsButton:
            self.settingsButton.clicked.connect(self.capture_frame)
        
        # Autonomous mode flag
        self.autonomous_mode = False
        self.otonoumBtn.clicked.connect(self.toggle_autonomous_mode)
        
        # ═══════════════════════════════════════════════════════════════
        # ✅ FINAL LINE FOLLOWING + ARC PID PARAMETERS (YOLO11 Segmentation)
        # ═══════════════════════════════════════════════════════════════
        # ROBOT PARAMETRELERİ
        self.lane_width_cm = 27.0       # Gerçek şerit genişliği (cm)
        self.base_speed = 50            # Temel hız (0-100 arası, PWM'e dönüştürülür)
        self.min_pwm = 30               # Minimum PWM
        self.max_pwm = 100              # Maximum PWM
        
        # PID PARAMETRELERİ
        self.pid_kp = 0.07
        self.pid_kd = 0.015
        self.pid_ki = 0.0
        self.k_heading = 5.0            # Heading error ağırlığı
        
        # PID DEĞİŞKENLERİ
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_integral_limit = 30.0
        self.pid_last_time = time.time()
        
        # KALİBRASYON
        self.pixel_per_cm = None
        self.calibration_frames = []
        self.calibration_done = False
        
        # ROI - Alt %25
        self.roi_top_ratio = 0.75
        self.roi_bottom_ratio = 1.0
        
        # Çoklu çizgi / yol parametreleri
        self.estimated_half_road_width = None
        self.road_width_alpha = 0.1
        self.default_half_road_pct = 0.20
        self.slope_history = collections.deque(maxlen=5)
        self.last_is_left = None
        self.ideal_left_x = None
        self.ideal_right_x = None
        
        # Hız yumuşatma
        self.auto_base_speed = 45.0
        self.auto_min_speed = 15.0
        self.auto_max_speed = 60.0
        self.smoothed_speed = 0.0
        self.search_dir = "left"
        
        # Arama modu
        self.last_line_seen = time.time()
        self.no_line_timeout = 0.8
        self.search_turn_speed = 35
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
            
            self.socket_client.send_command("F")  # Forward
        elif self.wasd_pressed['S']:
            
            self.socket_client.send_command("B")  # Backward
        elif self.wasd_pressed['A']:
            
            self.socket_client.send_command("L")  # Left
        elif self.wasd_pressed['D']:
            
            self.socket_client.send_command("R")  # Right
        else:
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
        
        # If both are ready, close loading dialog
        if camera_ready and socket_ready:
            self.close_loading_dialog()
            return
        
        # If camera is not ready but socket is, show camera error
        if not camera_ready and socket_ready:
            if not hasattr(self, '_camera_error_shown'):
                self._camera_error_shown = True
                QMessageBox.critical(self, "Kamera Hatası", "Kamera başlatılamadı!")
            QTimer.singleShot(100, self.check_connections)
            return
        
        # If socket is not ready but camera is, show socket error
        if camera_ready and not socket_ready:
            if not hasattr(self, '_socket_error_shown'):
                self._socket_error_shown = True
                QMessageBox.critical(self, "Bağlantı Hatası", "Sunucuya bağlanılamadı!")
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
            self.camera_thread.frame_ready.connect(self.yolo_thread.set_frame)
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

        out = p + i + d
        
        # ✅ PID DEBUG
        if DEBUG_VERBOSE:
            debug_print("PID DEBUG", f"""
  error: {error:.3f}
  P: {p:.2f}  I: {i:.2f}  D: {d:.2f}
  OUT: {out:.2f}  dt: {dt:.4f}""")
        
        return out, p, i, d

    def pid_reset(self):
        """PID durumunu sıfırla"""
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = time.time()

    # ─── Çizgi Noktalarını Bul (polygon/contour/slope YOK) ─────
    def find_line_centers(self, masks, boxes, frame_shape):
        """
        Basit nokta tabanlı çizgi tespiti.
        Önce maskeleri dener (segmentation), olmazsa box merkezlerini kullanır.
        
        Return: [(cx, cy, mask_or_none), ...]  Sol → Sağ sıralı
                mask_or_none: mask binary (varsa) veya None (box fallback)
                Boş liste → hiçbir çizgi bulunamadı
        """
        h, w = frame_shape[:2]
        roi_top = int(h * self.roi_top_ratio)
        roi_bottom = int(h * self.roi_bottom_ratio)

        line_data = []

        # 1) Segmentation maskelerini dene
        if masks is not None and len(masks.data) > 0:
            for idx, mask_tensor in enumerate(masks.data):
                if boxes is not None and idx < len(boxes):
                    conf = boxes[idx].conf.item()
                    if conf < 0.2:
                        continue

                mask_np = mask_tensor.cpu().numpy()
                mask_resized = cv2.resize(mask_np, (w, h),
                                          interpolation=cv2.INTER_NEAREST)
                mask_binary = (mask_resized > 0.5).astype(np.uint8)

                if np.sum(mask_binary) < 50:
                    continue

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

                line_data.append((cx, cy, roi_mask))

        # 2) Fallback: segmentation yoksa box merkezini kullan
        elif boxes is not None and len(boxes) > 0:
            for idx, box in enumerate(boxes):
                conf = box.conf.item()
                if conf < 0.2:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx = (x1 + x2) // 2
                cy = min(y2 - 1, int(y1 + (y2 - y1) * 0.75))

                if cy < roi_top or cy > roi_bottom:
                    continue

                line_data.append((cx, cy, None))

        line_data.sort(key=lambda item: item[0])

        if DEBUG_VERBOSE and len(line_data) > 0:
            for i, item in enumerate(line_data):
                debug_print(f"LINE {i}", f"cx={item[0]}, cy={item[1]}")

        return line_data

    def compute_steering_error(self, line_centers, frame_shape):
        """
        Nokta tabanlı direksiyon hatası (polygon/slope YOK).
        
        2 çizgi: error = midpoint(sol, sağ) - frame_center
        1 çizgi: error = cx + yön_offset - frame_center
        0 çizgi: None (SEARCH)
        
        Return: (error_normalized, target_cx, mode_str) veya (None, None, mode_str)
        """
        h, w = frame_shape[:2]
        center_x = w // 2
        half_w = w / 2

        half_road = self.estimated_half_road_width
        if half_road is None:
            half_road = w * self.default_half_road_pct

        if len(line_centers) == 0:
            return None, None, "SEARCH"

        elif len(line_centers) >= 2:
            left_cx = line_centers[0][0]
            right_cx = line_centers[-1][0]

            gap = right_cx - left_cx
            if gap > 20:
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

        else:
            cx = line_centers[0][0]

            # Histerezis: son kararı koru, yoksa cx pozisyonuna bak
            if self.last_is_left is not None:
                is_left = self.last_is_left
            else:
                is_left = (cx < center_x)

            self.last_is_left = is_left
            avg_slope = None  # slope yok

            if is_left:
                target_cx = int(cx + half_road * 0.40)
                self.last_seen_line_side = "left"
                mode_str = "1-LINE-L"
            else:
                target_cx = int(cx - half_road * 0.40)
                self.last_seen_line_side = "right"
                mode_str = "1-LINE-R"

            error = (target_cx - center_x) / half_w
            return error, target_cx, mode_str

    def get_dual_row_centers(self, line_centers, frame_shape, num_rows=5):
        """
        Look-ahead: Varsa maskeleri yatay dilimlere böl → curvature tahmini.
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

        all_masks = [item[2] for item in line_centers if item[2] is not None]
        if not all_masks:
            return []

        row_height = roi_height // num_rows
        centers = []

        for i in range(num_rows):
            y_start = roi_top + i * row_height
            y_end = y_start + row_height

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
                slice_cxs.sort()
                target = (slice_cxs[0] + slice_cxs[-1]) // 2
            else:
                cx_single = slice_cxs[0]
                if cx_single < center_x:
                    target = int(cx_single + half_road)
                else:
                    target = int(cx_single - half_road)

            centers.append((target, cy))

        return centers

    def apply_deadzone(self, speed):
        """Motor hız filtresi — sadece gürültüyü sıfırla, dönüş farkını yeme"""
        if abs(speed) < 5:
            return 0  # Gürültü filtresi
        return speed  # Min_speed zorlaması kaldırıldı — dönüşte yavaş tekerlek serbest

    # ═══════════════════════════════════════════════════════════════
    # ✅ FINAL LINE FOLLOWING - YOLO11 Segmentation + ARC PID
    # ═══════════════════════════════════════════════════════════════
    def on_frame_processed(self, frame, results):
        """YOLO'dan işlenmiş frame geldi - Her zaman çizgi tespiti + görsel, otonomda PID"""
        try:
            self.current_frame = frame.copy()
            self.last_detection_results = results

            # FPS hesaplama
            fps = 0
            if hasattr(self, 'prev_time'):
                current_time = time.time()
                fps = 1 / (current_time - self.prev_time)
                self.prev_time = current_time
            else:
                self.prev_time = time.time()

            processed_frame = frame.copy()
            h, w = frame.shape[:2]

            # ── Her zaman: Çizgi tespiti ──
            if results is not None:
                masks = results.masks if hasattr(results, 'masks') and results.masks is not None else None
                boxes = results.boxes if hasattr(results, 'boxes') and results.boxes is not None else None
            else:
                masks = boxes = None

            line_centers = self.find_line_centers(masks, boxes, frame.shape) if results is not None else []
            error, target_cx, line_mode = self.compute_steering_error(line_centers, frame.shape) if results is not None else (None, None, "NO-LINE")
            num_lines = len(line_centers)
            best_conf = 0.0
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    conf = box.conf.item()
                    if conf > best_conf:
                        best_conf = conf

            # ── Her zaman: PID + Motor hızı (dry-run / real) ──
            if results is not None and error is not None and target_cx is not None:
                self.last_line_seen = time.time()

                curvature = 0.0
                if line_centers:
                    row_centers = self.get_dual_row_centers(line_centers, frame.shape, 5)
                    if len(row_centers) >= 3:
                        curvature = (row_centers[-1][0] - row_centers[0][0]) / w
                        error -= curvature * 0.80

                pid_out, p_val, i_val, d_val = self.pid_compute(error)
                pid_out = max(-100, min(100, pid_out))
                pid_out = float(np.tanh(pid_out / 40.0)) * 100.0

                turn_penalty = abs(pid_out / 100.0) * 25.0
                target_base_speed = max(self.auto_min_speed, self.auto_base_speed - turn_penalty)
                if target_base_speed > self.smoothed_speed:
                    self.smoothed_speed += 1.0
                    self.smoothed_speed = min(self.smoothed_speed, target_base_speed)
                else:
                    self.smoothed_speed = target_base_speed

                steering_strength = 30.0
                left_speed = self.smoothed_speed + (pid_out / 100.0) * steering_strength
                right_speed = self.smoothed_speed - (pid_out / 100.0) * steering_strength
                left_speed = max(-self.auto_max_speed, min(self.auto_max_speed, left_speed))
                right_speed = max(-self.auto_max_speed, min(self.auto_max_speed, right_speed))
                left_speed = self.apply_deadzone(left_speed)
                right_speed = self.apply_deadzone(right_speed)

                if error > 0.1:
                    self.search_dir = "right"
                elif error < -0.1:
                    self.search_dir = "left"

                now = time.time()
                cmd = f"DIFF,{-int(left_speed)},{-int(right_speed)}"
                if cmd != self.last_sent_cmd and (now - self.last_cmd_send_time) > self.cmd_send_interval:
                    self.last_sent_cmd = cmd
                    self.last_cmd_send_time = now
                    # SADECE otonom modda Raspberry'ye gönder
                    if self.autonomous_mode:
                        if self.socket_client and self.socket_client.connected:
                            self.socket_client.send_command(cmd)
                            if DEBUG_VERBOSE:
                                debug_print("MOTOR", f"L:{int(left_speed)} R:{int(right_speed)} | Mode:{line_mode} | Error:{error:.3f} | PID:{pid_out:.1f}")

                debug_log_csv(error, pid_out, left_speed, right_speed, line_mode, num_lines, None)

            else:
                # Çizgi yok → her zaman arama modu hesapla (gönderme aşağıda korumalı)
                left_speed, right_speed, pid_out = self._search_mode_impl()
                elapsed = time.time() - self.last_line_seen
                line_mode = f"SEARCH {elapsed:.0f}s"
                now = time.time()
                cmd = f"DIFF,{-int(left_speed)},{-int(right_speed)}"
                if cmd != self.last_sent_cmd and (now - self.last_cmd_send_time) > self.cmd_send_interval:
                    self.last_sent_cmd = cmd
                    self.last_cmd_send_time = now
                    if self.autonomous_mode:
                        if self.socket_client and self.socket_client.connected:
                            self.socket_client.send_command(cmd)

            # ── Her zaman: Debug çiz ──
            send_label = "AUTO SEND" if self.autonomous_mode else "SIMULATION"
            display_mode = f"{send_label} | {line_mode}"
            processed_frame = self._draw_debug_info(
                processed_frame, frame.shape, line_centers,
                error, target_cx, display_mode, num_lines,
                pid_out, left_speed, right_speed, best_conf, fps
            )

            # Frame göster
            self._display_frame(processed_frame, fps)

        except Exception as e:
            print(f"[ERROR] on_frame_processed: {e}")
            import traceback
            traceback.print_exc()

    def _search_mode_impl(self):
        """Arama modu - (left_speed, right_speed, pid_out) döndür (my_controller.py mantığı)"""
        elapsed = time.time() - self.last_line_seen

        if elapsed < self.no_line_timeout:
            base = self.auto_min_speed
            turn_power = self.search_turn_speed * 1.0
            if self.search_dir == "left":
                return base - turn_power, base + turn_power, 0
            else:
                return base + turn_power, base - turn_power, 0
        elif elapsed < self.no_line_timeout * 3:
            if self.search_dir == "left":
                return -self.search_turn_speed, self.search_turn_speed, 0
            else:
                return self.search_turn_speed, -self.search_turn_speed, 0
        else:
            self.pid_reset()
            self.smoothed_speed = self.auto_base_speed
            return 0, 0, 0

    def _draw_debug_info(self, frame, frame_shape, line_centers, error, target_cx, mode_str, num_lines, pid_out, left_speed, right_speed, best_conf, fps=0):
        """Görsel debug çizimleri (manual modda dahil her zaman çalışır)"""
        h, w = frame_shape[:2]
        center_x = w // 2

        roi_y = int(h * self.roi_top_ratio)
        cv2.line(frame, (0, roi_y), (w, roi_y), (255, 255, 0), 1)
        cv2.line(frame, (center_x, 0), (center_x, h), (255, 255, 255), 1)
        cv2.line(frame, (center_x, roi_y), (center_x, h), (0, 165, 255), 1)

        for idx, item in enumerate(line_centers):
            lcx, lcy = item[0], item[1]
            color = (0, 255, 255)
            label = ""
            if idx == 0 and num_lines >= 2:
                color = (255, 0, 0)
                label = "L"
            elif idx == num_lines - 1 and num_lines >= 2:
                color = (0, 255, 0)
                label = "R"
            cv2.circle(frame, (lcx, lcy), 6, color, -1)
            if label:
                cv2.putText(frame, label, (lcx - 5, lcy - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        if target_cx is not None:
            target_cy = line_centers[0][1] if line_centers else h // 2
            cv2.circle(frame, (target_cx, target_cy), 10, (0, 255, 255), 2)
            cv2.arrowedLine(frame, (center_x, target_cy), (target_cx, target_cy), (0, 0, 255), 2)

        mode_color = (0, 255, 0) if "AUTO" in mode_str else (0, 255, 255)
        cv2.putText(frame, mode_str, (w - 220, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, mode_color, 2)

        debug_texts = [
            f"MODE: {mode_str} | LINES: {num_lines}",
            f"ERROR: {error:+.3f}" if error is not None else "ERROR: N/A",
            f"PID: {pid_out:+.1f}",
            f"MOTOR L: {left_speed:+5.2f} | R: {right_speed:+5.2f}",
            f"FPS: {fps:.0f} | CONF: {best_conf:.2f}"
        ]

        for i, text in enumerate(debug_texts):
            cv2.putText(frame, text, (10, 30 + i * 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        return frame

    def _display_frame(self, processed_frame, fps):
        """Frame'i Qt label'a göster"""
        try:
            mode_text = "AUTO" if self.autonomous_mode else "MANUAL"
            gpu_memory_percent = f"{self.vram_usage_percent:.0f}%" if self.vram_usage_percent is not None else "--%"
            self.fpsLabel.setText(f"FPS: {fps:.0f} | Mode: {mode_text} | VRAM: {gpu_memory_percent}")

            h, w, ch = processed_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(processed_frame.data, w, h, bytes_per_line, QImage.Format_BGR888)

            self.CamLabel.setPixmap(QPixmap.fromImage(qt_image).scaled(
                self.CamLabel.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        except Exception as e:
            print(f"[ERROR] _display_frame: {e}")


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
            self.slope_history.clear()
            self.last_is_left = None
            self.ideal_left_x = None
            self.ideal_right_x = None
            self.smoothed_speed = self.auto_base_speed
            self.search_dir = "left"
            
            # ✅ Debug log header yazılsın (yeni oturum)
            if DEBUG_LOG_TO_FILE:
                with open(DEBUG_LOG_PATH, "a") as f:
                    f.write(f"# === NEW SESSION {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    f.write("# timestamp,error,pid_out,speed_l,speed_r,mode,num_lines,slope\n")
            
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
    # PyInstaller için multiprocessing desteği
    import multiprocessing
    multiprocessing.freeze_support()
    
    # Windows görev çubuğu için App ID ayarla
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OtonomCarUI.1.0")
    
    app = QApplication(sys.argv)
    app.setApplicationName("Otonom Car UI")
    icon_path = get_resource_path("icons/luxury-car.ico")
    app.setWindowIcon(QIcon(icon_path))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
