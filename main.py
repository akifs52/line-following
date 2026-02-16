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
import subprocess
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
        self.joystick_root = None
        
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
        self.detector = ObjectDetector(model_path="best.pt", device=device)
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
            fullipCam = f"http://" + ip + f":" + camport + f"/video"
            
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
            
            # Save frame using frame_saver
            # self.frame_saver.try_save(frame)

            # Process frame with object detection
            processed_frame, fps, _, _, results = process_frame(
                frame, 
                self.detector,
                frame_counter=0,
                show_fps=True
            )

            # Update FPS display
            gpu_text = f"{self.gpu_util_percent:.0f}%" if self.gpu_util_percent is not None else "--%"
            gpu_memory_percent = f"{self.vram_usage_percent:.0f}%" if self.vram_usage_percent is not None else "--%"
            if fps > 0:
                self.fpsLabel.setText(f"FPS: {fps:.0f} | Mode: {'AUTO' if self.autonomous_mode else 'MANUAL'} | VRAM: {gpu_memory_percent}")
                self.fpsLabel.setStyleSheet("color: #10B981; border-radius: 4px;")
            else:
                self.fpsLabel.setText("FPS: -- | Mode: MANUAL | VRAM: --%")
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

            # No statusbar update needed - FPS label shows the same info
                
        except Exception as e:
            print(f"Error in on_frame_received: {str(e)}")
            # Optionally show error in status bar
            

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
           
        else:
            # Enable manual control
            if hasattr(self, 'quickWidgetJoystick'):
                self.quickWidgetJoystick.setEnabled(True)
            self.otonoumBtn.setStyleSheet("")
            
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

        if hasattr(self, 'gpu_timer') and self.gpu_timer.isActive():
            self.gpu_timer.stop()
        
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
