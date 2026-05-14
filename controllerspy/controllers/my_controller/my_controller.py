"""
OTONOM NAVIGASYON MODULU - Webots Entegrasyonlu
Sadece cizgi takibi, PID kontrol ve Webots motor kontrolunu icerir.
"""

import cv2
import numpy as np
import time
import collections
import torch
from ultralytics import YOLO

DEBUG_ENABLED = True
DEBUG_LOG_TO_FILE = True
DEBUG_LOG_PATH = "debug_log.txt"
DEBUG_VERBOSE = True


def debug_print(tag, msg):
    if DEBUG_ENABLED:
        print(f"[{tag}] {msg}")


def debug_log_csv(error, pid_out, speed_l, speed_r, mode, num_lines, slope=None):
    if not DEBUG_LOG_TO_FILE:
        return
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            ts = time.time()
            slope_str = f"{slope:.3f}" if slope is not None else "None"
            f.write(f"{ts:.3f},{error:.4f},{pid_out:.2f},{speed_l:.1f},{speed_r:.1f},{mode},{num_lines},{slope_str}\n")
    except Exception:
        pass


class AutonomousNavigation:
    def __init__(self, model_path="best.pt", device=None):
        if device is None:
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        print(f"[INFO] Otonom navigasyon baslatiliyor - Device: {self.device}")

        self.model = YOLO(model_path)

        self.pid_kp = 15.0
        self.pid_ki = 0.02
        self.pid_kd = 6.0
        self.pid_integral_limit = 30.0
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = time.time()

        self.auto_base_speed = 45.0
        self.auto_min_speed = 15.0
        self.auto_max_speed = 60.0
        self.smoothed_speed = 0.0

        self.roi_top_ratio = 0.25
        self.roi_bottom_ratio = 1.0

        self.estimated_half_road_width = None
        self.road_width_alpha = 0.1
        self.default_half_road_pct = 0.20

        self.ideal_left_x = None
        self.ideal_right_x = None

        self.slope_history = collections.deque(maxlen=5)
        self.last_is_left = None

        self.last_line_seen = time.time()
        self.no_line_timeout = 0.8
        self.search_turn_speed = 35.0
        self.search_dir = "left"
        self.last_seen_line_side = None

        self.prev_time = time.time()
        self.current_fps = 0

    def process_frame(self, frame, draw_debug=True):
        current_time = time.time()
        self.current_fps = 1 / (current_time - self.prev_time) if self.prev_time else 0
        self.prev_time = current_time

        results = self.model(frame, verbose=False)

        processed_frame = frame.copy() if draw_debug else None

        if len(results) > 0:
            result = results[0]
            masks = result.masks if hasattr(result, 'masks') and result.masks is not None else None
            boxes = result.boxes if hasattr(result, 'boxes') and result.boxes is not None else None

            best_conf = 0.0
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    conf = box.conf.item()
                    if conf > best_conf:
                        best_conf = conf

            line_centers = self._find_line_centers(masks, boxes, frame.shape)

            error, target_cx, mode_str = self._compute_steering_error(line_centers, frame.shape)
            num_lines = len(line_centers)

            left_speed = 0
            right_speed = 0
            pid_out = 0

            if error is not None and target_cx is not None:
                self.last_line_seen = time.time()

                curvature = 0.0
                if line_centers:
                    row_centers = self._get_dual_row_centers(line_centers, frame.shape, 5)
                    if len(row_centers) >= 3:
                        h, w = frame.shape[:2]
                        curvature = (row_centers[-1][0] - row_centers[0][0]) / w
                        error -= curvature * 0.80

                pid_out, p_val, i_val, d_val = self._pid_compute(error)
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

                left_speed = self._apply_deadzone(left_speed)
                right_speed = self._apply_deadzone(right_speed)

                if error > 0.1:
                    self.search_dir = "right"
                elif error < -0.1:
                    self.search_dir = "left"

                first_slope = line_centers[0][3] if line_centers else None
                debug_log_csv(error, pid_out, left_speed, right_speed, mode_str, num_lines, first_slope)

                if DEBUG_VERBOSE:
                    debug_print("MOTOR", f"L:{left_speed:.2f} R:{right_speed:.2f} | PID:{pid_out:.1f}")

            else:
                mode_str = "SEARCH"
                left_speed, right_speed, pid_out = self._search_mode()

            if draw_debug and processed_frame is not None:
                processed_frame = self._draw_debug_info(
                    processed_frame, frame.shape, line_centers,
                    error, target_cx, mode_str, num_lines,
                    pid_out, left_speed, right_speed, best_conf
                )

            return {
                'left_speed': left_speed,
                'right_speed': right_speed,
                'mode': mode_str,
                'error': error if error is not None else 0,
                'pid_output': pid_out,
                'fps': self.current_fps,
                'frame': processed_frame
            }

        left_speed, right_speed, pid_out = self._search_mode()
        return {
            'left_speed': left_speed,
            'right_speed': right_speed,
            'mode': "SEARCH",
            'error': 0,
            'pid_output': pid_out,
            'fps': self.current_fps,
            'frame': processed_frame if draw_debug else None
        }

    def _find_line_centers(self, masks, boxes, frame_shape):
        if masks is None or len(masks.data) == 0:
            return []

        h, w = frame_shape[:2]
        roi_top = int(h * self.roi_top_ratio)
        roi_bottom = int(h * self.roi_bottom_ratio)

        line_data = []

        for idx, mask_tensor in enumerate(masks.data):
            if boxes is not None and idx < len(boxes):
                conf = boxes[idx].conf.item()
                if conf < 0.2:
                    continue

            mask_np = mask_tensor.cpu().numpy()
            mask_resized = cv2.resize(mask_np, (w, h), interpolation=cv2.INTER_NEAREST)
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

            slope = None
            try:
                contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    all_points = np.vstack(contours)
                    if len(all_points) >= 10:
                        [vx, vy, x0, y0] = cv2.fitLine(all_points, cv2.DIST_L2, 0, 0.01, 0.01)
                        if abs(vx[0]) > 0.01:
                            slope = float(vy[0] / vx[0])
            except Exception:
                slope = None

            line_data.append((cx, cy, mask_binary, slope))

        line_data.sort(key=lambda item: item[0])
        return line_data

    def _compute_steering_error(self, line_centers, frame_shape):
        h, w = frame_shape[:2]
        center_x = w // 2
        half_w = w / 2

        half_road = self.estimated_half_road_width
        if half_road is None:
            half_road = w * self.default_half_road_pct

        if len(line_centers) == 0:
            return None, None, "SEARCH"

        if len(line_centers) >= 2:
            sorted_lines = sorted(line_centers, key=lambda x: x[0])
            main_left = sorted_lines[0]
            main_right = sorted_lines[-1]

            gap = main_right[0] - main_left[0]
            if gap > w * 0.2:
                new_half = gap / 2.0
                if self.estimated_half_road_width is None:
                    self.estimated_half_road_width = new_half
                    self.estimated_half_road_width = (
                            (1 - self.road_width_alpha) * self.estimated_half_road_width +
                            self.road_width_alpha * new_half
                    )
                    self.estimated_half_road_width = max(w * 0.15, min(w * 0.45, self.estimated_half_road_width))

                target_cx = (main_left[0] + main_right[0]) // 2
                error = (target_cx - center_x) / half_w
                self.last_seen_line_side = "both"
                self.last_is_left = None

                alpha_ideal = 0.1
                if self.ideal_left_x is None:
                    self.ideal_left_x = main_left[0]
                    self.ideal_right_x = main_right[0]
                else:
                    if abs(error) < 0.15:
                        self.ideal_left_x = (1 - alpha_ideal) * self.ideal_left_x + alpha_ideal * main_left[0]
                        self.ideal_right_x = (1 - alpha_ideal) * self.ideal_right_x + alpha_ideal * main_right[0]

                return error, target_cx, "2-LINE"

        line = min(line_centers, key=lambda x: abs(x[0] - center_x))
        cx = line[0]
        slope = line[3]

        if slope is not None:
            self.slope_history.append(slope)
            if len(self.slope_history) > 5:
                self.slope_history.pop(0)

        if len(self.slope_history) > 0:
            avg_slope = sum(self.slope_history) / len(self.slope_history)
        else:
            avg_slope = slope

        if self.last_seen_line_side == "left":
            is_left = True
        elif self.last_seen_line_side == "right":
            is_left = False
        else:
            is_left = (cx < center_x)

        self.last_is_left = is_left

        if is_left:
            ideal = self.ideal_left_x if self.ideal_left_x is not None else w * 0.20
            error = (cx - ideal) / half_w
            target_cx = int(ideal)
            self.last_seen_line_side = "left"
            mode_str = "1-LINE-L"
        else:
            ideal = self.ideal_right_x if self.ideal_right_x is not None else w * 0.80
            error = (cx - ideal) / half_w
            target_cx = int(ideal)
            self.last_seen_line_side = "right"
            mode_str = "1-LINE-R"

        return error, target_cx, mode_str

    def _get_dual_row_centers(self, line_centers, frame_shape, num_rows=5):
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

    def _pid_compute(self, error):
        now = time.time()
        dt = now - self.pid_last_time
        if dt <= 0:
            dt = 0.01
        self.pid_last_time = now

        p = self.pid_kp * error
        self.pid_integral += error * dt
        self.pid_integral = max(-self.pid_integral_limit, min(self.pid_integral_limit, self.pid_integral))
        i = self.pid_ki * self.pid_integral
        derivative = (error - self.pid_prev_error) / dt
        d = self.pid_kd * derivative
        self.pid_prev_error = error
        out = p + i + d

        if DEBUG_VERBOSE:
            debug_print("PID", f"E:{error:.3f} P:{p:.2f} I:{i:.2f} D:{d:.2f} OUT:{out:.2f}")

        return out, p, i, d

    def _apply_deadzone(self, speed):
        if abs(speed) < 0.3:
            return 0
        return speed

    def _search_mode(self):
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
            self.reset()
            return 0, 0, 0

    def reset(self):
        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = time.time()
        self.last_line_seen = time.time()
        self.last_seen_line_side = None
        self.estimated_half_road_width = None
        self.slope_history.clear()
        self.last_is_left = None
        self.smoothed_speed = self.auto_base_speed
        debug_print("RESET", "Otonom navigasyon sifirlandi")

    def _draw_debug_info(self, frame, frame_shape, line_centers, error, target_cx, mode_str, num_lines, pid_out,
                         left_speed, right_speed, best_conf):
        h, w = frame_shape[:2]
        center_x = w // 2

        roi_y = int(h * self.roi_top_ratio)
        cv2.line(frame, (0, roi_y), (w, roi_y), (255, 255, 0), 1)

        cv2.line(frame, (center_x, 0), (center_x, h), (255, 255, 255), 1)
        cv2.line(frame, (center_x, roi_y), (center_x, h), (0, 165, 255), 1)

        for idx, item in enumerate(line_centers):
            lcx, lcy = item[0], item[1]
            if idx == 0 and num_lines >= 2:
                cv2.circle(frame, (lcx, lcy), 8, (255, 0, 0), -1)
                cv2.putText(frame, "L", (lcx - 5, lcy - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            elif idx == num_lines - 1 and num_lines >= 2:
                cv2.circle(frame, (lcx, lcy), 8, (0, 255, 0), -1)
                cv2.putText(frame, "R", (lcx - 5, lcy - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                cv2.circle(frame, (lcx, lcy), 8, (0, 255, 255), -1)

        if target_cx is not None:
            target_cy = line_centers[0][1] if line_centers else h // 2
            cv2.circle(frame, (target_cx, target_cy), 12, (0, 255, 255), 3)
            cv2.drawMarker(frame, (target_cx, target_cy), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
            cv2.arrowedLine(frame, (center_x, target_cy), (target_cx, target_cy), (0, 0, 255), 2)

        mode_colors = {"2-LINE": (0, 255, 0), "1-LINE-L": (255, 165, 0), "1-LINE-R": (0, 165, 255),
                       "SEARCH": (0, 0, 255)}
        mode_color = mode_colors.get(mode_str, (200, 200, 200))
        cv2.putText(frame, mode_str, (w - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, mode_color, 2)

        debug_texts = [
            f"MODE: {mode_str} | LINES: {num_lines}",
            f"ERROR: {error:+.3f}" if error is not None else "ERROR: N/A",
            f"PID: {pid_out:+.1f}",
            f"MOTOR L: {left_speed:+5.2f} | R: {right_speed:+5.2f}",
            f"FPS: {self.current_fps:.1f} | CONF: {best_conf:.2f}"
        ]

        for i, text in enumerate(debug_texts):
            cv2.putText(frame, text, (10, 30 + i * 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        return frame


if __name__ == "__main__":
    try:
        from controller import Robot

        robot = Robot()
        timestep = int(robot.getBasicTimeStep())

        print("[Webots] Robot baslatiliyor...")

        camera = robot.getDevice('camera')
        camera.enable(timestep)
        width = camera.getWidth()
        height = camera.getHeight()
        print(f"[Webots] Kamera kuruldu: {width}x{height}")

        left_motor = robot.getDevice('left_motor')
        right_motor = robot.getDevice('right_motor')
        left_motor.setPosition(float('inf'))
        right_motor.setPosition(float('inf'))
        left_motor.setVelocity(0.0)
        right_motor.setVelocity(0.0)
        print("[Webots] Motorlar kuruldu")

        nav = AutonomousNavigation(model_path="linen.pt")

        print("[Webots] Simulasyon basliyor...")

        while robot.step(timestep) != -1:
            raw_image = camera.getImage()
            if raw_image:
                frame = np.frombuffer(raw_image, np.uint8).reshape((height, width, 4))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                result = nav.process_frame(frame, draw_debug=True)

                left_motor.setVelocity(result['left_speed'])
                right_motor.setVelocity(result['right_speed'])

                if result['frame'] is not None:
                    cv2.imshow("Otonom Navigasyon", result['frame'])
                    cv2.waitKey(1)

                if DEBUG_VERBOSE:
                    print(
                        f"[Webots] {result['mode']} | L:{result['left_speed']:.2f} R:{result['right_speed']:.2f} | FPS:{result['fps']:.1f}")

        cv2.destroyAllWindows()

    except ImportError:
        print("[HATA] Webots kutuphanesi bulunamadi! Bu kodu Webots icinde calistirin.")
    except Exception as e:
        print(f"[HATA] {str(e)}")
