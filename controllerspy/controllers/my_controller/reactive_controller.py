import cv2
import numpy as np
import time
import math
import torch
from ultralytics import YOLO

DEBUG_ENABLED = True
DEBUG_LOG_TO_FILE = True
DEBUG_LOG_PATH = "debug_reactive.txt"
DEBUG_VERBOSE = True

# ── Webots simülasyonu için ayarlanmış parametreler ──
KWALL_TARGET_CM = 13.5          # Hedef mesafe (sabit, degismez)
KDANGER_ZONE_CM = 5.0           # Tehlike bolgesi
KBASE_SPEED = 28.0              # Baz hiz (teker 12cm, 40*0.12=4.8m/s cok hizliydi)
KMIN_PWM = 8.0                  # Min motor
KMAX_PWM = 40.0                 # Max motor (teker 12cm, fazlasi havaya kaldirir)
KSTEER_GAIN = 0.055             # Kazanc: 0.025 ile virajlarda donemiyordu, 0.055 ile fark ~25+
KNO_LINE_TIMEOUT_MS = 800       # Cizgi kaybi timeout (C++ 500'dü, daha toleransli)
KSEARCH_TURN_SPEED = 25.0       # Arama donusu (C++ 35'ti, daha yumusak)
KDETECTION_SCORE_THRESHOLD = 0.30
KCAMERA_VIEW_WIDTH_CM = 28.0    # Webots kamerasi daha genis gorur (C++ 17'ydi)
KROI_TOP_RATIO = 0.30           # ROI biraz daha yukari cekildi
SMOOTH_ALPHA = 0.25             # Turn EMA filtrasyonu (kucuk = daha yumusak)


def debug_print(tag, msg):
    if DEBUG_ENABLED:
        print(f"[{tag}] {msg}")


