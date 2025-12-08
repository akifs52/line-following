from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                              QStatusBar, QLineEdit, QVBoxLayout, QWidget, 
                              QMessageBox, QDialog, QVBoxLayout, QHBoxLayout)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt, QUrl, QThread, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QColor, QMovie
from PySide6.QtQuickWidgets import QQuickWidget
import sys
import torch
import cv2
import time
import math
from ultralytics import YOLO
from CamDetection import CameraThread, ObjectDetector, process_frame
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
        self.detector = ObjectDetector(model_path="yolo11n.pt", device=device)
        self.device = device
        self.verbose = False  # Flag to control our own debug output

        self.statusbar.showMessage(device)

         #timer update frame
        self.timer = QTimer()
       

         #FPS için

        self.prev_time = time.time()
        self.fps_smooth = None

        self.tcpCamBtn.clicked.connect(self.start_camera)

        self.closeCam.clicked.connect(self.closeEvent)
        
        # Autonomous mode flag
        self.autonomous_mode = False
        self.otonoumBtn.clicked.connect(self.toggle_autonomous_mode)
    
    def show_loading_dialog(self, message):
        """Show a loading dialog with the given message"""
        self.loading_dialog = QDialog(self)
        self.loading_dialog.setWindowTitle("Yükleniyor...")
        self.loading_dialog.setModal(True)
        self.loading_dialog.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Add loading animation
        self.movie = QMovie("icons/loading.gif")
        self.movie.setScaledSize(QSize(50, 50))
        
        loading_label = QLabel()
        loading_label.setMovie(self.movie)
        loading_label.setAlignment(Qt.AlignCenter)
        self.movie.start()
        
        # Add message
        msg_label = QLabel(message)
        msg_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(loading_label)
        layout.addWidget(msg_label)
        
        self.loading_dialog.setLayout(layout)
        self.loading_dialog.show()
    
    def close_loading_dialog(self):
        """Close the loading dialog if it's open"""
        if hasattr(self, 'loading_dialog') and self.loading_dialog:
            self.movie.stop()
            self.loading_dialog.accept()
            self.loading_dialog = None
    
    def check_connections(self):
        """Check if both camera and socket connections are established"""
        camera_ready = hasattr(self, 'camera_thread') and self.camera_thread and self.camera_thread.isRunning()
        socket_ready = hasattr(self, 'socket_client') and self.socket_client and self.socket_client.connected
        
        if camera_ready and socket_ready:
            self.close_loading_dialog()
            self.timer.start(30)
        else:
            # Try again in 100ms if not both connections are ready
            QTimer.singleShot(100, self.check_connections)
    
    def start_camera(self):
        if not self.ipLineEdit.text():
            QMessageBox.warning(self, "Hata", "IP adresi boş olamaz!")
            return

        try:
            ip = self.ipLineEdit.text()
            camport = self.camPortLine.text()
            raspiport = int(self.raspiPortLine.text())
            fullipCam = f"http://{ip}:{camport}/video"
            
            # Show loading dialog
            self.show_loading_dialog("Kamera ve bağlantılar başlatılıyor...")
            
            print("[INFO] Starting Camera Thread...")
            
            # Start camera thread
            self.camera_thread = CameraThread(fullipCam)
            self.camera_ready = False
            self.camera_thread.start()
            
            # Start socket client
            if not hasattr(self, 'socket_client') or not self.socket_client:
                self.socket_client = SocketClient(ip, raspiport)
                self.socket_client.connect()
            
            # Start checking connections
            self.check_connections()
            
        except Exception as e:
            self.close_loading_dialog()
            QMessageBox.critical(self, "Hata", f"Başlatma hatası: {str(e)}")
    
    def check_connections(self):
        
        # Check camera status
        camera_ready = (hasattr(self, 'camera_thread') and 
                    self.camera_thread and 
                    self.camera_thread.isRunning())
        
        socket_ready = (hasattr(self, 'socket_client') and 
                    self.socket_client and 
                    self.socket_client.connected)
        
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
            fullipCam = f"http://{ip}:{camport}/video"
            
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
    
    def on_frame_received(self, frame):
        """Handle frame received from camera thread"""
        try:
            # Process frame with object detection
            processed_frame, fps, _, _, results = process_frame(
                frame, 
                self.detector,
                frame_counter=0,
                show_fps=True
            )

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

            # Handle detection results
            if results is not None and hasattr(results, 'boxes') and len(results.boxes) > 0:
                # Find the detection with highest confidence
                best_conf = 0
                best_label = None
                
                for box in results.boxes:
                    conf = box.conf.item()
                    if conf > best_conf:
                        best_conf = conf
                        best_label = self.detector.names.get(int(box.cls.item()), "unknown")

                # Process the best detection
                if best_label and best_label != self.last_label:
                    self.last_label = best_label
                    if self.autonomous_mode and hasattr(self, 'socket_client') and self.socket_client:
                        command = LABEL_TO_CMD.get(best_label, "S")  # Default to stop if label not in mapping
                        self.socket_client.send_command(command)
            else:
                # No detections - send stop if we were tracking a label
                if self.last_label != "stop":
                    self.last_label = "stop"
                    if self.autonomous_mode and hasattr(self, 'socket_client') and self.socket_client:
                        self.socket_client.send_command("S")

            # Update status bar with FPS
            if fps > 0:
                self.statusbar.showMessage(f"FPS: {fps:.1f} | Mode: {'AUTO' if self.autonomous_mode else 'MANUAL'}")
                
        except Exception as e:
            print(f"Error in on_frame_received: {str(e)}")
            # Optionally show error in status bar
            self.statusbar.showMessage(f"Error: {str(e)}")
    
    
    
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
                # Determine direction based on angle
                if -45 <= angle < 45:  # Right
                    self.socket_client.send_command(f"R")
                elif 45 <= angle < 135:  # Forward
                    self.socket_client.send_command(f"F")
                elif -135 <= angle < -45:  # Backward
                    self.socket_client.send_command(f"B")
                else:  # Left
                    self.socket_client.send_command(f"L")
    
    def on_joystick_released(self):
        """Handle joystick release - stop the vehicle"""
        if hasattr(self, 'socket_client') and self.socket_client:
            self.socket_client.send_command("S")
    
    def closeEvent(self, event):
        # Close camera thread if running
        self.close_camera()
        
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