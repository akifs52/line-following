from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QStatusBar, QLineEdit
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
import sys
import torch
import cv2
import time
from ultralytics import YOLO
from CamDetection import CameraThread, draw_boxes


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
        self.ipCamLineEdit : QLineEdit = self.ui.findChild(QLineEdit , "ipCamLineEdit")
        
         # Kamera Thread
        self.camera_thread = None

        self.setGeometry(self.ui.geometry())
        
        self.setWindowTitle("Otonoum Car UI")

         #Yolo Model

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print ("[INFO] Using:", device)
        self.model = YOLO("yolov8n.pt")
        self.device = device
        self.names = self.model.names

        self.statusbar.showMessage(device)

         #timer update frame
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

         #FPS için

        self.prev_time = time.time()
        self.fps_smooth = None

        self.tcpCamBtn.clicked.connect(self.start_camera)
    
    def start_camera(self):

        if self.ipCamLineEdit.text() == "" :
            return
        else :
            ip = self.ipCamLineEdit.text()
            fullip = "http://" + ip + "/video"

        print("[INFO] Starting Camera Thread...")
        self.camera_thread = CameraThread(fullip)
        self.camera_thread.start()
        self.timer.start(30)

    def update_frame(self):

        if not self.camera_thread or self.camera_thread.frame is None:
            return
        
        self.frame = self.camera_thread.frame.copy()

        self.results = self.model(self.frame, device = self.device, imgsz = 640, conf = 0.75)[0]

        self.frame = draw_boxes(self.frame, self.results, self.names)

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
    
    def closeEvent(self, event):
        if self.camera_thread:
            self.camera_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())