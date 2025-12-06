from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                              QStatusBar, QLineEdit, QVBoxLayout, QWidget)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtQuickWidgets import QQuickWidget
import sys
from sympy import true
import torch
import cv2
import time
import math
from ultralytics import YOLO
from CamDetection import CameraThread, draw_bounding_boxes,strongest_label
from frame_saver import FrameSaver
from socket_client import SocketClient

LABEL_TO_CMD = {
            "left": "L",
            "right": "R",
            "straight": "F",
            "crossleft": "CL",
            "crossright": "CR",
        }

class MainWindow (QMainWindow):
    def __init__(self):
        super().__init__()

        loader = QUiLoader()
        ui_file = QFile("mainwindow.ui")
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()

        
        # UI'yi göstermek için
        self.setCentralWidget(self.ui)

        # Widget erişimi (objectName ile)
        self.tcpCamBtn: QPushButton = self.ui.findChild(QPushButton, "tcpCamBtn")
        self.otonoumBtn: QPushButton = self.ui.findChild(QPushButton, "otonoumBtn")
        self.CamLabel: QLabel = self.ui.findChild(QLabel, "CamLabel")
        self.statusbar: QStatusBar = self.ui.findChild(QStatusBar, "statusbar")
        self.ipLineEdit : QLineEdit = self.ui.findChild(QLineEdit , "ipLineEdit")
        self.closeCam : QPushButton = self.ui.findChild(QPushButton, "closeCam")
        self.camPortLine : QLineEdit = self.ui.findChild(QLineEdit, "camPortLine")
        self.raspiPortLine : QLineEdit = self.ui.findChild(QLineEdit , "raspiPortLine")
        self.quickWidgetSlider1 = self.ui.findChild(QQuickWidget, "quickWidgetSlider1")
        self.quickWidgetJoystick = self.ui.findChild(QQuickWidget, "quickWidgetJoystick")
        self.joystick_root = None
        
        if self.quickWidgetJoystick:
            try:
                self.quickWidgetJoystick.setResizeMode(QQuickWidget.SizeRootObjectToView)
                self.quickWidgetJoystick.setSource(QUrl.fromLocalFile("tools/AnalogJoystick.qml"))
                self.joystick_root = self.quickWidgetJoystick.rootObject()
                
                if self.joystick_root:
                    # Connect joystick signals
                    if hasattr(self.joystick_root, 'positionChanged'):
                        self.joystick_root.positionChanged.connect(self.on_joystick_moved)
                    if hasattr(self.joystick_root, 'released'):
                        self.joystick_root.released.connect(self.on_joystick_released)
                    
                    # Initially disable joystick until manual mode is activated
                    self.quickWidgetJoystick.setEnabled(true)
                else:
                    print("Warning: Failed to get joystick root object")
                    
            except Exception as e:
                print(f"Error initializing joystick: {e}")
        else:
            print("Warning: quickWidgetJoystick not found in UI")

        self.closeCam.hide()

        # Kamera Thread
        self.camera_thread = None
        self.frame_saver = FrameSaver(interval=0.75)
        self.socket_client = None
        self.last_label = None


       
        self.quickWidgetSlider1.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.quickWidgetSlider1.setSource(QUrl.fromLocalFile("tools/circularSlider.qml"))
        

         #slider renk ayarları

        self.rootSlider1 = self.quickWidgetSlider1.rootObject()
        
        self.rootSlider1.valueChanged.connect(self.on_slider_changed)

    

        self.setGeometry(self.ui.geometry())
        
        self.setWindowTitle("Otonoum Car UI")

         #Yolo Model

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print ("[INFO] Using:", device)
      
        # Load model with verbose=False to reduce output
        self.model = YOLO("yolov8n.pt")
        self.model.verbose = False  # Disable YOLO's built-in logging
        self.device = device
        self.names = self.model.names
        self.verbose = False  # Flag to control our own debug output

        self.statusbar.showMessage(device)

         #timer update frame
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

         #FPS için

        self.prev_time = time.time()
        self.fps_smooth = None

        self.tcpCamBtn.clicked.connect(self.start_camera)

        self.closeCam.clicked.connect(self.closeEvent)
        
        # Autonomous mode flag
        self.autonomous_mode = False
        self.otonoumBtn.clicked.connect(self.toggle_autonomous_mode)
    
    def start_camera(self):

        if not self.ipLineEdit.text():
            print("IP boş")
            return

        ip = self.ipLineEdit.text()
        camport = self.camPortLine.text()
        raspiport = int(self.raspiPortLine.text())

        fullipCam = f"http://{ip}:{camport}/video"

        print("[INFO] Starting Camera Thread...")

        # ---- Kamera thread zaten çalışıyorsa durdur ----
        
        self.camera_thread = CameraThread(fullipCam)
        self.camera_thread.start()
        self.timer.start(30)

        # ---- Socket ----
        if not self.socket_client:
            self.socket_client = SocketClient(ip, raspiport)
            self.socket_client.connect()


    def update_frame(self):

        if not self.camera_thread or self.camera_thread.frame is None:
            return
        
        self.frame = self.camera_thread.frame.copy()

        # Run YOLO detection with verbose=False to suppress output
        self.results = self.model(self.frame, device=self.device, imgsz=640, conf=0.75, verbose=False)[0]
        
        # Only show detection info when in verbose mode
        if self.verbose and len(self.results.boxes) > 0:
            print(f"Detected {len(self.results.boxes)} objects")

        #self.frame_saver.try_save(self.frame)

        self.frame = draw_bounding_boxes(self.frame, self.results, self.names)

        self.frame , best_label = strongest_label(self.frame,self.results, self.names)

                # ---- TESPİT VARSA ----
        if best_label:
            if best_label != self.last_label:
                self.last_label = best_label
                if self.autonomous_mode:  # Only send command if in autonomous mode
                    command = LABEL_TO_CMD[best_label]
                    self.socket_client.send_command(command)

        # ---- TESPİT YOKSA → STOP ----
        else:
            if self.last_label != "stop":
                self.last_label = "stop"
                if self.autonomous_mode:  # Only send stop command if in autonomous mode
                    self.socket_client.send_command("S")

         # ---- FPS ----
        now = time.time()
        fps = 1.0 / (now - self.prev_time)
        self.prev_time = now
        self.fps_smooth = fps if self.fps_smooth is None else (0.9 * self.fps_smooth + 0.1 * fps)
        
        self.statusbar.showMessage(f"FPS: {self.fps_smooth:.2f}")

         # ---- BGR → RGB ----
        
        rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        h,w,ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)

        #Image Size eşitlenir

        pix = QPixmap.fromImage(img)
        scaled_pix = pix.scaled(self.CamLabel.width(), 
                        self.CamLabel.height(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation)

        self.CamLabel.setPixmap(scaled_pix)

    def on_slider_changed(self):
        v = int(self.rootSlider1.property("value"))

        # Update slider color based on value
        if v < 85:
            self.rootSlider1.setProperty("progressColor", QColor("#ff5252"))
        elif v < 170:
            self.rootSlider1.setProperty("progressColor", QColor("#ffca28"))
        else:
            self.rootSlider1.setProperty("progressColor", QColor("#66bb6a"))
            
        # Send PWM value through socket if connected
        if hasattr(self, 'socket_client') and self.socket_client and self.socket_client.connected:
            # Send value in format "PWM{value}" where value is 0-255
            self.socket_client.send_command(f"PWM{v}")

    def toggle_autonomous_mode(self):
        """Toggle autonomous mode and update button text"""
        self.autonomous_mode = not self.autonomous_mode
        if self.autonomous_mode:
            # Disable manual control when in autonomous mode
            if hasattr(self, 'quickWidgetJoystick'):
                self.quickWidgetJoystick.setEnabled(False)
            self.otonoumBtn.setStyleSheet("background-color: green; color: white;")
            self.statusbar.showMessage("Otonom modu: AÇIK")
        else:
            # Enable manual control
            if hasattr(self, 'quickWidgetJoystick'):
                self.quickWidgetJoystick.setEnabled(True)
            self.otonoumBtn.setStyleSheet("")
            self.statusbar.showMessage("Manuel kontrol: AÇIK")
            # Send stop command when switching to manual mode
            if self.socket_client:
                self.socket_client.send_command("S")
        
    
    def on_joystick_moved(self, x, y):
        """Handle joystick movement in manual mode"""
        if not self.autonomous_mode and hasattr(self, 'socket_client') and self.socket_client:
            # Map joystick position to motor commands
            if abs(x) < 0.1 and abs(y) < 0.1:
                # Center position - stop
                self.socket_client.send_command("S")
            else:
                # Calculate angle and speed
                angle = math.atan2(y, x) * 180 / math.pi  # Convert to degrees
                speed = min(int(math.sqrt(x*x + y*y) * 100), 100)  # 0-100%
                
                # Determine direction based on angle
                if -45 <= angle < 45:  # Right
                    self.socket_client.send_command(f"R{speed}")
                elif 45 <= angle < 135:  # Forward
                    self.socket_client.send_command(f"F{speed}")
                elif -135 <= angle < -45:  # Backward
                    self.socket_client.send_command(f"B{speed}")
                else:  # Left
                    self.socket_client.send_command(f"L{speed}")
    
    def on_joystick_released(self):
        """Handle joystick release - stop the vehicle"""
        if hasattr(self, 'socket_client') and self.socket_client:
            self.socket_client.send_command("S")
    
    def closeEvent(self, event):
        if self.camera_thread:
            self.camera_thread.stop()
            self.frame_saver.last_save_time = 0
            if hasattr(self, 'socket_client') and self.socket_client:
                self.socket_client.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())