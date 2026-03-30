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
AIN1 = 4
AIN2 = 5
BIN1 = 25
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
INVERT_STEERING = True  # Swap left/right to match your 2-motor wiring
INVERT_MOTOR_A = True   # If Motor A only spins in one direction, flip it
INVERT_MOTOR_B = False
MOTOR_A_SCALE = 1.0     # 0.0 - 1.2 (tweak to balance motors)
MOTOR_B_SCALE = 1.0

# =====================
# MOTOR FUNCTIONS
# =====================
def _set_motor(in1, in2, forward):
    if forward:
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)
    else:
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.HIGH)

def _motor_a(forward):
    if INVERT_MOTOR_A:
        forward = not forward
    _set_motor(AIN1, AIN2, forward)

def _motor_b(forward):
    if INVERT_MOTOR_B:
        forward = not forward
    _set_motor(BIN1, BIN2, forward)

def stop():
    GPIO.output([AIN1, AIN2, BIN1, BIN2], GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    pwmB.ChangeDutyCycle(0)
    GPIO.output(STBY, GPIO.LOW)  # Disable motor driver
    print("[MOTOR] STOP - STBY disabled")

def forward():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    _motor_a(True)
    _motor_b(True)

def backward():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    _motor_a(False)
    _motor_b(False)

def left():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    _motor_a(False)
    _motor_b(True)

def right():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    _motor_a(True)
    _motor_b(False)

def cross_left():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    _motor_a(False)
    _motor_b(True)

def cross_right():
    GPIO.output(STBY, GPIO.HIGH)  # Enable motor driver
    _motor_a(True)
    _motor_b(False)

def apply_speed():
    GPIO.output(STBY, GPIO.HIGH)  # Ensure motor driver is enabled
    duty_a = max(0, min(100, speed * MOTOR_A_SCALE))
    duty_b = max(0, min(100, speed * MOTOR_B_SCALE))
    pwmA.ChangeDutyCycle(duty_a)
    pwmB.ChangeDutyCycle(duty_b)

# =====================
# COMMAND HANDLER
# =====================
def handle_command(data):
    global speed, last_cmd_time
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
        return

    # DIRECTION
    if data == "straight" or data == "F":
        forward()
        apply_speed()

    elif data == "backward" or data == "B":
        backward()
        apply_speed()

    elif data == "left" or data == "L":
        (right() if INVERT_STEERING else left())
        apply_speed()

    elif data == "right" or data == "R":
        (left() if INVERT_STEERING else right())
        apply_speed()

    elif data == "crossleft" or data == "CL":
        (cross_right() if INVERT_STEERING else cross_left())
        apply_speed()

    elif data == "crossright" or data == "CR":
        (cross_left() if INVERT_STEERING else cross_right())
        apply_speed()

    elif data == "stop" or data == "S":
        stop()

    else:
        print(f"[WARNING] Unknown command: {data}")

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
    buffer = ""
    while True:
        chunk = conn.recv(1024)
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="ignore")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            data = line.strip().replace("\x00", "")
            if not data:
                continue
            handle_command(data)

except KeyboardInterrupt:
    print("\n[EXIT] Cleaning GPIO")

finally:
    stop()
    pwmA.stop()
    pwmB.stop()
    GPIO.cleanup()
    conn.close()
    sock.close()
