import cv2
import asyncio
import websockets
import json
import base64
import numpy as np
import torch
from PIL import Image
import io
import time
from ultralytics import YOLO

class WebCameraClient:
    def __init__(self, websocket_url="ws://localhost:8000/ws"):
        self.websocket_url = websocket_url
        self.websocket = None
        self.running = False
        
        # YOLO model
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print(f"[INFO] Using: {self.device}")
        self.detector = YOLO("best.pt")
        self.detector.to(self.device)
        
        # Camera
        self.cap = cv2.VideoCapture(0)
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0
        
    async def connect(self):
        """Connect to WebSocket server"""
        try:
            self.websocket = await websockets.connect(self.websocket_url)
            print("Connected to WebSocket server")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    async def send_frame(self):
        """Capture and send frame to server"""
        if not self.cap.isOpened():
            print("Camera not available")
            return
        
        ret, frame = self.cap.read()
        if not ret:
            return
        
        # Run YOLO detection
        results = self.detector(frame)
        
        # Draw detections
        annotated_frame = results[0].plot()
        
        # Calculate FPS
        self.fps_counter += 1
        elapsed_time = time.time() - self.fps_start_time
        if elapsed_time >= 1.0:
            self.current_fps = self.fps_counter / elapsed_time
            self.fps_counter = 0
            self.fps_start_time = time.time()
        
        # Count detections
        num_objects = len(results[0].boxes)
        
        # Convert frame to base64
        _, buffer = cv2.imencode('.jpg', annotated_frame)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # Send to server
        if self.websocket:
            try:
                await self.websocket.send(json.dumps({
                    'type': 'frame',
                    'frame': frame_base64,
                    'fps': round(self.current_fps, 1),
                    'device': self.device,
                    'objects': num_objects
                }))
            except Exception as e:
                print(f"Failed to send frame: {e}")
    
    async def handle_commands(self):
        """Handle incoming commands from server"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                print(f"Received command: {data}")
                
                # Here you would send commands to the car
                # For example, via socket_client.send_command(data['value'])
                
        except Exception as e:
            print(f"Error handling commands: {e}")
    
    async def run(self):
        """Main loop"""
        if not await self.connect():
            return
        
        self.running = True
        print("Camera client started")
        
        try:
            while self.running:
                # Send frame
                await self.send_frame()
                
                # Small delay to control frame rate
                await asyncio.sleep(0.03)  # ~30 FPS
                
        except KeyboardInterrupt:
            print("Stopping camera client...")
        finally:
            self.running = False
            if self.cap:
                self.cap.release()
            if self.websocket:
                await self.websocket.close()

if __name__ == "__main__":
    client = WebCameraClient()
    asyncio.run(client.run())
