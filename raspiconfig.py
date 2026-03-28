import socket
import time
import threading
import RPi.GPIO as GPIO

# =====================
# GPIO SETUP
# =====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# New pin assignments
PWMA = 12
PWMB = 13
AIN1 = 27
AIN2 = 22
BIN1 = 23
BIN2 = 24
STBY = 6

GPIO.setup([PWMA, PWMB, AIN1, AIN2, BIN1, BIN2, STBY], GPIO.OUT)

# Enable motor driver
GPIO.output(STBY, GPIO.HIGH)

pwmA = GPIO.PWM(PWMA, 1000)
pwmB = GPIO.PWM(PWMB, 1000)
pwmA.start(0)
pwmB.start(0)

# =====================
# GLOBAL STATE
# =====================
speed = 40           # default speed (%)
last_cmd_time = time.time()
TIMEOUT_SEC = 3.0

# =====================
# MOTOR FUNCTIONS
# =====================
def stop():
    GPIO.output([AIN1, AIN2, BIN1, BIN2], GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    pwmB.ChangeDutyCycle(0)
    GPIO.output(STBY, GPIO.LOW)  # Disable motor driver
    print("[MOTOR] STOP - STBY disabled")

def forward():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.HIGH)
    GPIO.output(BIN2, GPIO.LOW)

def left():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.HIGH)
    GPIO.output(BIN2, GPIO.LOW)

def right():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.HIGH)

def cross_left():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.HIGH)
    GPIO.output(BIN2, GPIO.LOW)

def cross_right():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.HIGH)

def apply_speed():
    GPIO.output(STBY, GPIO.HIGH)  # Ensure motor driver is enabled
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)

# =====================
# FAILSAFE THREAD
# =====================
def failsafe_loop():
    global last_cmd_time
    while True:
        if time.time() - last_cmd_time > TIMEOUT_SEC:
            stop()
        time.sleep(0.1)

# =====================
# TCP SERVER
# =====================
HOST = "0.0.0.0"
PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((HOST, PORT))
sock.listen(1)

print(f"[SERVER] Listening on {PORT}")

threading.Thread(target=failsafe_loop, daemon=True).start()

conn, addr = sock.accept()
print("[CLIENT] Connected:", addr)

try:
    while True:
        data = conn.recv(1024).decode().strip()
        if not data:
            continue

        last_cmd_time = time.time()
        print("[CMD]", data)

        # SPEED (PWM format: PWM<value> where value is 0-255)
        if data.startswith("PWM"):
            try:
                pwm_value = int(data[3:])  # Extract number after 'PWM'
                speed = max(0, min(100, int((pwm_value / 255) * 100)))  # Convert 0-255 to 0-100%
                apply_speed()
                print(f"[MOTOR] Speed set to {speed}% (PWM: {pwm_value})")
            except (ValueError, IndexError):
                print(f"[ERROR] Invalid PWM value: {data}")

        # DIRECTION
        elif data == "straight":
            forward()
            apply_speed()

        elif data == "left":
            left()
            apply_speed()

        elif data == "right":
            right()
            apply_speed()

        elif data == "crossleft":
            cross_left()
            apply_speed()

        elif data == "crossright":
            cross_right()
            apply_speed()

        elif data == "stop":
            stop()

except KeyboardInterrupt:
    print("\n[EXIT] Cleaning GPIO")

finally:
    stop()
    pwmA.stop()
    pwmB.stop()
    GPIO.cleanup()
    conn.close()
    sock.close()