class ReactiveController:
    """
    RaspiControlClient C++ kodunun Python Webots portu.
    Saf reaktif surus: PID yok, mesafe hatasi -> tanh -> motor.
    """

    def __init__(self, model_path="linen.pt", device=None):
        self.device = device if device else ("cuda:0" if torch.cuda.is_available() else "cpu")
        print(f"[Reactive] Baslatiliyor - Device: {self.device}")

        self.model = YOLO(model_path)

        # Otonom durum
        self.autonomous_mode = False
        self.autonomous_pending = False
        self.last_detection_ms = 0
        self.last_line_seen_ms = 0
        self.last_seen_side = None  # "left" | "right" | None

        # Kalibrasyon
        self.pixel_per_cm = 0.0
        self.frame_width = 0

        # Arama
        self.search_dir = "left"

        # Turn smoothing (EMA)
        self.smoothed_turn = 0.0

        # ----- PID state (tanimli ama kullanilmiyor, C++ ile uyum) -----
        self.pid_integral = 0.0
        self.pid_prev_error = 0.0
        self.pid_last_ms = 0

        # Gorsellestirme
        self.current_pid_error = 0.0
        self.current_pid_output = 0.0
        self.current_base_speed = KBASE_SPEED
        self.current_left_speed = 0.0
        self.current_right_speed = 0.0
        self.current_line_center_x = 0.5
        self.current_wall_distance = 0.0
        self.current_target_center = 0.5
        self.current_heading_error = 0.0
        self.current_total_error = 0.0
        self.current_turn_ratio = 0.0
        self.current_mode = "MANUAL"

        # Zamanlama
        self.command_timer = time.time()
        self.prev_time = time.time()
        self.current_fps = 0

    # ──────────────────────────────────────────────
    # Ana islem dongusu
    # ──────────────────────────────────────────────
    def process_frame(self, frame, draw_debug=True):
        now = time.time()
        self.current_fps = 1 / (now - self.prev_time) if self.prev_time else 0
        self.prev_time = now
        now_ms = int(now * 1000)

        results = self.model(frame, verbose=False)
        processed_frame = frame.copy() if draw_debug else None

        if not results:
            return self._build_result(0, 0, "NO-DETECTION", processed_frame)

        result = results[0]
        masks = result.masks if hasattr(result, 'masks') and result.masks is not None else None
        boxes = result.boxes if hasattr(result, 'boxes') and result.boxes is not None else None

        best_conf = 0.0
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                conf = box.conf.item()
                if conf > best_conf:
                    best_conf = conf

        # laneLeftX / laneRightX cikar (C++ detection modeli)
        lane_left_x, lane_right_x, left_detected, right_detected = self._extract_lane_metrics(
            masks, boxes, frame.shape
        )

        if not left_detected and not right_detected:
            return self._handle_search_mode(now_ms, frame, processed_frame, draw_debug)

        # Cizgi secimi (sol oncelikli)
        if left_detected:
            line_x = lane_left_x
            line_is_left = True
        else:
            line_x = lane_right_x
            line_is_left = False

        if line_x <= 0.02 or line_x >= 0.98:
            return self._handle_search_mode(now_ms, frame, processed_frame, draw_debug)

        self.last_line_seen_ms = now_ms
        self.last_seen_side = "left" if line_is_left else "right"

        # ----- Kalibrasyon (pixelPerCm) -----
        h, w = frame.shape[:2]
        self.frame_width = w
        if self.pixel_per_cm <= 1e-6:
            self.pixel_per_cm = w / KCAMERA_VIEW_WIDTH_CM
            debug_print("KALIB", f"pixel_per_cm={self.pixel_per_cm:.2f} (frame={w})")

        # ----- Mesafe hesaplama (cm) -----
        robot_center_px = 0.5 * w
        line_px = line_x * w
        if line_is_left:
            distance_cm = (robot_center_px - line_px) / self.pixel_per_cm
        else:
            distance_cm = (line_px - robot_center_px) / self.pixel_per_cm

        distance_cm = max(0.0, distance_cm)

        # ----- Hata hesaplama -----
        error_cm = KWALL_TARGET_CM - distance_cm
        # pozitif error = cizgiye cok yakin -> kac
        # negatif error = cizgiden cok uzak -> yaklas

        # Tehlike bolgesi boost
        steer_multiplier = 1.0
        if distance_cm < KDANGER_ZONE_CM:
            steer_multiplier = 1.0 + 2.0 * (1.0 - distance_cm / KDANGER_ZONE_CM)

        # Donus miktari (raw)
        turn_raw = KSTEER_GAIN * error_cm * steer_multiplier
        if not line_is_left:
            turn_raw = -turn_raw
        turn_raw = math.tanh(turn_raw)

        # EMA smoothing (salinim onleyici)
        self.smoothed_turn = SMOOTH_ALPHA * turn_raw + (1.0 - SMOOTH_ALPHA) * self.smoothed_turn
        turn = self.smoothed_turn

        # ----- Hiz hesabi -----
        base_speed = KBASE_SPEED
        if distance_cm < KDANGER_ZONE_CM:
            slow_factor = 0.75 + 0.25 * (distance_cm / KDANGER_ZONE_CM)
            base_speed *= slow_factor

        turn_mag = abs(turn)
        if turn_mag > 0.3:
            base_speed *= (1.0 + turn_mag * 0.15)
        if turn_mag < 0.15:
            base_speed *= 1.1

        # ----- Motor PWM -----
        left_pwm = base_speed * (1.0 + turn)
        right_pwm = base_speed * (1.0 - turn)

        left_pwm = max(KMIN_PWM, min(KMAX_PWM, left_pwm))
        right_pwm = max(KMIN_PWM, min(KMAX_PWM, right_pwm))

        # ----- Debug -----
        mode_str = "DANGER" if distance_cm < KDANGER_ZONE_CM else "TRACK"
        mode_label = f"{mode_str}-{'L' if line_is_left else 'R'}"
        debug_print("REACT",
            f"Dist={distance_cm:.1f}cm | Err={error_cm:.1f} | Turn={turn:.3f} | L={left_pwm:.1f} R={right_pwm:.1f}")

        # ----- Gorsellestirme state -----
        self.current_pid_error = error_cm
        self.current_pid_output = turn
        self.current_base_speed = base_speed
        self.current_left_speed = left_pwm
        self.current_right_speed = right_pwm
        self.current_line_center_x = line_x
        self.current_target_center = 0.5
        self.current_wall_distance = distance_cm
        self.current_heading_error = 0.0
        self.current_total_error = error_cm
        self.current_turn_ratio = turn
        self.current_mode = mode_label

        if draw_debug and processed_frame is not None:
            processed_frame = self._draw_debug(processed_frame, frame.shape,
                line_x, line_is_left, distance_cm, error_cm, turn,
                left_pwm, right_pwm, base_speed, mode_str, best_conf)

        return self._build_result(left_pwm, right_pwm, mode_label, processed_frame)

    # ──────────────────────────────────────────────
    # Yardimcilar
    # ──────────────────────────────────────────────
    def _extract_lane_metrics(self, masks, boxes, frame_shape):
        """C++ extractLaneCentersFromMask + laneLeftX/laneRightX mantigi"""
        h, w = frame_shape[:2]
        roi_top = int(h * KROI_TOP_RATIO)

        lane_left_x = -1.0
        lane_right_x = -1.0
        left_detected = False
        right_detected = False

        if masks is None or len(masks.data) == 0:
            return lane_left_x, lane_right_x, left_detected, right_detected

        for idx, mask_tensor in enumerate(masks.data):
            if boxes is not None and idx < len(boxes):
                conf = boxes[idx].conf.item()
                if conf < KDETECTION_SCORE_THRESHOLD:
                    continue

            mask_np = mask_tensor.cpu().numpy()
            mask_resized = cv2.resize(mask_np, (w, h), interpolation=cv2.INTER_NEAREST)
            mask_binary = (mask_resized > 0.5).astype(np.uint8)

            if np.sum(mask_binary) < 30:
                continue

            # ROI uygula
            roi_mask = mask_binary.copy()
            roi_mask[:roi_top, :] = 0
            if np.sum(roi_mask) < 20:
                continue

            M = cv2.moments(roi_mask, binaryImage=True)
            if M["m00"] == 0:
                continue

            cx = M["m10"] / M["m00"]
            cx_norm = cx / w

            if cx_norm < 0.5:
                if not left_detected or cx_norm < lane_left_x:
                    lane_left_x = cx_norm
                    left_detected = True
            else:
                if not right_detected or cx_norm > lane_right_x:
                    lane_right_x = cx_norm
                    right_detected = True

        return lane_left_x, lane_right_x, left_detected, right_detected

    def _handle_search_mode(self, now_ms, frame, processed_frame, draw_debug):
        """C++ handleSearchMode mantigi"""
        elapsed_ms = now_ms - self.last_line_seen_ms

        if elapsed_ms < KNO_LINE_TIMEOUT_MS:
            slow = KBASE_SPEED * 0.7
            left = right = max(KMIN_PWM, min(KMAX_PWM, slow))
            mode = "SEARCH-FWD"
        elif elapsed_ms < KNO_LINE_TIMEOUT_MS * 3:
            search_left = (self.last_seen_side == "left")
            if search_left:
                left = -KSEARCH_TURN_SPEED
                right = KSEARCH_TURN_SPEED
            else:
                left = KSEARCH_TURN_SPEED
                right = -KSEARCH_TURN_SPEED
            mode = "SEARCH-TURN"
        else:
            left = right = 0
            mode = "STOP"

        self.current_mode = mode
        self.current_left_speed = left
        self.current_right_speed = right
        self.current_pid_output = 0
        self.current_pid_error = 0
        self.current_turn_ratio = 0
        self.current_wall_distance = 0

        debug_print("SEARCH", f"{elapsed_ms}ms | Last: {self.last_seen_side} | L={left:.1f} R={right:.1f}")

        if draw_debug and processed_frame is not None:
            processed_frame = self._draw_debug(processed_frame, frame.shape,
                0.5, True, 0, 0, 0, left, right, 0, mode, 0)

        return self._build_result(left, right, mode, processed_frame)

    def _build_result(self, left, right, mode, frame):
        return {
            'left_speed': left,
            'right_speed': right,
            'mode': mode,
            'error': self.current_pid_error,
            'pid_output': self.current_pid_output,
            'fps': self.current_fps,
            'frame': frame
        }

    def set_autonomous(self, enabled):
        if not enabled:
            self.autonomous_mode = False
            self.autonomous_pending = False
            self.current_mode = "MANUAL"
            return
        self.autonomous_pending = True
        self.autonomous_mode = False
        self._reset_controller()

    def _reset_controller(self):
        now_ms = int(time.time() * 1000)
        self.last_line_seen_ms = now_ms
        self.last_detection_ms = 0
        self.last_seen_side = None
        self.search_dir = "left"
        self.pid_integral = 0.0
        self.pid_prev_error = 0.0
        self.pid_last_ms = now_ms
        self.pixel_per_cm = 0.0
        self.smoothed_turn = 0.0
        self.current_mode = "ARMED"

    # ──────────────────────────────────────────────
    # Debug gorsellestirme
    # ──────────────────────────────────────────────
    def _draw_debug(self, frame, frame_shape, line_x, line_is_left,
                    distance_cm, error_cm, turn, left_pwm, right_pwm,
                    base_speed, mode_str, best_conf):
        h, w = frame_shape[:2]
        center_x = w // 2
        roi_y = int(h * KROI_TOP_RATIO)

        # ROI cizgisi
        cv2.line(frame, (0, roi_y), (w, roi_y), (255, 255, 0), 1)

        # Merkez
        cv2.line(frame, (center_x, 0), (center_x, h), (255, 255, 255), 1)
        cv2.line(frame, (center_x, roi_y), (center_x, h), (0, 165, 255), 1)

        # Cizgi merkezi
        lx = int(line_x * w)
        ly = roi_y + (h - roi_y) // 2
        color = (255, 0, 0) if line_is_left else (0, 255, 0)
        cv2.circle(frame, (lx, ly), 8, color, -1)
        cv2.putText(frame, "L" if line_is_left else "R",
                    (lx - 5, ly - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Hedef pozisyon
        if line_is_left:
            target_px = int(center_x - KWALL_TARGET_CM * self.pixel_per_cm)
        else:
            target_px = int(center_x + KWALL_TARGET_CM * self.pixel_per_cm)
        target_px = max(0, min(w - 1, target_px))
        cv2.circle(frame, (target_px, ly), 12, (0, 255, 255), 3)
        cv2.drawMarker(frame, (target_px, ly), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
        cv2.arrowedLine(frame, (center_x, ly), (target_px, ly), (0, 0, 255), 2)

        # Mod rengi
        mode_colors = {
            "TRACK": (0, 255, 0), "DANGER": (0, 0, 255),
            "SEARCH-FWD": (255, 165, 0), "SEARCH-TURN": (0, 165, 255),
            "STOP": (0, 0, 0)
        }
        mc = mode_colors.get(mode_str, (200, 200, 200))
        cv2.putText(frame, f"{mode_str}-{'L' if line_is_left else 'R'}",
                    (w - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, mc, 2)

        texts = [
            f"DIST: {distance_cm:.1f}cm | TARGET: {KWALL_TARGET_CM}cm",
            f"ERROR: {error_cm:+.1f}cm",
            f"TURN: {turn:+.3f}",
            f"L: {left_pwm:+5.1f} | R: {right_pwm:+5.1f}",
            f"BASE: {base_speed:.1f} | FPS: {self.current_fps:.1f} | CONF: {best_conf:.2f}"
        ]
        for i, t in enumerate(texts):
            cv2.putText(frame, t, (10, 30 + i * 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        return frame


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        from controller import Robot

        robot = Robot()
        timestep = int(robot.getBasicTimeStep())

        print("[Webots] Reactive controller baslatiliyor...")

        camera = robot.getDevice('camera')
        camera.enable(timestep)
        width = camera.getWidth()
        height = camera.getHeight()
        print(f"[Webots] Kamera: {width}x{height}")

        left_motor = robot.getDevice('left_motor')
        right_motor = robot.getDevice('right_motor')
        left_motor.setPosition(float('inf'))
        right_motor.setPosition(float('inf'))
        left_motor.setVelocity(0.0)
        right_motor.setVelocity(0.0)
        print("[Webots] Motorlar kuruldu")

        ctrl = ReactiveController(model_path="linen.pt")
        ctrl.set_autonomous(True)

        print("[Webots] Reactive surus basliyor...")

        while robot.step(timestep) != -1:
            raw_image = camera.getImage()
            if raw_image:
                frame = np.frombuffer(raw_image, np.uint8).reshape((height, width, 4))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                result = ctrl.process_frame(frame, draw_debug=True)

                left_motor.setVelocity(result['left_speed'])
                right_motor.setVelocity(result['right_speed'])

                if result['frame'] is not None:
                    cv2.imshow("Reactive Controller", result['frame'])
                    cv2.waitKey(1)

                if DEBUG_VERBOSE:
                    print(f"[Webots] {result['mode']} | L:{result['left_speed']:.1f} R:{result['right_speed']:.1f} FPS:{result['fps']:.1f}")

        cv2.destroyAllWindows()

    except ImportError:
        print("[HATA] Webots kutuphanesi bulunamadi!")
    except Exception as e:
        print(f"[HATA] {str(e)}")
