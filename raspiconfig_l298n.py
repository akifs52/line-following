#!/usr/bin/env python3
"""
Raspberry Pi Motor Control with L298N Driver
Uses same GPIO pins as raspiconfig.py
Compatible with L298N motor driver
"""

import RPi.GPIO as GPIO
import time
import socket
import threading

# =====================
# L298N MOTOR DRIVER TRUTH TABLE
# =====================
# L298N Motor Direction Control
# IN1  IN2  | Motor A Direction
# 0    1    | Forward
# 1    0    | Backward
# 0    0    | Brake
# 1    1    | Brake

# IN3  IN4  | Motor B Direction
# 0    1    | Forward
# 1    0    | Backward
# 0    0    | Brake
# 1    1    | Brake

# =====================
# GPIO SETUP (Same as raspiconfig.py)
# =====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin assignments from raspiconfig.py (updated BIN1 to GPIO25)
PWMA = 12    # Motor A PWM (L298N ENA)
PWMB = 13    # Motor B PWM (L298N ENB)
AIN1 = 27    # Motor A Input 1 (L298N IN1)
AIN2 = 22    # Motor A Input 2 (L298N IN2)
BIN1 = 25    # Motor B Input 1 (L298N IN3) - Updated to GPIO25
BIN2 = 24    # Motor B Input 2 (L298N IN4)
STBY = 6     # Standby (Not used with L298N, but kept for compatibility)

# Setup all pins
GPIO.setup([PWMA, PWMB, AIN1, AIN2, BIN1, BIN2, STBY], GPIO.OUT)

# PWM setup
pwm_freq = 1000  # 1kHz frequency
pwmA = GPIO.PWM(PWMA, pwm_freq)
pwmB = GPIO.PWM(PWMB, pwm_freq)

# Start PWM with 0% duty cycle
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
    """Stop all motors"""
    GPIO.output([AIN1, AIN2, BIN1, BIN2], GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    pwmB.ChangeDutyCycle(0)
    print("[MOTOR] STOP")

def forward():
    """Move both motors forward"""
    GPIO.output(AIN1, GPIO.LOW)   # Motor A: IN1=0, IN2=1 = Forward
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.LOW)   # Motor B: IN3=0, IN4=1 = Forward
    GPIO.output(BIN2, GPIO.HIGH)
    apply_speed()
    print("[MOTOR] FORWARD")

def backward():
    """Move both motors backward"""
    GPIO.output(AIN1, GPIO.HIGH)  # Motor A: IN1=1, IN2=0 = Backward
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.HIGH)  # Motor B: IN3=1, IN4=0 = Backward
    GPIO.output(BIN2, GPIO.LOW)
    apply_speed()
    print("[MOTOR] BACKWARD")

def left():
    """Turn left (Motor A backward, Motor B forward)"""
    GPIO.output(AIN1, GPIO.HIGH)  # Motor A: IN1=1, IN2=0 = Backward
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)   # Motor B: IN3=0, IN4=1 = Forward
    GPIO.output(BIN2, GPIO.HIGH)
    apply_speed()
    print("[MOTOR] LEFT")

def right():
    """Turn right (Motor A forward, Motor B backward)"""
    GPIO.output(AIN1, GPIO.LOW)   # Motor A: IN1=0, IN2=1 = Forward
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.HIGH)  # Motor B: IN3=1, IN4=0 = Backward
    GPIO.output(BIN2, GPIO.LOW)
    apply_speed()
    print("[MOTOR] RIGHT")

def cross_left():
    """Cross left (sharp left turn)"""
    GPIO.output(AIN1, GPIO.LOW)   # Motor A: IN1=0, IN2=1 = Forward
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.LOW)   # Motor B: IN3=0, IN4=1 = Forward
    GPIO.output(BIN2, GPIO.HIGH)
    apply_speed()
    print("[MOTOR] CROSS_LEFT")

def cross_right():
    """Cross right (sharp right turn)"""
    GPIO.output(AIN1, GPIO.HIGH)  # Motor A: IN1=1, IN2=0 = Backward
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.HIGH)  # Motor B: IN3=1, IN4=0 = Backward
    GPIO.output(BIN2, GPIO.LOW)
    apply_speed()
    print("[MOTOR] CROSS_RIGHT")

def apply_speed():
    """Apply current speed to motors"""
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)

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

    # DIRECTION (Single letter commands for compatibility)
    if data == "straight" or data == "F":
        forward()

    elif data == "backward" or data == "B":
        backward()

    elif data == "left" or data == "L":
        left()

    elif data == "right" or data == "R":
        right()

    elif data == "crossleft" or data == "CL":
        cross_left()

    elif data == "crossright" or data == "CR":
        cross_right()

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
# TCP SERVER (Same as raspiconfig.py)
# =====================
HOST = "0.0.0.0"
PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((HOST, PORT))
sock.listen(1)

print(f"[SERVER] Listening on {PORT}")
print("[L298N] Motor driver initialized")
print(f"[GPIO] PWMA={PWMA}, PWMB={PWMB}")
print(f"[GPIO] AIN1={AIN1}, AIN2={AIN2}")
print(f"[GPIO] BIN1={BIN1}, BIN2={BIN2}")
print(f"[GPIO] STBY={STBY}")

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
    print("[EXIT] L298N motor control stopped")
