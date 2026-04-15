#!/usr/bin/env python3
"""
Raspberry Pi – Motor Kontrol Sunucusu (L298N)
===============================================
raspiconfig_l298n.py'nin geliştirilmiş versiyonu.

Raspberry Pi'de GÖRÜNTÜ İŞLEME YAPILMAZ.
Kamera görüntüsü ayrı TCP stream ile PC'ye gönderilir (libcamera/gstreamer).
Bu dosya sadece PC'den gelen motor komutlarını alır ve motorları sürer.

TCP Komutları:
  F / B / L / R / S       → İleri / Geri / Sol / Sağ / Dur
  CL / CR                 → Çapraz sol / sağ
  PWM<0-255>              → Hız ayarı (slider)
  DIFF,<sol>,<sag>        → Diferansiyel hız (PID otonom komutları)
                             sol/sağ = -100..+100 (neg = geri)

Kullanım:
  python3 autonomous_yolo_pid.py
"""

import RPi.GPIO as GPIO
import time
import socket
import threading
import signal
import sys

# =============================================
#  G P I O   P İ N L E R İ
# =============================================
PWMA = 12       # Motor A PWM (L298N ENA)
PWMB = 13       # Motor B PWM (L298N ENB)
AIN1 = 5        # Motor A Input 1 (L298N IN1)
AIN2 = 23       # Motor A Input 2 (L298N IN2)
BIN1 = 25       # Motor B Input 1 (L298N IN3)
BIN2 = 24       # Motor B Input 2 (L298N IN4)

# =============================================
#  M O T O R   A Y A R L A R I
# =============================================
INVERT_STEERING = False
INVERT_MOTOR_A = False
INVERT_MOTOR_B = False
MOTOR_A_SCALE = 1.0
MOTOR_B_SCALE = 1.0

# =============================================
#  T C P   A Y A R L A R I
# =============================================
HOST = "0.0.0.0"
PORT = 5005
TIMEOUT_SEC = 3.0       # İnaktiflik süresi → dur

# =============================================
#  G L O B A L   D U R U M
# =============================================
speed = 40               # Manuel hız (%)
last_cmd_time = time.time()
running = True

# =============================================
#  G P I O   K U R U L U M
# =============================================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup([PWMA, PWMB, AIN1, AIN2, BIN1, BIN2], GPIO.OUT)

pwm_freq = 1000
pwmA = GPIO.PWM(PWMA, pwm_freq)
pwmB = GPIO.PWM(PWMB, pwm_freq)
pwmA.start(0)
pwmB.start(0)


# =============================================
#  M O T O R   F O N K S İ Y O N L A R I
# =============================================
def _set_motor(in1, in2, forward):
    if forward:
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.HIGH)
    else:
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)


def _motor_a(forward):
    if INVERT_MOTOR_A:
        forward = not forward
    _set_motor(AIN1, AIN2, forward)


def _motor_b(forward):
    if INVERT_MOTOR_B:
        forward = not forward
    _set_motor(BIN1, BIN2, forward)


