from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QStatusBar, QLineEdit
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap, QColor
from PySide6.QtQuickWidgets import QQuickWidget
import sys
import torch
import cv2
import time
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
        self.quickWidgetSlider1 : QQuickWidget = self.ui.findChild(QQuickWidget, "quickWidgetSlider1")

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

        self.closeCam.clicked.connect(self.closeEvent)

        #self.otonoumBtn.clicked.connect()
    
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

        self.results = self.model(self.frame, device = self.device, imgsz = 640, conf = 0.75)[0]

        #self.frame_saver.try_save(self.frame)

        self.frame = draw_bounding_boxes(self.frame, self.results, self.names)

        self.frame , best_label = strongest_label(self.frame,self.results, self.names)

                # ---- TESPİT VARSA ----
        if best_label:
            if best_label != self.last_label:
                self.last_label = best_label
                command = LABEL_TO_CMD[best_label]
                self.socket_client.send_command(command)

        # ---- TESPİT YOKSA → STOP ----
        else:
            if self.last_label != "stop":
                self.last_label = "stop"
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
        v = self.rootSlider1.property("value")

        if v < 85:
            self.rootSlider1.setProperty("progressColor", QColor("#ff5252"))
        elif v < 170:
            self.rootSlider1.setProperty("progressColor", QColor("#ffca28"))
        else:
            self.rootSlider1.setProperty("progressColor", QColor("#66bb6a"))


        
    
    def closeEvent(self, event):
        if self.camera_thread:
            self.camera_thread.stop()
            self.frame_saver.last_save_time = 0
            self.socket_client.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())