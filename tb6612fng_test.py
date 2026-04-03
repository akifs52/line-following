#!/usr/bin/env python3
"""
TB6612FNG Motor Driver Test for Raspberry Pi
Uses the same GPIO pins as raspiconfig.py
Tests 2 motors with TB6612FNG driver
"""

import RPi.GPIO as GPIO
import time
import sys

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
# GPIO SETUP (Same as raspiconfig.py)
# =====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin assignments from raspiconfig.py
PWMA = 12    # Motor A PWM (TB6612FNG PWMA)
PWMB = 13    # Motor B PWM (TB6612FNG PWMB)
AIN1 = 4     # Motor A Input 1 (TB6612FNG AIN1)
AIN2 = 5     # Motor A Input 2 (TB6612FNG AIN2)
BIN1 = 25    # Motor B Input 1 (TB6612FNG BIN1)
BIN2 = 24    # Motor B Input 2 (TB6612FNG BIN2)
STBY = 6     # Standby (TB6612FNG STBY)

# Motor direction inversion (fix for Motor A going backward)
INVERT_MOTOR_A = False  # Motor A normal direction
INVERT_MOTOR_B = True   # Motor B inverted direction

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
    original_forward = forward
    if INVERT_MOTOR_A:
        forward = not forward
    print(f"[DEBUG] Motor A: requested={original_forward}, inverted={forward}, INVERT_MOTOR_A={INVERT_MOTOR_A}")
    _set_motor(AIN1, AIN2, forward)

def _motor_b(forward):
    original_forward = forward
    if INVERT_MOTOR_B:
        forward = not forward
    print(f"[DEBUG] Motor B: requested={original_forward}, inverted={forward}, INVERT_MOTOR_B={INVERT_MOTOR_B}")
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

def forward(speed=50):
    """Move both motors forward"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(True)
    _motor_b(True)
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] FORWARD - Speed: {speed}%")

def backward(speed=50):
    """Move both motors backward"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(False)
    _motor_b(False)
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] BACKWARD - Speed: {speed}%")

def left(speed=50):
    """Turn left (Motor A backward, Motor B forward)"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(False)   # Motor A backward
    _motor_b(True)    # Motor B forward
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] LEFT - Speed: {speed}%")

def right(speed=50):
    """Turn right (Motor A forward, Motor B backward)"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    _motor_a(True)    # Motor A forward
    _motor_b(False)   # Motor B backward
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] RIGHT - Speed: {speed}%")

