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
        .velocity-dial {
            touch-action: none;
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

        <!-- Steering and Velocity Panels -->
        <div class="grid grid-cols-2 gap-4">
            <!-- Steering Control -->
            <div class="glass p-6 rounded-[2.5rem] flex flex-col items-center justify-center relative">
                <div class="absolute top-4 left-6">
                    <h3 class="text-[10px] font-bold uppercase tracking-widest text-slate-400">Steering Control</h3>
                </div>
                <div class="mt-8 mb-4">
                    <div id="joystick" class="relative w-36 h-36 rounded-full border border-slate-700/50 flex items-center justify-center bg-slate-900/30">
                        <div class="absolute inset-0 border border-white/5 rounded-full scale-75"></div>
                        <div class="absolute w-[1px] h-full bg-white/5 left-1/2 -translate-x-1/2"></div>
                        <div class="absolute h-[1px] w-full bg-white/5 top-1/2 -translate-y-1/2"></div>
                        <div id="joystickHandle" class="w-20 h-20 rounded-full bg-primary shadow-[0_0_30px_rgba(59,130,246,0.5)] flex items-center justify-center text-white cursor-pointer transition-all duration-200 ease-out"></div>
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
                <div id="velocityDial" class="velocity-dial relative w-40 h-40 rounded-full bg-[#19243d] flex items-center justify-center select-none cursor-pointer">
                    <svg class="absolute inset-0 w-full h-full" viewBox="0 0 160 160">
                        <g transform="rotate(-135 80 80)">
                            <circle id="velocityArcBg" cx="80" cy="80" r="76" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="9" stroke-linecap="round"/>
                            <circle id="velocityArcFg" cx="80" cy="80" r="76" fill="none" stroke="#3B82F6" stroke-width="9" stroke-linecap="round"/>
                        </g>
                    </svg>
                    <div id="velocityGlow" class="absolute" style="width:20px;height:20px;border-radius:10px;background:#3B82F6;opacity:0.4;pointer-events:none;"></div>
                    <div id="velocityHandle" class="absolute" style="width:16px;height:16px;border-radius:8px;background:#4F8DF9;pointer-events:none;"></div>
                    <div class="text-center z-10">
                        <div id="speedValue" class="text-4xl font-semibold text-slate-200">0</div>
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
            <div class="space-y-4">
                <div class="flex flex-col gap-1">
                    <label class="text-[8px] font-bold uppercase tracking-wider text-slate-400">Raspberry Pi IP</label>
                    <div class="relative">
                        <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">router</span>
                        <input id="raspiIp" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-3 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="192.168.1.100" type="text"/>
                    </div>
                </div>
                <div class="flex flex-col gap-1">
                    <label class="text-[8px] font-bold uppercase tracking-wider text-slate-400">Ports</label>
                    <div class="grid grid-cols-2 gap-2">
                        <div class="relative">
                            <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">lan</span>
                            <input id="hostPort" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-2 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="Host:8000" type="text"/>
                        </div>
                        <div class="relative">
                            <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">settings_ethernet</span>
                            <input id="raspiPort" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-2 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="Raspi:8001" type="text"/>
                        </div>
                    </div>
                </div>
                <button id="startBtn" class="w-full bg-green-500/20 text-green-500 border border-green-500/30 rounded-lg py-2 text-sm font-bold hover:bg-green-500/30 transition-colors flex items-center justify-center gap-2">
                    <span class="material-icons-round text-sm">play_arrow</span>
                    START
                </button>
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
        const velocityDial = document.getElementById('velocityDial');
        const velocityArcBg = document.getElementById('velocityArcBg');
        const velocityArcFg = document.getElementById('velocityArcFg');
        const velocityHandle = document.getElementById('velocityHandle');
        const velocityGlow = document.getElementById('velocityGlow');
        const steeringMode = document.getElementById('steeringMode');
        const startBtn = document.getElementById('startBtn');
        const deviceInfo = document.getElementById('deviceInfo');
        const cpuInfo = document.getElementById('cpuInfo');
        const latencyInfo = document.getElementById('latencyInfo');
        const videoCanvas = document.getElementById('videoCanvas');
        const steeringStatus = document.getElementById('steeringStatus');
        
        let autonomousMode = false;
        let currentSpeed = 0;
        let joystickActive = false;
        let velocityActive = false;
        
        const velocityConfig = {
            min: 0,
            max: 255,
            startAngle: -135,
            sweep: 270,
            radius: 76
        };
        
        const velocityCircumference = 2 * Math.PI * velocityConfig.radius;
        const velocityArcLength = velocityCircumference * (velocityConfig.sweep / 360);
        
        if (velocityArcBg && velocityArcFg) {
            velocityArcBg.style.strokeDasharray = `${velocityArcLength} ${velocityCircumference}`;
            velocityArcFg.style.strokeDasharray = `0 ${velocityCircumference}`;
        }
        
        function updateVelocityDial(value) {
            const ratio = Math.max(0, Math.min(1, (value - velocityConfig.min) / (velocityConfig.max - velocityConfig.min)));
            const arcValue = velocityArcLength * ratio;
            
            if (velocityArcFg) {
                velocityArcFg.style.strokeDasharray = `${arcValue} ${velocityCircumference}`;
            }
            
            const angle = velocityConfig.startAngle + ratio * velocityConfig.sweep;
            const rad = angle * Math.PI / 180;
            const x = Math.cos(rad) * velocityConfig.radius;
            const y = Math.sin(rad) * velocityConfig.radius;
            
            if (velocityHandle) {
                velocityHandle.style.transform = `translate(-50%, -50%) translate(${x}px, ${y}px)`;
            }
            if (velocityGlow) {
                velocityGlow.style.transform = `translate(-50%, -50%) translate(${x}px, ${y}px)`;
            }
        }
        
        function setVelocityValue(value, options = {}) {
            const { send = false } = options;
            const clamped = Math.round(Math.max(velocityConfig.min, Math.min(velocityConfig.max, value)));
            
            currentSpeed = clamped;
            speedValue.textContent = clamped;
            updateVelocityDial(clamped);
            
            if (send) {
                ws.send(JSON.stringify({
                    type: 'speed',
                    value: clamped
                }));
            }
        }
        
        if (velocityHandle) {
            velocityHandle.style.left = '50%';
            velocityHandle.style.top = '50%';
        }
        if (velocityGlow) {
            velocityGlow.style.left = '50%';
            velocityGlow.style.top = '50%';
        }
        setVelocityValue(0, { send: false });
        
        
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
                const nextSpeed = data.speed ?? data.value ?? 0;
                setVelocityValue(nextSpeed, { send: false });
            }
        };
        
        // Traditional joystick controls
        function startJoystick(e) {
            if (autonomousMode) return;
            
            joystickActive = true;
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
            
            joystickHandle.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
            
            // Send position
            ws.send(JSON.stringify({
                type: 'joystick',
                x: deltaX / maxDistance,
                y: -deltaY / maxDistance,
                speed: currentSpeed
            }));
        }
        
        function endJoystick() {
            if (!joystickActive) return;
            
            joystickActive = false;
            
            // Reset handle to center with smooth animation
            joystickHandle.style.transform = 'translate(0px, 0px)';
            
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
            const ip = raspiIp.value;
            const hPort = hostPort.value;
            const rPort = raspiPort.value;
            
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
            const ip = raspiIp.value;
            const port = raspiPort.value;
            
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
        
        function updateVelocityFromPointer(clientX, clientY, send) {
            if (!velocityDial || autonomousMode) return;
            const rect = velocityDial.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 2;
            const dx = clientX - cx;
            const dy = clientY - cy;
            
            let deg = Math.atan2(dy, dx) * 180 / Math.PI;
            const start = velocityConfig.startAngle;
            const end = velocityConfig.startAngle + velocityConfig.sweep;
            
            if (deg < start) deg = start;
            if (deg > end) deg = end;
            
            const ratio = (deg - start) / velocityConfig.sweep;
            const value = velocityConfig.min + ratio * (velocityConfig.max - velocityConfig.min);
            setVelocityValue(value, { send });
        }
        
        if (velocityDial) {
            velocityDial.addEventListener('pointerdown', function(e) {
                velocityActive = true;
                velocityDial.setPointerCapture(e.pointerId);
                updateVelocityFromPointer(e.clientX, e.clientY, true);
            });
            
            velocityDial.addEventListener('pointermove', function(e) {
                if (!velocityActive) return;
                updateVelocityFromPointer(e.clientX, e.clientY, true);
            });
            
            const endVelocityDrag = function(e) {
                if (!velocityActive) return;
                velocityActive = false;
                if (velocityDial.hasPointerCapture(e.pointerId)) {
                    velocityDial.releasePointerCapture(e.pointerId);
                }
            };
            
            velocityDial.addEventListener('pointerup', endVelocityDrag);
            velocityDial.addEventListener('pointercancel', endVelocityDrag);
        }
        
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
        
        // Keyboard controls (WASD + arrows, supports diagonal)
        const pressedKeys = new Set();
        const validKeys = new Set(['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright']);
        
        function updateKeyboardJoystick() {
            if (autonomousMode || joystickActive || velocityActive) return;
            
            const rect = joystick.getBoundingClientRect();
            const maxDistance = rect.width / 2 - joystickHandle.offsetWidth / 2;
            
            const up = pressedKeys.has('w') || pressedKeys.has('arrowup');
            const down = pressedKeys.has('s') || pressedKeys.has('arrowdown');
            const left = pressedKeys.has('a') || pressedKeys.has('arrowleft');
            const right = pressedKeys.has('d') || pressedKeys.has('arrowright');
            
            let x = 0;
            let y = 0;
            
            if (up && !down) y = -maxDistance;
            if (down && !up) y = maxDistance;
            if (left && !right) x = -maxDistance;
            if (right && !left) x = maxDistance;
            
            joystickHandle.style.transform = `translate(${x}px, ${y}px)`;
            
            ws.send(JSON.stringify({
                type: 'joystick',
                x: maxDistance ? x / maxDistance : 0,
                y: maxDistance ? -y / maxDistance : 0,
                speed: currentSpeed
            }));
        }
        
        document.addEventListener('keydown', function(e) {
            const key = e.key.toLowerCase();
            if (!validKeys.has(key)) return;
            
            pressedKeys.add(key);
            updateKeyboardJoystick();
        });
        
        document.addEventListener('keyup', function(e) {
            const key = e.key.toLowerCase();
            if (!validKeys.has(key)) return;
            
            pressedKeys.delete(key);
            updateKeyboardJoystick();
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