def stop():
    """Tüm motorları durdur"""
    GPIO.output([AIN1, AIN2, BIN1, BIN2], GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    pwmB.ChangeDutyCycle(0)
    print("[MOTOR] DUR")


def forward():
    _motor_a(True)
    _motor_b(True)
    apply_speed()
    print("[MOTOR] İLERİ")


def backward():
    _motor_a(False)
    _motor_b(False)
    apply_speed()
    print("[MOTOR] GERİ")


def left():
    _motor_a(True)
    _motor_b(False)
    apply_speed()
    print("[MOTOR] SOL")


def right():
    _motor_a(False)
    _motor_b(True)
    apply_speed()
    print("[MOTOR] SAĞ")


def cross_left():
    _motor_a(True)
    _motor_b(True)
    apply_speed()
    print("[MOTOR] ÇAPRAZ SOL")


def cross_right():
    _motor_a(False)
    _motor_b(False)
    apply_speed()
    print("[MOTOR] ÇAPRAZ SAĞ")


def apply_speed():
    """Manuel modda mevcut hızı uygula"""
    duty_a = max(0, min(100, speed * MOTOR_A_SCALE))
    duty_b = max(0, min(100, speed * MOTOR_B_SCALE))
    pwmA.ChangeDutyCycle(duty_a)
    pwmB.ChangeDutyCycle(duty_b)


def set_differential_speed(speed_left, speed_right):
    """
    PC'deki PID kontrolcüsünden gelen diferansiyel hız komutu.
    Her motor bağımsız hız + yön alır.
    speed_left, speed_right: -100 ... +100  (negatif = geri)
    """
    # Motor A (sol)
    if speed_left >= 0:
        _motor_a(True)
    else:
        _motor_a(False)

    # Motor B (sağ)
    if speed_right >= 0:
        _motor_b(True)
    else:
        _motor_b(False)

    duty_a = max(0, min(100, abs(speed_left) * MOTOR_A_SCALE))
    duty_b = max(0, min(100, abs(speed_right) * MOTOR_B_SCALE))

    if INVERT_STEERING:
        pwmA.ChangeDutyCycle(duty_b)
        pwmB.ChangeDutyCycle(duty_a)
    else:
        pwmA.ChangeDutyCycle(duty_a)
        pwmB.ChangeDutyCycle(duty_b)


# =============================================
#  K O M U T   İ Ş L E Y İ C İ
# =============================================
def handle_command(data):
    """TCP'den gelen komutları işle"""
    global speed, last_cmd_time
    last_cmd_time = time.time()

    # --- PWM Hız Ayarı ---
    if data.startswith("PWM"):
        try:
            pwm_value = int(data[3:])
            speed = max(0, min(100, int((pwm_value / 255) * 100)))
            apply_speed()
            print(f"[MOTOR] Hız: {speed}%  (PWM: {pwm_value})")
        except (ValueError, IndexError):
            print(f"[HATA] Geçersiz PWM: {data}")
        return

    # --- Diferansiyel Hız (PC'deki PID'den gelir) ---
    #     Format: DIFF,<sol_hız>,<sağ_hız>
    #     Örnek:  DIFF,45.2,30.8   veya   DIFF,-20,35
    if data.startswith("DIFF,"):
        try:
            parts = data.split(",")
            spd_left = float(parts[1])
            spd_right = float(parts[2])
            set_differential_speed(spd_left, spd_right)
        except (ValueError, IndexError):
            print(f"[HATA] Geçersiz DIFF komutu: {data}")
        return

    # --- Yön Komutları (Manuel mod) ---
    if data == "straight" or data == "F":
        forward()
    elif data == "backward" or data == "B":
        backward()
    elif data == "left" or data == "L":
        (right if INVERT_STEERING else left)()
    elif data == "right" or data == "R":
        (left if INVERT_STEERING else right)()
    elif data == "stop" or data == "S":
        stop()
    else:
        print(f"[UYARI] Bilinmeyen komut: {data}")


# =============================================
#  F A I L S A F E
# =============================================
def failsafe_loop():
    while running:
        if time.time() - last_cmd_time > TIMEOUT_SEC:
            stop()
        time.sleep(0.1)


# =============================================
#  T C P   S U N U C U
# =============================================
def tcp_server():
    global running

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(1)
    sock.settimeout(1.0)

    print(f"[TCP] Dinleniyor: {HOST}:{PORT}")

    while running:
        try:
            conn, addr = sock.accept()
            print(f"[TCP] Bağlandı: {addr}")
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            buffer = ""
            while running:
                try:
                    chunk = conn.recv(1024)
                except ConnectionResetError:
                    break
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    data = line.strip().replace("\x00", "")
                    if not data:
                        continue
                    handle_command(data)

        except Exception as e:
            print(f"[TCP] Bağlantı hatası: {e}")
        finally:
            try:
                conn.close()
            except:
                pass
            print("[TCP] İstemci ayrıldı, yeni bağlantı bekleniyor...")
            stop()

    sock.close()
    print("[TCP] Sunucu kapatıldı")


# =============================================
#  G İ R İ Ş   N O K T A S I
# =============================================
def shutdown(signum=None, frame=None):
    global running
    print("\n[ÇIKIŞ] Kapatılıyor...")
    running = False
    stop()
    pwmA.stop()
    pwmB.stop()
    GPIO.cleanup()
    print("[ÇIKIŞ] Temiz çıkış ✓")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)

    print("\n" + "=" * 55)
    print("  L298N MOTOR KONTROL SUNUCUSU")
    print("  (YOLO+PID PC tarafında çalışır)")
    print("=" * 55)
    print(f"  TCP          : {HOST}:{PORT}")
    print(f"  GPIO PWMA    : {PWMA}   PWMB : {PWMB}")
    print(f"  GPIO AIN1/2  : {AIN1}/{AIN2}  BIN1/2: {BIN1}/{BIN2}")
    print("=" * 55)
    print("  Komutlar:")
    print("    Manuel   → F  B  L  R  S  CL  CR")
    print("    Hız      → PWM<0-255>")
    print("    Otonom   → DIFF,<sol>,<sag>  (-100..+100)")
    print("=" * 55 + "\n")

    # Failsafe thread
    threading.Thread(target=failsafe_loop, daemon=True).start()

    # TCP sunucu (ana thread)
    try:
        tcp_server()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