def test_motor_a(speed=50):
    """Test Motor A only"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    GPIO.output(BIN1, GPIO.LOW)   # Motor B brake
    GPIO.output(BIN2, GPIO.LOW)
    pwmB.ChangeDutyCycle(0)
    
    GPIO.output(AIN1, GPIO.LOW)   # TB6612FNG: IN1=0, IN2=1 = Forward
    GPIO.output(AIN2, GPIO.HIGH)
    pwmA.ChangeDutyCycle(speed)
    print(f"[MOTOR A] FORWARD - Speed: {speed}%")

def test_motor_b(speed=50):
    """Test Motor B only"""
    GPIO.output(STBY, GPIO.HIGH)   # TB6612FNG: Enable motor driver
    GPIO.output(AIN1, GPIO.LOW)   # Motor A brake
    GPIO.output(AIN2, GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    
    GPIO.output(BIN1, GPIO.LOW)   # TB6612FNG: IN1=0, IN2=1 = Forward
    GPIO.output(BIN2, GPIO.HIGH)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR B] FORWARD - Speed: {speed}%")

def brake_test():
    """Test TB6612FNG brake mode"""
    print("\n--- Testing TB6612FNG Brake Mode ---")
    
    # Forward
    GPIO.output(STBY, GPIO.HIGH)
    _motor_a(True)
    _motor_b(True)
    pwmA.ChangeDutyCycle(50)
    pwmB.ChangeDutyCycle(50)
    print("Motors forward at 50% speed...")
    time.sleep(2)
    
    # Brake (IN1=0, IN2=0)
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.LOW)
    print("Motors BRAKE mode...")
    time.sleep(2)
    
    # Stop
    stop()

def standby_test():
    """Test TB6612FNG standby mode"""
    print("\n--- Testing TB6612FNG Standby Mode ---")
    
    # Forward
    GPIO.output(STBY, GPIO.HIGH)
    _motor_a(True)
    _motor_b(True)
    pwmA.ChangeDutyCycle(50)
    pwmB.ChangeDutyCycle(50)
    print("Motors forward at 50% speed...")
    time.sleep(2)
    
    # Standby (STBY=LOW)
    GPIO.output(STBY, GPIO.LOW)
    print("Motors STANDBY mode...")
    time.sleep(2)
    
    # Forward again
    GPIO.output(STBY, GPIO.HIGH)
    print("Motors forward again (STBY HIGH)...")
    time.sleep(2)
    
    # Stop
    stop()

def speed_test(motor_func, duration=3):
    """Test motor at different speeds"""
    speeds = [25, 50, 75, 100]
    
    for speed in speeds:
        print(f"\n--- Testing at {speed}% speed ---")
        motor_func(speed)
        time.sleep(duration)
        stop()
        time.sleep(1)

# =====================
# TEST FUNCTIONS
# =====================
def test_individual_motors():
    """Test each motor individually"""
    print("\n" + "="*50)
    print("TESTING INDIVIDUAL MOTORS")
    print("="*50)
    
    # Test Motor A
    print("\n--- Testing Motor A ---")
    speed_test(test_motor_a, 2)
    
    # Test Motor B
    print("\n--- Testing Motor B ---")
    speed_test(test_motor_b, 2)

def test_directions():
    """Test all directions"""
    print("\n" + "="*50)
    print("TESTING DIRECTIONS")
    print("="*50)
    
    directions = [
        ("FORWARD", forward),
        ("BACKWARD", backward),
        ("LEFT", left),
        ("RIGHT", right)
    ]
    
    for name, func in directions:
        print(f"\n--- Testing {name} ---")
        speed_test(func, 2)

def test_sequence():
    """Test movement sequence"""
    print("\n" + "="*50)
    print("TESTING MOVEMENT SEQUENCE")
    print("="*50)
    
    movements = [
        ("Forward", forward, 3),
        ("Stop", stop, 1),
        ("Backward", backward, 3),
        ("Stop", stop, 1),
        ("Left", left, 2),
        ("Stop", stop, 1),
        ("Right", right, 2),
        ("Stop", stop, 1)
    ]
    
    for name, func, duration in movements:
        print(f"\n--- {name} ({duration}s) ---")
        func(50)
        time.sleep(duration)

def test_tb6612fng_features():
    """Test TB6612FNG specific features"""
    print("\n" + "="*50)
    print("TESTING TB6612FNG FEATURES")
    print("="*50)
    
    brake_test()
    time.sleep(1)
    standby_test()

def interactive_test():
    """Interactive test mode"""
    print("\n" + "="*50)
    print("INTERACTIVE TEST MODE")
    print("="*50)
    print("Commands:")
    print("  f - Forward")
    print("  b - Backward")
    print("  l - Left")
    print("  r - Right")
    print("  s - Stop")
    print("  a - Test Motor A")
    print("  b - Test Motor B")
    print("  q - Quit")
    print("  1-9 - Speed (10-90%)")
    print("  0 - Speed 100%")
    
    current_speed = 50
    
    try:
        while True:
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == 'f':
                forward(current_speed)
            elif cmd == 'b':
                backward(current_speed)
            elif cmd == 'l':
                left(current_speed)
            elif cmd == 'r':
                right(current_speed)
            elif cmd == 's':
                stop()
            elif cmd == 'a':
                test_motor_a(current_speed)
            elif cmd == 'b':
                test_motor_b(current_speed)
            elif cmd.isdigit():
                speed = int(cmd) * 10 if int(cmd) > 0 else 100
                current_speed = min(100, speed)
                print(f"Speed set to {current_speed}%")
            else:
                print("Unknown command")
                
    except KeyboardInterrupt:
        pass

# =====================
# MAIN MENU
# =====================
def main():
    print("="*60)
    print("TB6612FNG MOTOR DRIVER TEST")
    print("="*60)
    print("\nGPIO Pin Configuration:")
    print(f"  PWMA (ENA)  -> GPIO{PWMA}")
    print(f"  PWMB (ENB)  -> GPIO{PWMB}")
    print(f"  AIN1 (IN1)  -> GPIO{AIN1}")
    print(f"  AIN2 (IN2)  -> GPIO{AIN2}")
    print(f"  BIN1 (IN3)  -> GPIO{BIN1}")
    print(f"  BIN2 (IN4)  -> GPIO{BIN2}")
    print(f"  STBY       -> GPIO{STBY}")
    print(f"\nMotor Direction Inversion:")
    print(f"  Motor A: {'INVERTED' if INVERT_MOTOR_A else 'NORMAL'}")
    print(f"  Motor B: {'INVERTED' if INVERT_MOTOR_B else 'NORMAL'}")
    print("\nTB6612FNG Connections:")
    print("  PWMA -> GPIO12 (Motor A PWM)")
    print("  PWMB -> GPIO13 (Motor B PWM)")
    print("  AIN1 -> GPIO4  (Motor A Direction 1)")
    print("  AIN2 -> GPIO5  (Motor A Direction 2)")
    print("  BIN1 -> GPIO25 (Motor B Direction 1)")
    print("  BIN2 -> GPIO24 (Motor B Direction 2)")
    print("  STBY -> GPIO6  (Standby)")
    print("  VCC  -> 3.3V (Logic power)")
    print("  VM   -> 12V (Motor power)")
    print("  GND  -> Ground")
    print("  A01/A02 -> Motor A")
    print("  B01/B02 -> Motor B")
    
    print("\n" + "="*60)
    print("TEST OPTIONS:")
    print("1. Individual Motor Test")
    print("2. Direction Test")
    print("3. Movement Sequence")
    print("4. TB6612FNG Features Test")
    print("5. Interactive Test")
    print("6. Run All Tests")
    print("0. Exit")
    
    try:
        while True:
            choice = input("\nSelect test (0-6): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                test_individual_motors()
            elif choice == '2':
                test_directions()
            elif choice == '3':
                test_sequence()
            elif choice == '4':
                test_tb6612fng_features()
            elif choice == '5':
                interactive_test()
            elif choice == '6':
                test_individual_motors()
                test_directions()
                test_sequence()
                test_tb6612fng_features()
            else:
                print("Invalid choice!")
                
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        print("\nCleaning up...")
        stop()
        pwmA.stop()
        pwmB.stop()
        GPIO.cleanup()
        print("Done!")

if __name__ == "__main__":
    main()
