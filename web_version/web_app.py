from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import cv2
import numpy as np
import torch
import asyncio
import json
import base64
from ultralytics import YOLO
import time
import io
from PIL import Image

app = FastAPI()

# YOLO modelini yükle
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Using: {device}")
detector = YOLO("best.pt")
detector.to(device)

# WebSocket bağlantıları
active_connections = []

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html class="dark" lang="en">
<head>
    <meta charset="utf-8"/>
    <meta content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" name="viewport"/>
    <title>Modern Autonomous Desktop V2 - Mobile</title>
    <script src="https://cdn.tailwindcss.com?plugins=forms,typography"></script>
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Round" rel="stylesheet"/>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
    <script>
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    colors: {
                        primary: "#3b82f6",
                        "background-light": "#f1f5f9",
                        "background-dark": "#0f172a",
                    },
                    fontFamily: {
                        display: ["Inter", "sans-serif"],
                    },
                    borderRadius: {
                        DEFAULT: "1.25rem",
                    },
                },
            },
        };
    </script>
    <style>
        body {
            font-family: 'Inter', sans-serif;
            -webkit-tap-highlight-color: transparent;
        }
        .glass {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .dark .glass {
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .joystick-outer {
            background: radial-gradient(circle, rgba(59, 130, 246, 0.1) 0%, transparent 70%);
        }
        .speed-gauge {
            background: conic-gradient(from 180deg at 50% 50%, #3b82f6 0deg, transparent 270deg);
            mask: radial-gradient(transparent 60%, black 61%);
            -webkit-mask: radial-gradient(transparent 60%, black 61%);
        }
        .center-dot-glow {
            transition: all 0.15s ease;
        }
        body {
            min-height: max(884px, 100dvh);
        }
    </style>
</head>
<body class="bg-background-light dark:bg-background-dark text-slate-900 dark:text-slate-100 min-h-screen transition-colors duration-300 overflow-hidden select-none">
    <!-- Status Bar -->
    <div class="px-6 pt-12 pb-2 flex justify-between items-center w-full">
        <div class="flex items-center space-x-2">
            <span class="text-sm font-semibold">9:41</span>
            <span class="material-icons-round text-xs">location_on</span>
        </div>
        <div class="flex items-center space-x-2">
            <span class="material-icons-round text-lg">signal_cellular_alt</span>
            <span class="material-icons-round text-lg">wifi</span>
            <span class="material-icons-round text-lg">battery_full</span>
        </div>
    </div>

    <!-- Main Content -->
    <main class="px-4 space-y-4 h-[calc(100vh-140px)] overflow-y-auto pb-32">
        <!-- Header -->
        <header class="flex justify-between items-center py-2 px-2">
            <div>
                <h1 class="text-2xl font-bold tracking-tight">Otonom V2</h1>
                <p class="text-xs text-slate-500 dark:text-slate-400 font-medium">System Ready: <span class="text-green-500">Online</span></p>
            </div>
            <button class="w-10 h-10 rounded-full glass flex items-center justify-center text-primary">
                <span class="material-icons-round">settings</span>
            </button>
        </header>

        <!-- Video Section -->
        <div class="relative aspect-video w-full rounded-3xl overflow-hidden bg-black shadow-2xl group border-2 border-white/10 dark:border-white/5">
            <img id="videoCanvas" alt="Live vehicle camera feed" class="w-full h-full object-cover opacity-60" src=""/>
            <div class="absolute inset-0 p-4 flex flex-col justify-between">
                <div class="flex justify-between items-start">
                    <div class="bg-black/50 backdrop-blur px-2 py-1 rounded-lg text-[10px] font-mono text-white/80 border border-white/20">
                        CAM_FRONT_01
                    </div>
                    <div class="flex space-x-2">
                        <div class="bg-red-500/80 px-2 py-1 rounded-lg text-[10px] font-bold text-white flex items-center animate-pulse">
                            <span class="w-1.5 h-1.5 bg-white rounded-full mr-1.5"></span> REC
                        </div>
                    </div>
                </div>
                <div class="flex justify-between items-end">
                    <div class="glass px-3 py-1.5 rounded-xl flex items-center space-x-3">
                        <div class="flex flex-col">
                            <span class="text-[8px] uppercase tracking-wider text-white/50">Lat</span>
                            <span class="text-[10px] font-mono text-white">41.0082° N</span>
                        </div>
                        <div class="flex flex-col">
                            <span class="text-[8px] uppercase tracking-wider text-white/50">Lon</span>
                            <span class="text-[10px] font-mono text-white">28.9784° E</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Connection Panel -->
        <div class="glass p-6 rounded-[2.5rem] flex flex-col space-y-4">
            <div class="flex justify-between items-start">
                <span class="text-[12px] uppercase font-bold text-slate-500">Connection</span>
                <span class="material-icons-round text-primary text-lg">lan</span>
            </div>
            <div class="grid grid-cols-2 gap-6">
                <div class="space-y-4">
                    <div class="space-y-3">
                        <div class="flex justify-between items-center">
                            <span class="text-xs opacity-70">IP</span>
                            <span id="ipDisplay" class="text-xs font-mono text-slate-300">192.168.1.100</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-xs opacity-70">Port</span>
                            <span id="portDisplay" class="text-xs font-mono text-slate-300">8001</span>
                        </div>
                    </div>
                    <button id="startBtn" class="w-full bg-green-500/20 text-green-500 border border-green-500/30 rounded-lg py-2 text-sm font-bold hover:bg-green-500/30 transition-colors flex items-center justify-center gap-2">
                        <span class="material-icons-round text-sm">play_arrow</span>
                        START
                    </button>
                </div>
                <div class="space-y-3">
                    <div class="flex flex-col gap-1">
                        <label class="text-[8px] font-bold uppercase tracking-wider text-slate-400">Raspberry Pi IP</label>
                        <div class="relative">
                            <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">router</span>
                            <input id="raspiIp" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-3 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="192.168.1.100" type="text"/>
                        </div>
                    </div>
                    <div class="flex flex-col gap-1">
                        <label class="text-[8px] font-bold uppercase tracking-wider text-slate-400">Ports</label>
                        <div class="flex gap-2">
                            <div class="relative flex-1">
                                <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">lan</span>
                                <input id="hostPort" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-2 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="Host:8000" type="text"/>
                            </div>
                            <div class="relative flex-1">
                                <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">settings_ethernet</span>
                                <input id="raspiPort" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-2 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="Raspi:8001" type="text"/>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Steering and Velocity Panels -->
        <div class="grid grid-cols-2 gap-4">
            <!-- Steering Control -->
            <div class="glass p-6 rounded-[2.5rem] flex flex-col items-center justify-center relative">
                <div class="absolute top-4 left-6">
                    <h3 class="text-[10px] font-bold uppercase tracking-widest text-slate-400">Steering Control</h3>
                </div>
                <div id="joystick" class="relative w-44 h-44 rounded-full border border-slate-700/50 flex items-center justify-center bg-slate-900/30">
                    <div class="absolute inset-0 border border-white/5 rounded-full scale-75"></div>
                    <div class="absolute w-[1px] h-full bg-white/5 left-1/2 -translate-x-1/2"></div>
                    <div class="absolute h-[1px] w-full bg-white/5 top-1/2 -translate-y-1/2"></div>
                    <div id="joystickHandle" class="w-20 h-20 rounded-full bg-primary shadow-[0_0_30px_rgba(59,130,246,0.5)] flex items-center justify-center text-white cursor-pointer hover:scale-105 transition-transform">
                        <span class="material-icons-round text-3xl">add</span>
                    </div>
                </div>
                <div class="mt-5 text-center space-y-1">
                    <div>
                        <p class="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Status</p>
                        <p id="steeringStatus" class="text-sm font-bold text-green-500">Active</p>
                    </div>
                    <div>
                        <p class="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Mode</p>
                        <p id="steeringMode" class="text-sm font-bold text-blue-500">Manual</p>
                    </div>
                </div>
            </div>

            <!-- Velocity Panel -->
            <div class="glass p-6 rounded-[2.5rem] flex flex-col items-center justify-center relative">
                <div class="absolute top-4 left-6">
                    <h3 class="text-[10px] font-bold uppercase tracking-widest text-slate-400">Velocity</h3>
                </div>
                <div class="relative w-44 h-44 rounded-full border border-slate-700/50 flex items-center justify-center bg-slate-900/30">
                    <div class="absolute inset-0 flex items-center justify-center">
                        <div class="w-32 h-32 rounded-full border-4 border-slate-200/20 dark:border-white/5 relative flex items-center justify-center">
                            <div class="absolute inset-0 speed-gauge opacity-40 rounded-full"></div>
                            <div class="text-center z-10">
                                <span id="speedValue" class="text-4xl font-black text-primary">48</span>
                                <p class="text-[10px] uppercase font-bold text-slate-500 tracking-widest">km/h</p>
                            </div>
                        </div>
                    </div>
                    <div class="absolute bottom-4 flex space-x-1">
                        <span class="w-1 h-1 rounded-full bg-primary"></span>
                        <span class="w-1 h-1 rounded-full bg-primary"></span>
                        <span class="w-1 h-1 rounded-full bg-primary/20"></span>
                        <span class="w-1 h-1 rounded-full bg-primary/20"></span>
                    </div>
                </div>
                <div class="mt-5 text-center space-y-1">
                    <div>
                        <p class="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Current</p>
                        <p class="text-sm font-bold text-primary">48 km/h</p>
                    </div>
                    <div>
                        <p class="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Max</p>
                        <p class="text-sm font-bold text-slate-400">100 km/h</p>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- Bottom Control Bar -->
    <div class="fixed bottom-0 inset-x-0 p-6 pt-2 pb-10 glass dark:bg-slate-900/80 border-t border-white/5">
        <button id="autonomousBtn" class="w-full bg-primary hover:bg-blue-600 text-white font-bold py-4 rounded-2xl shadow-[0_10px_30px_rgba(59,130,246,0.3)] active:scale-[0.98] transition-all flex items-center justify-center space-x-3">
            <span class="material-icons-round">smart_toy</span>
            <span>OTONOM SÜRÜŞÜ BAŞLAT</span>
        </button>
        <div class="mt-4 flex justify-between items-center text-[10px] font-mono text-slate-500 dark:text-slate-400 uppercase tracking-tighter">
            <div class="flex space-x-4">
                <span id="deviceInfo">CUDA:0 - 45°C</span>
                <span id="cpuInfo">CPU: 12%</span>
            </div>
            <div class="flex items-center">
                <span class="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5"></span>
                LATENCY: <span id="latencyInfo">12</span>ms
            </div>
        </div>
    </div>

    <!-- Bottom Indicator -->
    <div class="fixed bottom-1 inset-x-0 flex justify-center">
        <div class="w-32 h-1 bg-slate-400/30 dark:bg-slate-500/40 rounded-full"></div>
    </div>

    <script>
        // WebSocket connection
        const ws = new WebSocket('ws://localhost:8000/ws');
        
        // Control elements
        const joystick = document.getElementById('joystick');
        const joystickHandle = document.getElementById('joystickHandle');
        const autonomousBtn = document.getElementById('autonomousBtn');
        
        // Raspberry Pi controls
        const raspiIp = document.getElementById('raspiIp');
        const hostPort = document.getElementById('hostPort');
        const raspiPort = document.getElementById('raspiPort');
        
        // Status elements
        const speedValue = document.getElementById('speedValue');
        const steeringMode = document.getElementById('steeringMode');
        const ipDisplay = document.getElementById('ipDisplay');
        const portDisplay = document.getElementById('portDisplay');
        const startBtn = document.getElementById('startBtn');
        const deviceInfo = document.getElementById('deviceInfo');
        const cpuInfo = document.getElementById('cpuInfo');
        const latencyInfo = document.getElementById('latencyInfo');
        const videoCanvas = document.getElementById('videoCanvas');
        const steeringStatus = document.getElementById('steeringStatus');
        
        let autonomousMode = false;
        let currentSpeed = 0;
        let joystickActive = false;
        let centerX, centerY;
        
        // WebSocket events
        ws.onopen = function() {
            console.log('Connected to WebSocket server');
        };
        
        ws.onclose = function() {
            console.log('Disconnected from WebSocket server');
        };
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            if (data.type === 'frame') {
                // Display video frame
                videoCanvas.src = 'data:image/jpeg;base64,' + data.frame;
                
                // Update info
                latencyInfo.textContent = data.latency || '12';
                deviceInfo.textContent = `${data.device || 'CUDA:0'} - 45°C`;
                cpuInfo.textContent = `CPU: ${data.cpu || '12'}%`;
                
            } else if (data.type === 'speed') {
                currentSpeed = data.speed;
                speedValue.textContent = currentSpeed;
            }
        };
        
        // Traditional joystick controls
        function startJoystick(e) {
            if (autonomousMode) return;
            
            joystickActive = true;
            const rect = joystick.getBoundingClientRect();
            centerX = rect.left + rect.width / 2;
            centerY = rect.top + rect.height / 2;
            
            document.addEventListener('mousemove', moveJoystick);
            document.addEventListener('mouseup', endJoystick);
            document.addEventListener('touchmove', moveJoystick);
            document.addEventListener('touchend', endJoystick);
        }
        
        function moveJoystick(e) {
            if (!joystickActive || autonomousMode) return;
            
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const clientY = e.touches ? e.touches[0].clientY : e.clientY;
            
            const rect = joystick.getBoundingClientRect();
            const joystickCenterX = rect.left + rect.width / 2;
            const joystickCenterY = rect.top + rect.height / 2;
            
            let deltaX = clientX - joystickCenterX;
            let deltaY = clientY - joystickCenterY;
            
            const maxDistance = rect.width / 2 - joystickHandle.offsetWidth / 2;
            const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
            
            if (distance > maxDistance) {
                const angle = Math.atan2(deltaY, deltaX);
                deltaX = Math.cos(angle) * maxDistance;
                deltaY = Math.sin(angle) * maxDistance;
            }
            
            // Position handle
            joystickHandle.style.left = `${rect.width / 2 - joystickHandle.offsetWidth / 2 + deltaX}px`;
            joystickHandle.style.top = `${rect.height / 2 - joystickHandle.offsetHeight / 2 + deltaY}px`;
            
            // Update speed gauge based on joystick position
            const speed = Math.round(Math.sqrt(deltaX * deltaX + deltaY * deltaY) / maxDistance * 100);
            currentSpeed = speed;
            speedValue.textContent = currentSpeed;
            
            // Send joystick position
            const x = deltaX / maxDistance;
            const y = -deltaY / maxDist;
            
            ws.send(JSON.stringify({
                type: 'joystick',
                x: x,
                y: y,
                speed: currentSpeed
            }));
        }
        
        function endJoystick() {
            if (!joystickActive) return;
            
            joystickActive = false;
            
            // Reset handle to center
            const rect = joystick.getBoundingClientRect();
            joystickHandle.style.left = `${rect.width / 2 - joystickHandle.offsetWidth / 2}px`;
            joystickHandle.style.top = `${rect.height / 2 - joystickHandle.offsetHeight / 2}px`;
            
            // Reset speed gauge
            currentSpeed = 0;
            speedValue.textContent = '0';
            
            // Send stop command
            ws.send(JSON.stringify({
                type: 'joystick',
                x: 0,
                y: 0,
                speed: 0
            }));
            
            document.removeEventListener('mousemove', moveJoystick);
            document.removeEventListener('mouseup', endJoystick);
            document.removeEventListener('touchmove', moveJoystick);
            document.removeEventListener('touchend', endJoystick);
        }
        
        // Raspberry Pi connection
        function connectToRaspberryPi() {
            const ip = raspiIp.value || '192.168.1.100';
            const hPort = hostPort.value || '8000';
            const rPort = raspiPort.value || '8001';
            
            // Update connection displays
            ipDisplay.textContent = ip;
            portDisplay.textContent = rPort;
            
            // Send connection info
            ws.send(JSON.stringify({
                type: 'connect',
                raspi_ip: ip,
                host_port: hPort,
                raspi_port: rPort
            }));
        }
        
        // Start button functionality
        function startConnection() {
            const ip = raspiIp.value || '192.168.1.100';
            const port = raspiPort.value || '8001';
            
            // Update button state
            startBtn.innerHTML = '<span class="material-icons-round text-xs">refresh</span>CONNECTING...';
            startBtn.classList.add('bg-yellow-500/20', 'text-yellow-500', 'border-yellow-500/30');
            startBtn.classList.remove('bg-green-500/20', 'text-green-500', 'border-green-500/30');
            startBtn.disabled = true;
            
            // Send start command
            ws.send(JSON.stringify({
                type: 'start',
                raspi_ip: ip,
                raspi_port: port
            }));
            
            // Simulate connection success
            setTimeout(() => {
                startBtn.innerHTML = '<span class="material-icons-round text-xs">check_circle</span>CONNECTED';
                startBtn.classList.add('bg-green-500/20', 'text-green-500', 'border-green-500/30');
                startBtn.classList.remove('bg-yellow-500/20', 'text-yellow-500', 'border-yellow-500/30');
                startBtn.disabled = false;
            }, 2000);
        }
        
        // Event listeners
        joystick.addEventListener('mousedown', startJoystick);
        joystick.addEventListener('touchstart', startJoystick);
        
        // Raspberry Pi input listeners
        raspiIp.addEventListener('change', connectToRaspberryPi);
        hostPort.addEventListener('change', connectToRaspberryPi);
        raspiPort.addEventListener('change', connectToRaspberryPi);
        
        // Start button listener
        startBtn.addEventListener('click', startConnection);
        
        // Autonomous mode toggle
        autonomousBtn.addEventListener('click', function() {
            autonomousMode = !autonomousMode;
            
            if (autonomousMode) {
                this.innerHTML = '<span class="material-icons-round">smart_toy</span><span>OTONOM SÜRÜŞÜ DURDUR</span>';
                this.classList.add('bg-red-500');
                this.classList.remove('bg-primary');
                
                // Update steering status
                steeringStatus.textContent = 'Inactive';
                steeringStatus.style.color = '#64748B';
                steeringMode.textContent = 'Autonomous';
                steeringMode.style.color = '#ef4444';
                
                ws.send(JSON.stringify({
                    type: 'autonomous',
                    enabled: true
                }));
            } else {
                this.innerHTML = '<span class="material-icons-round">smart_toy</span><span>OTONOM SÜRÜŞÜ BAŞLAT</span>';
                this.classList.add('bg-primary');
                this.classList.remove('bg-red-500');
                
                // Update steering status
                steeringStatus.textContent = 'Active';
                steeringStatus.style.color = '#10B981';
                steeringMode.textContent = 'Manual';
                steeringMode.style.color = '#3b82f6';
                
                ws.send(JSON.stringify({
                    type: 'autonomous',
                    enabled: false
                }));
            }
        });
        
        // Keyboard controls (WASD for joystick)
        document.addEventListener('keydown', function(e) {
            if (autonomousMode) return;
            
            const key = e.key.toLowerCase();
            const rect = joystick.getBoundingClientRect();
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            const maxDistance = rect.width / 2 - joystickHandle.offsetWidth / 2;
            
            let x = 0, y = 0;
            
            if (key === 'w' || key === 'arrowup') y = -maxDistance;
            if (key === 's' || key === 'arrowdown') y = maxDistance;
            if (key === 'a' || key === 'arrowleft') x = -maxDistance;
            if (key === 'd' || key === 'arrowright') x = maxDistance;
            
            // Update handle position
            joystickHandle.style.left = `${centerX - joystickHandle.offsetWidth / 2 + x}px`;
            joystickHandle.style.top = `${centerY - joystickHandle.offsetHeight / 2 + y}px`;
            
            // Update speed
            const distance = Math.sqrt(x * x + y * y);
            currentSpeed = Math.round((distance / maxDistance) * 100);
            speedValue.textContent = currentSpeed;
            
            // Send position
            ws.send(JSON.stringify({
                type: 'joystick',
                x: x / maxDistance,
                y: -y / maxDistance,
                speed: currentSpeed
            }));
        });
        
        document.addEventListener('keyup', function(e) {
            const key = e.key.toLowerCase();
            if (['w', 's', 'a', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key)) {
                // Reset joystick
                const rect = joystick.getBoundingClientRect();
                joystickHandle.style.left = `${rect.width / 2 - joystickHandle.offsetWidth / 2}px`;
                joystickHandle.style.top = `${rect.height / 2 - joystickHandle.offsetHeight / 2}px`;
                
                currentSpeed = 0;
                speedValue.textContent = '0';
                
                ws.send(JSON.stringify({
                    type: 'joystick',
                    x: 0,
                    y: 0,
                    speed: 0
                }));
            }
        });
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTMLResponse(content=HTML_TEMPLATE)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get('type') == 'joystick':
                # Send joystick command to car
                x, y = message['x'], message['y']
                command = determine_direction(x, y)
                await manager.broadcast(json.dumps({'type': 'command', 'value': command}))
                
            elif message.get('type') == 'speed':
                # Send PWM speed command
                await manager.broadcast(json.dumps({'type': 'command', 'value': f"PWM{message['value']}"}))
                
            elif message.get('type') == 'autonomous':
                # Toggle autonomous mode
                await manager.broadcast(json.dumps({'type': 'command', 'value': "AUTO" if message['enabled'] else "MANUAL"}))
                
            elif message.get('type') == 'stop':
                # Send stop command
                await manager.broadcast(json.dumps({'type': 'command', 'value': "S"}))
                
            elif message.get('type') == 'key':
                # Handle WASD keys
                key = message['key']
                if message['pressed']:
                    if key == 'W':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "F"}))
                    elif key == 'S':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "B"}))
                    elif key == 'A':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "L"}))
                    elif key == 'D':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "R"}))
                else:
                    await manager.broadcast(json.dumps({'type': 'command', 'value': "S"}))
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def determine_direction(x, y):
    """Determine direction based on joystick position"""
    threshold = 0.1
    
    if abs(x) < threshold and abs(y) < threshold:
        return "S"  # Stop
    
    # Determine primary direction
    if abs(y) > abs(x):
        return "F" if y < 0 else "B"  # Forward or Backward
    else:
        return "L" if x < 0 else "R"  # Left or Right

@app.post("/upload_frame")
async def upload_frame(frame_data: dict):
    """Process uploaded frame and return detection results"""
    try:
        # Decode base64 image
        image_data = base64.b64decode(frame_data['frame'])
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to OpenCV format
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Run YOLO detection
        results = detector(frame)
        
        # Process results
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = box.conf[0].cpu().numpy()
                cls = int(box.cls[0].cpu().numpy())
                
                detections.append({
                    'class': cls,
                    'confidence': float(conf),
                    'bbox': [float(x1), float(y1), float(x2), float(y2)]
                })
        
        # Draw detections on frame
        annotated_frame = results[0].plot()
        
        # Convert back to base64
        _, buffer = cv2.imencode('.jpg', annotated_frame)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return {
            'frame': frame_base64,
            'detections': detections,
            'fps': frame_data.get('fps', 0),
            'device': device,
            'objects': len(detections)
        }
        
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
