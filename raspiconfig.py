import socket
import time
import threading
import RPi.GPIO as GPIO

# =====================
# TB6612FNG MOTOR DRIVER TRUTH TABLE
# =====================
# TB6612FNG Motor Direction Control
# AIN1 AIN2 | Motor A Direction | STBY
# 0    0    | Brake             | HIGH
# 0    1    | Forward           | HIGH
# 1    0    | Backward          | HIGH
# 1    1    | Brake             | HIGH
# X    X    | Standby           | LOW

# BIN1 BIN2 | Motor B Direction | STBY
# 0    0    | Brake             | HIGH
# 0    1    | Forward           | HIGH
# 1    0    | Backward          | HIGH
# 1    1    | Brake             | HIGH
# X    X    | Standby           | LOW

# =====================
# GPIO SETUP
# =====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# TB6612FNG Motor Driver Pin Configuration
PWMA = 12    # Motor A PWM (TB6612FNG PWMA)
PWMB = 13    # Motor B PWM (TB6612FNG PWMB)
AIN1 = 4     # Motor A Input 1 (TB6612FNG AIN1)
AIN2 = 5     # Motor A Input 2 (TB6612FNG AIN2)
BIN1 = 25    # Motor B Input 1 (TB6612FNG BIN1)
BIN2 = 24    # Motor B Input 2 (TB6612FNG BIN2)
STBY = 6     # Standby (TB6612FNG STBY)

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
TIMEOUT_SEC = 10.0    # Increased timeout for joystick control (10 seconds)
INVERT_STEERING = False  # Swap left/right to match your 2-motor wiring
INVERT_MOTOR_A = False   # If Motor A only spins in one direction, flip it
INVERT_MOTOR_B = False
MOTOR_A_SCALE = 1.0     # 0.0 - 1.2 (tweak to balance motors)
MOTOR_B_SCALE = 1.0

# =====================
# MOTOR FUNCTIONS
# =====================
def _set_motor(in1, in2, forward):
    """Set motor direction using TB6612FNG logic"""
    if forward:
        GPIO.output(in1, GPIO.LOW)   # TB6612FNG: IN1=0, IN2=1 = Forward
        GPIO.output(in2, GPIO.HIGH)
    else:
        GPIO.output(in1, GPIO.HIGH)  # TB6612FNG: IN1=1, IN2=0 = Backward
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
    """Stop all motors - TB6612FNG brake mode"""
    GPIO.output(AIN1, GPIO.LOW)   # TB6612FNG: IN1=0, IN2=0 = Brake
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)   # TB6612FNG: IN1=0, IN2=0 = Brake
    GPIO.output(BIN2, GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    pwmB.ChangeDutyCycle(0)
    GPIO.output(STBY, GPIO.LOW)   # TB6612FNG: STBY=LOW = Standby
    print("[MOTOR] STOP - TB6612FNG standby")

def forward():
    """Move both motors forward"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(True)
    _motor_b(True)
    print("[MOTOR] FORWARD")

def backward():
    """Move both motors backward"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(False)
    _motor_b(False)
    print("[MOTOR] BACKWARD")

def left():
    """Turn left (Motor A backward, Motor B forward)"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(False)
    _motor_b(True)
    print("[MOTOR] LEFT")

def right():
    """Turn right (Motor A forward, Motor B backward)"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(True)
    _motor_b(False)
    print("[MOTOR] RIGHT")

def cross_left():
    """Cross left (sharp left turn)"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(False)
    _motor_b(True)
    print("[MOTOR] CROSS_LEFT")

def cross_right():
    """Cross right (sharp right turn)"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(True)
    _motor_b(False)
    print("[MOTOR] CROSS_RIGHT")

def apply_speed():
    """Apply current speed to motors - only when called"""
    GPIO.output(STBY, GPIO.HIGH)   # Ensure motor driver is enabled
    duty_a = max(0, min(100, speed * MOTOR_A_SCALE))
    duty_b = max(0, min(100, speed * MOTOR_B_SCALE))
    pwmA.ChangeDutyCycle(duty_a)
    pwmB.ChangeDutyCycle(duty_b)
    print(f"[MOTOR] Speed applied: A={duty_a:.1f}%, B={duty_b:.1f}%")

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
            apply_speed()  # Apply speed immediately when PWM command received
            print(f"[MOTOR] Speed set to {speed}% (PWM: {pwm_value})")
        except (ValueError, IndexError):
            print(f"[ERROR] Invalid PWM value: {data}")
        return

    # DIRECTION COMMANDS - only change direction, don't apply speed
    if data == "straight" or data == "F":
        forward()
        print("[MOTOR] Direction: FORWARD")

    elif data == "backward" or data == "B":
        backward()
        print("[MOTOR] Direction: BACKWARD")

    elif data == "left" or data == "L":
        (right() if INVERT_STEERING else left())
        print("[MOTOR] Direction: LEFT")

    elif data == "right" or data == "R":
        (left() if INVERT_STEERING else right())
        print("[MOTOR] Direction: RIGHT")

    elif data == "crossleft" or data == "CL":
        (cross_right() if INVERT_STEERING else cross_left())
        print("[MOTOR] Direction: CROSS_LEFT")

    elif data == "crossright" or data == "CR":
        (cross_left() if INVERT_STEERING else cross_right())
        print("[MOTOR] Direction: CROSS_RIGHT")

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
print("[TB6612FNG] Motor driver initialized")
print(f"[GPIO] PWMA={PWMA}, PWMB={PWMB}")
print(f"[GPIO] AIN1={AIN1}, AIN2={AIN2}")
print(f"[GPIO] BIN1={BIN1}, BIN2={BIN2}")
print(f"[GPIO] STBY={STBY}")
print(f"[CONFIG] Timeout: {TIMEOUT_SEC}s, Motor A scale: {MOTOR_A_SCALE}, Motor B scale: {MOTOR_B_SCALE}")

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
