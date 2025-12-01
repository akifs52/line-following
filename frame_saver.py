import cv2
import time
import os
from datetime import datetime


class FrameSaver:
    def __init__(self, save_dir = "frames", interval = 0.75):
        self.save_dir  = save_dir
        self.interval = interval #saniye
        self.last_save_time = 0.0

        os.makedirs(self.save_dir, exist_ok= True)

    def try_save(self, frame):
        """Her çağrıda kontrol eder, süre dolduysa kaydeder"""

        now = time.time()

        if now -self.last_save_time >= self.interval:
            filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
            path = os.path.join(self.save_dir, filename)

            cv2.imwrite(path, frame)
            self.last_save_time = now
            return path # GUI logu için
        
        return None