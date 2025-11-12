import cv2
import time
import threading
from ultralytics import YOLO
import torch


class CameraThread(threading.Thread):
    def __init__(self, cam_index=0):
        super().__init__()
        self.cap = cv2.VideoCapture(cam_index)
        if not self.cap.isOpened():
            raise RuntimeError("Camera could not be opened.")
        self.frame = None
        self.running = True

    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
            else:
                break
        self.cap.release()

    def stop(self):
        self.running = False
        self.join()


def draw_boxes(frame, results, names):
    if not hasattr(results, "boxes") or len(results.boxes) == 0:
        return frame

    xyxy = results.boxes.xyxy.cpu().numpy()
    confs = results.boxes.conf.cpu().numpy()
    clss = results.boxes.cls.cpu().numpy()

    h, w = frame.shape[:2]
    for i in range(len(xyxy)):
        x1, y1, x2, y2 = map(int, xyxy[i])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        conf = float(confs[i])
        cls_idx = int(clss[i])
        cls_name = names[cls_idx] if 0 <= cls_idx < len(names) else str(cls_idx)
        label = f"{cls_name} {conf:.2f}"

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
        cv2.rectangle(frame, (x1, y1 - t_size[1] - 6),
                      (x1 + t_size[0] + 6, y1), (0, 255, 0), -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    return frame


def main():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Using device: {device}")

    model = YOLO("yolov8n.pt")  # Model otomatik indirir
    names = model.names if hasattr(model, "names") else []

    cam_thread = CameraThread("http://192.168.1.179:2002/video")
    cam_thread.start()
    print("[INFO] Camera thread started.")

    prev_time = time.time()
    fps_smooth = None

    try:
        while True:
            frame = cam_thread.frame
            if frame is None:
                continue

            # YOLO tahmini
            results = model(frame, device=device, imgsz=640, conf=0.3)[0]

            frame = draw_boxes(frame, results, names)

            # FPS hesapla
            now = time.time()
            fps = 1.0 / (now - prev_time) if now != prev_time else 0.0
            prev_time = now
            fps_smooth = fps if fps_smooth is None else (
                0.9 * fps_smooth + 0.1 * fps)

            cv2.putText(frame, f"FPS: {fps_smooth:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.imshow("YOLOv8 Threaded Camera", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cam_thread.stop()
        cv2.destroyAllWindows()
        print("[INFO] Camera stopped and windows closed.")


if __name__ == "__main__":
    main()
