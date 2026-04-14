from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                              QStatusBar, QLineEdit, QVBoxLayout, QWidget, 
                              QMessageBox, QDialog, QVBoxLayout, QHBoxLayout)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt, QUrl, QThread, Signal, QSize, QEvent
from PySide6.QtGui import QImage, QPixmap, QColor, QMovie, QKeySequence
from PySide6.QtQuickWidgets import QQuickWidget
import sys
import torch
import cv2
import numpy as np
import time
import subprocess
from ultralytics import YOLO
from CamDetection import CameraThread, ObjectDetector, process_frame
from frame_saver import FrameSaver
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
        self.detector = ObjectDetector(model_path="yolov8n.pt", device=device)
        self.device = device
        self.verbose = False  # Flag to control our own debug output

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
        
        # Autonomous mode flag
        self.autonomous_mode = False
        self.otonoumBtn.clicked.connect(self.toggle_autonomous_mode)
        
        # ── PID Otonom Sürüş Parametreleri (PC tarafında hesaplanır) ──
        self.pid_kp = 0.45
        self.pid_ki = 0.005
        self.pid_kd = 0.25
        self.pid_integral_limit = 100.0
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = time.time()
        
        # Motor hızları (otonom mod)
        self.auto_base_speed = 40
        self.auto_min_speed = 15
        self.auto_max_speed = 75
        
        # ROI – sadece alt kısma odaklan
        self.roi_top_ratio = 0.40
        self.roi_bottom_ratio = 1.0
        
        # Yol kaybolma
        self.last_line_seen = time.time()
        self.no_line_timeout = 1.0
        self.search_turn_speed = 30
        self.search_dir = "left"
        
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

    # ─── Segment Maskesinden Yol Merkezi ──────────────────────
    def find_line_center(self, masks, frame_shape):
        """
        YOLO segment maskesinden yolun ağırlık merkezini bul.
        Dönüş: (cx, cy, mask_binary)  veya  (None, None, None)
        """
        if masks is None or len(masks.data) == 0:
            return None, None, None

        h, w = frame_shape[:2]
        best_mask = None
        best_area = 0

        for mask_tensor in masks.data:
            mask_np = mask_tensor.cpu().numpy()
            mask_resized = cv2.resize(mask_np, (w, h),
                                      interpolation=cv2.INTER_NEAREST)
            mask_binary = (mask_resized > 0.5).astype(np.uint8)
            area = np.sum(mask_binary)
            if area > best_area:
                best_area = area
                best_mask = mask_binary

        if best_mask is None or best_area < 50:
            return None, None, None

        # ROI uygula
        roi_top = int(h * self.roi_top_ratio)
        roi_bottom = int(h * self.roi_bottom_ratio)
        roi_mask = best_mask.copy()
        roi_mask[:roi_top, :] = 0
        roi_mask[roi_bottom:, :] = 0

        if np.sum(roi_mask) < 30:
            return None, None, None

        M = cv2.moments(roi_mask, binaryImage=True)
        if M["m00"] == 0:
            return None, None, None

        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        return cx, cy, best_mask

    def get_multi_row_centers(self, mask, frame_shape, num_rows=5):
        """Maskeyi yatay dilimlere böl → eğim/curvature tahmini"""
        if mask is None:
            return []
        h, w = frame_shape[:2]
        roi_top = int(h * self.roi_top_ratio)
        roi_bottom = int(h * self.roi_bottom_ratio)
        roi_height = roi_bottom - roi_top
        if roi_height <= 0:
            return []
        row_height = roi_height // num_rows
        centers = []
        for i in range(num_rows):
            y_start = roi_top + i * row_height
            y_end = y_start + row_height
            row_slice = mask[y_start:y_end, :]
            if np.sum(row_slice) < 10:
                continue
            M = cv2.moments(row_slice, binaryImage=True)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = y_start + row_height // 2
            centers.append((cx, cy))
        return centers

    # ─── Görüntü İşleme + Otonom/Manuel ───────────────────────
    def on_frame_received(self, frame):
        """Handle frame received from camera thread"""
        try:
            # Save frame using frame_saver
            self.frame_saver.try_save(frame)

            # Process frame with object detection
            processed_frame, fps, _, _, results = process_frame(
                frame,
                self.detector,
                frame_counter=0,
                show_fps=True
            )

            h, w = frame.shape[:2]
            center_x = w // 2

            # ── Otonom Mod: YOLO + PID → DIFF komutu gönder ──
            if self.autonomous_mode and results is not None:
                masks = results.masks if hasattr(results, 'masks') and results.masks is not None else None
                boxes = results.boxes if hasattr(results, 'boxes') and results.boxes is not None else None

                cx, cy, mask_vis = self.find_line_center(masks, frame.shape)

                # Fallback: bbox'tan merkez
                if cx is None and boxes is not None and len(boxes) > 0:
                    best_conf = 0
                    best_box = None
                    for box in boxes:
                        conf = box.conf.item()
                        if conf > best_conf:
                            best_conf = conf
                            best_box = box
                    if best_box is not None:
                        if best_box.xywhn is not None and len(best_box.xywhn) > 0:
                            xn, yn, wn, hn = best_box.xywhn[0].cpu().numpy()
                            cx = int(xn * w)
                            cy = int(yn * h)
                        else:
                            x1, y1, x2, y2 = map(int, best_box.xyxy[0].cpu().numpy())
                            cx = (x1 + x2) // 2
                            cy = (y1 + y2) // 2
                        mask_vis = None

                if cx is not None:
                    # Yol bulundu
                    self.last_line_seen = time.time()
                    error = (cx - center_x) / (w / 2)

                    # Eğim analizi (anticipatory steering)
                    if mask_vis is not None:
                        row_centers = self.get_multi_row_centers(mask_vis, frame.shape, 5)
                        if len(row_centers) >= 3:
                            curvature = (row_centers[-1][0] - row_centers[0][0]) / w
                            error += curvature * 0.15

                    pid_out, p_val, i_val, d_val = self.pid_compute(error)
                    pid_out = max(-100, min(100, pid_out))

                    speed_l = self.auto_base_speed - pid_out
                    speed_r = self.auto_base_speed + pid_out
                    speed_l = max(-self.auto_max_speed, min(self.auto_max_speed, speed_l))
                    speed_r = max(-self.auto_max_speed, min(self.auto_max_speed, speed_r))

                    if 0 < abs(speed_l) < self.auto_min_speed:
                        speed_l = self.auto_min_speed if speed_l > 0 else -self.auto_min_speed
                    if 0 < abs(speed_r) < self.auto_min_speed:
                        speed_r = self.auto_min_speed if speed_r > 0 else -self.auto_min_speed

                    # Arama yönünü güncelle
                    if error > 0.1:
                        self.search_dir = "right"
                    elif error < -0.1:
                        self.search_dir = "left"

                    # Pi'ye DIFF komutu gönder
                    if self.socket_client and self.socket_client.connected:
                        self.socket_client.send_command(f"DIFF,{speed_l:.1f},{speed_r:.1f}")

                    # Debug overlay çiz
                    cv2.circle(processed_frame, (cx, cy), 10, (0, 0, 255), -1)
                    cv2.line(processed_frame, (center_x, cy), (cx, cy), (0, 0, 255), 2)
                    cv2.putText(processed_frame, f"PID:{pid_out:+.1f} L:{speed_l:.0f} R:{speed_r:.0f}",
                                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                else:
                    # Yol kayıp → arama modunda
                    elapsed = time.time() - self.last_line_seen
                    if self.socket_client and self.socket_client.connected:
                        if elapsed < self.no_line_timeout:
                            self.socket_client.send_command(f"DIFF,{self.auto_min_speed},{self.auto_min_speed}")
                        elif elapsed < self.no_line_timeout * 3:
                            if self.search_dir == "left":
                                self.socket_client.send_command(f"DIFF,{-self.search_turn_speed},{self.search_turn_speed}")
                            else:
                                self.socket_client.send_command(f"DIFF,{self.search_turn_speed},{-self.search_turn_speed}")
                        else:
                            self.socket_client.send_command("S")

                    cv2.putText(processed_frame, "ARAMA MODU",
                                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                # ROI çizgisi
                roi_y = int(h * self.roi_top_ratio)
                cv2.line(processed_frame, (0, roi_y), (w, roi_y), (255, 255, 0), 1)
                # Merkez çizgisi
                cv2.line(processed_frame, (center_x, roi_y), (center_x, h), (0, 165, 255), 1)

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
            # Otonom başlıyor → PID sıfırla
            self.pid_reset()
            self.last_line_seen = time.time()
            
            # Disable manual control when in autonomous mode
            if hasattr(self, 'quickWidgetJoystick'):
                self.quickWidgetJoystick.setEnabled(False)
            self.otonoumBtn.setStyleSheet("background-color: green; color: white;")
            # Clear WASD states when entering autonomous mode
            for key in self.wasd_pressed:
                self.wasd_pressed[key] = False
            print("[MOD] ═══ OTONOM BAŞLADI (PID on PC) ═══")
        else:
            # Manuel moda dön → dur
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
