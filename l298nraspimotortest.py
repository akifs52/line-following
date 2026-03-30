#!/usr/bin/env python3
"""
L298N Motor Driver Test for Raspberry Pi
Uses the same GPIO pins as raspiconfig.py
Tests 2 motors with L298N driver
"""

import RPi.GPIO as GPIO
import time
import sys

# =====================
# GPIO SETUP (Same as raspiconfig.py)
# =====================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin assignments from raspiconfig.py
PWMA = 12    # Motor A PWM (L298N ENA)
PWMB = 13    # Motor B PWM (L298N ENB)
AIN1 = 27    # Motor A Input 1 (L298N IN1)
AIN2 = 22    # Motor A Input 2 (L298N IN2)
BIN1 = 23    # Motor B Input 1 (L298N IN3)
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
# MOTOR FUNCTIONS
# =====================
def stop():
    """Stop all motors"""
    GPIO.output([AIN1, AIN2, BIN1, BIN2], GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    pwmB.ChangeDutyCycle(0)
    print("[MOTOR] STOP")

def forward(speed=50):
    """Move both motors forward"""
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.HIGH)
    GPIO.output(BIN2, GPIO.LOW)
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] FORWARD - Speed: {speed}%")

def backward(speed=50):
    """Move both motors backward"""
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.HIGH)
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] BACKWARD - Speed: {speed}%")

def left(speed=50):
    """Turn left (Motor A backward, Motor B forward)"""
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.HIGH)
    GPIO.output(BIN1, GPIO.HIGH)
    GPIO.output(BIN2, GPIO.LOW)
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] LEFT - Speed: {speed}%")

def right(speed=50):
    """Turn right (Motor A forward, Motor B backward)"""
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.HIGH)
    pwmA.ChangeDutyCycle(speed)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR] RIGHT - Speed: {speed}%")

def test_motor_a(speed=50):
    """Test Motor A only"""
    GPIO.output(BIN1, GPIO.LOW)
    GPIO.output(BIN2, GPIO.LOW)
    pwmB.ChangeDutyCycle(0)
    
    GPIO.output(AIN1, GPIO.HIGH)
    GPIO.output(AIN2, GPIO.LOW)
    pwmA.ChangeDutyCycle(speed)
    print(f"[MOTOR A] FORWARD - Speed: {speed}%")

def test_motor_b(speed=50):
    """Test Motor B only"""
    GPIO.output(AIN1, GPIO.LOW)
    GPIO.output(AIN2, GPIO.LOW)
    pwmA.ChangeDutyCycle(0)
    
    GPIO.output(BIN1, GPIO.HIGH)
    GPIO.output(BIN2, GPIO.LOW)
    pwmB.ChangeDutyCycle(speed)
    print(f"[MOTOR B] FORWARD - Speed: {speed}%")

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
    print("L298N MOTOR DRIVER TEST")
    print("="*60)
    print("\nGPIO Pin Configuration:")
    print(f"  PWMA (ENA)  -> GPIO{PWMA}")
    print(f"  PWMB (ENB)  -> GPIO{PWMB}")
    print(f"  AIN1 (IN1)  -> GPIO{AIN1}")
    print(f"  AIN2 (IN2)  -> GPIO{AIN2}")
    print(f"  BIN1 (IN3)  -> GPIO{BIN1}")
    print(f"  BIN2 (IN4)  -> GPIO{BIN2}")
    print(f"  STBY       -> GPIO{STBY}")
    print("\nL298N Connections:")
    print("  ENA -> GPIO12 (PWM Motor A)")
    print("  ENB -> GPIO13 (PWM Motor B)")
    print("  IN1 -> GPIO27 (Motor A Direction 1)")
    print("  IN2 -> GPIO22 (Motor A Direction 2)")
    print("  IN3 -> GPIO23 (Motor B Direction 1)")
    print("  IN4 -> GPIO24 (Motor B Direction 2)")
    print("  +12V -> Motor Power Supply")
    print("  GND  -> Ground (Raspberry Pi + Power Supply)")
    print("  OUT1/2 -> Motor A")
    print("  OUT3/4 -> Motor B")
    
    print("\n" + "="*60)
    print("TEST OPTIONS:")
    print("1. Individual Motor Test")
    print("2. Direction Test")
    print("3. Movement Sequence")
    print("4. Interactive Test")
    print("5. Run All Tests")
    print("0. Exit")
    
    try:
        while True:
            choice = input("\nSelect test (0-5): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                test_individual_motors()
            elif choice == '2':
                test_directions()
            elif choice == '3':
                test_sequence()
            elif choice == '4':
                interactive_test()
            elif choice == '5':
                test_individual_motors()
                test_directions()
                test_sequence()
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
