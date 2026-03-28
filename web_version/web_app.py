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
from pathlib import Path

app = FastAPI()

# YOLO modelini yükle
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Using: {device}")
model_path = Path(__file__).resolve().parent.parent / "yolov8n.pt"
detector = YOLO(str(model_path))
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
camera_task = None
camera_task_lock = asyncio.Lock()
MAX_TCP_FRAME_BYTES = 5 * 1024 * 1024
host_writer = None
host_reader_task = None
host_task_lock = asyncio.Lock()
host_send_lock = asyncio.Lock()
HOST_CONNECT_TIMEOUT = 5
DETECT_EVERY_N = 3
DETECT_MIN_INTERVAL = 0.2

async def broadcast_camera_status(status: str, detail: str = None):
    payload = {"type": "camera_status", "status": status}
    if detail:
        payload["detail"] = detail
    await manager.broadcast(json.dumps(payload))

async def broadcast_host_status(status: str, detail: str = None):
    payload = {"type": "host_status", "status": status}
    if detail:
        payload["detail"] = detail
    await manager.broadcast(json.dumps(payload))

async def camera_tcp_loop(ip: str, port: int):
    try:
        reader, writer = await asyncio.open_connection(ip, port)
    except Exception as e:
        await broadcast_camera_status("failed", str(e))
        return
    await broadcast_camera_status("starting")
    started_sent = False
    buffer = bytearray()
    frame_index = 0
    last_detect_ts = 0.0
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            buffer.extend(chunk)

            while buffer:
                if buffer and buffer[0] in (ord("{"), ord("[")):
                    nl_index = buffer.find(b"\n")
                    if nl_index == -1:
                        break
                    line = bytes(buffer[:nl_index]).strip()
                    del buffer[: nl_index + 1]
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    await manager.broadcast(json.dumps(msg))
                    continue

                start = buffer.find(b"\xff\xd8")
                if start == -1:
                    if len(buffer) > MAX_TCP_FRAME_BYTES * 2:
                        buffer[:] = buffer[-2:]
                    break
                if start > 0:
                    del buffer[:start]
                end = buffer.find(b"\xff\xd9", 2)
                if end == -1:
                    if len(buffer) > MAX_TCP_FRAME_BYTES * 2:
                        buffer.clear()
                    break
                frame = bytes(buffer[: end + 2])
                del buffer[: end + 2]
                if len(frame) > MAX_TCP_FRAME_BYTES:
                    continue
                frame_index += 1
                now = time.time()
                do_detect = (frame_index % DETECT_EVERY_N == 0) and (now - last_detect_ts >= DETECT_MIN_INTERVAL)
                if do_detect:
                    last_detect_ts = now
                    try:
                        np_frame = np.frombuffer(frame, dtype=np.uint8)
                        decoded = cv2.imdecode(np_frame, cv2.IMREAD_COLOR)
                    except Exception:
                        decoded = None
                    if decoded is None:
                        frame_b64 = base64.b64encode(frame).decode("utf-8")
                        await manager.broadcast(json.dumps({"type": "frame", "frame": frame_b64}))
                    else:
                        try:
                            results = detector(decoded)
                            annotated = results[0].plot()
                            ok, buffer_jpg = cv2.imencode(".jpg", annotated)
                            if not ok:
                                raise ValueError("encode failed")
                            frame_b64 = base64.b64encode(buffer_jpg).decode("utf-8")
                        except Exception:
                            frame_b64 = base64.b64encode(frame).decode("utf-8")
                        await manager.broadcast(json.dumps({"type": "frame", "frame": frame_b64}))
                else:
                    frame_b64 = base64.b64encode(frame).decode("utf-8")
                    await manager.broadcast(json.dumps({"type": "frame", "frame": frame_b64}))
                if not started_sent:
                    started_sent = True
                    await broadcast_camera_status("started")
    except asyncio.CancelledError:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        if started_sent:
            await broadcast_camera_status("failed", "disconnected")

async def start_camera_tcp_proxy(ip: str, port: int):
    global camera_task
    async with camera_task_lock:
        if camera_task and not camera_task.done():
            camera_task.cancel()
            try:
                await camera_task
            except Exception:
                pass
        camera_task = asyncio.create_task(camera_tcp_loop(ip, port))

async def host_read_loop(reader: asyncio.StreamReader):
    try:
        while True:
            data = await reader.read(1)
            if not data:
                break
    except asyncio.CancelledError:
        pass
    finally:
        await broadcast_host_status("failed", "disconnected")

async def start_host_tcp_connection(ip: str, port: int):
    global host_writer, host_reader_task
    async with host_task_lock:
        if host_reader_task and not host_reader_task.done():
            host_reader_task.cancel()
            try:
                await host_reader_task
            except Exception:
                pass
        if host_writer:
            try:
                host_writer.close()
                await host_writer.wait_closed()
            except Exception:
                pass
            host_writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=HOST_CONNECT_TIMEOUT)
        except Exception as e:
            await broadcast_host_status("failed", str(e))
            return
        host_writer = writer
        await broadcast_host_status("started")
        host_reader_task = asyncio.create_task(host_read_loop(reader))

async def send_host_command(cmd: str):
    global host_writer
    if not host_writer:
        return
    async with host_send_lock:
        try:
            host_writer.write((cmd + "\n").encode("utf-8"))
            await host_writer.drain()
        except Exception as e:
            await broadcast_host_status("failed", str(e))
            try:
                host_writer.close()
                await host_writer.wait_closed()
            except Exception:
                pass
            host_writer = None

# HTML Template
HTML_TEMPLATE = r"""
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
        .spinner {
            width: 28px;
            height: 28px;
            border: 3px solid rgba(148, 163, 184, 0.35);
            border-top-color: #3b82f6;
            border-radius: 9999px;
            animation: spin 0.9s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
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
                    <label class="text-[8px] font-bold uppercase tracking-wider text-slate-400">IP</label>
                    <div class="relative">
                        <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">dns</span>
                        <input id="deviceIp" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-3 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="192.168.34.43" type="text"/>
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
                            <span class="material-icons-round absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-xs">videocam</span>
                            <input id="camPort" class="w-full bg-slate-800/50 border border-slate-700/50 rounded-lg pl-8 pr-2 py-1.5 text-xs focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all text-slate-200 outline-none" placeholder="Cam:8001" type="text"/>
                        </div>
                    </div>
                </div>
                <button id="startBtn" class="w-full bg-green-500/20 text-green-500 border border-green-500/30 rounded-lg py-2 text-sm font-bold hover:bg-green-500/30 transition-colors flex items-center justify-center gap-2">
                    <span class="material-icons-round text-sm">play_arrow</span>
                    CONNECT
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

    <!-- Connection Dialog -->
    <div id="connectionDialog" class="fixed inset-0 hidden items-center justify-center bg-black/50 backdrop-blur-sm z-50">
        <div class="glass w-[90%] max-w-sm p-5 rounded-2xl border border-white/10 space-y-4">
            <div class="flex items-center gap-3">
                <div class="spinner"></div>
                <div class="flex flex-col">
                    <span class="text-sm font-semibold">Baglaniyor...</span>
                    <span id="connectionSummary" class="text-xs text-slate-400">Baslatiliyor...</span>
                </div>
            </div>
            <div class="space-y-1 text-xs">
                <div class="flex justify-between">
                    <span class="text-slate-400">Host</span>
                    <span id="hostStatus" class="text-yellow-400 font-semibold">Bekleniyor...</span>
                </div>
                <div class="flex justify-between">
                    <span class="text-slate-400">Camera</span>
                    <span id="cameraStatus" class="text-yellow-400 font-semibold">Bekleniyor...</span>
                </div>
            </div>
            <div class="space-y-1 text-[10px] text-slate-400 font-mono break-all">
                <div>
                    <span class="text-slate-500">Host URL:</span>
                    <span id="hostUrlText">-</span>
                </div>
                <div>
                    <span class="text-slate-500">Camera URL:</span>
                    <span id="cameraUrlText">-</span>
                </div>
            </div>
            <button id="connectionCloseBtn" class="w-full bg-slate-700/50 hover:bg-slate-700 text-slate-100 rounded-lg py-2 text-sm font-semibold">
                OK
            </button>
        </div>
    </div>

    <script>
        const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws`);
        let wsReady = false;
        let hostConnected = false;
        let cameraConnected = false;
        let hostResolved = false;
        let cameraResolved = false;
        let hostTimeoutId = null;
        let cameraTimeoutId = null;
        
        // Control elements
        const joystick = document.getElementById('joystick');
        const joystickHandle = document.getElementById('joystickHandle');
        const autonomousBtn = document.getElementById('autonomousBtn');
        
        // Connection controls
        const deviceIp = document.getElementById('deviceIp');
        const hostPort = document.getElementById('hostPort');
        const camPort = document.getElementById('camPort');
        
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
        const connectionDialog = document.getElementById('connectionDialog');
        const connectionSummary = document.getElementById('connectionSummary');
        const hostStatus = document.getElementById('hostStatus');
        const cameraStatus = document.getElementById('cameraStatus');
        const connectionCloseBtn = document.getElementById('connectionCloseBtn');
        const hostUrlText = document.getElementById('hostUrlText');
        const cameraUrlText = document.getElementById('cameraUrlText');

        if (deviceIp && !deviceIp.value) {
            deviceIp.value = window.location.hostname || 'localhost';
        }
        if (hostPort && !hostPort.value && window.location.port) {
            hostPort.value = window.location.port;
        }
        
        ws.onopen = function() {
            wsReady = true;
        };
        
        ws.onclose = function() {
            wsReady = false;
        };
        
        ws.onmessage = handleWsMessage;

        function setDialogVisible(visible) {
            if (!connectionDialog) return;
            if (visible) {
                connectionDialog.classList.remove('hidden');
                connectionDialog.classList.add('flex');
            } else {
                connectionDialog.classList.add('hidden');
                connectionDialog.classList.remove('flex');
            }
        }

        function setStatus(el, state) {
            if (!el) return;
            el.classList.remove('text-green-400', 'text-red-400', 'text-yellow-400');
            if (state === 'started') {
                el.textContent = 'Basladi';
                el.classList.add('text-green-400');
            } else if (state === 'failed') {
                el.textContent = 'Baslamadi';
                el.classList.add('text-red-400');
            } else {
                el.textContent = 'Bekleniyor...';
                el.classList.add('text-yellow-400');
            }
        }

        function updateConnectionSummary() {
            if (!connectionSummary) return;
            if (!hostResolved || !cameraResolved) {
                connectionSummary.textContent = 'Baslatiliyor...';
                setStartButtonState('connecting');
                return;
            }
            if (hostConnected && cameraConnected) {
                connectionSummary.textContent = 'Host ve Kamera basladi';
                setStartButtonState('success');
            } else if (hostConnected && !cameraConnected) {
                connectionSummary.textContent = 'Sadece Host basladi';
                setStartButtonState('partial');
            } else if (!hostConnected && cameraConnected) {
                connectionSummary.textContent = 'Sadece Kamera basladi';
                setStartButtonState('partial');
            } else {
                connectionSummary.textContent = 'Host ve Kamera baslamadi';
                setStartButtonState('failed');
            }
        }

        function setStartButtonState(state) {
            if (!startBtn) return;
            startBtn.disabled = state === 'connecting';
            startBtn.classList.remove(
                'bg-green-500/20', 'text-green-500', 'border-green-500/30',
                'bg-yellow-500/20', 'text-yellow-500', 'border-yellow-500/30',
                'bg-red-500/20', 'text-red-500', 'border-red-500/30'
            );
            if (state === 'connecting') {
                startBtn.innerHTML = '<span class="material-icons-round text-xs">refresh</span>CONNECTING...';
                startBtn.classList.add('bg-yellow-500/20', 'text-yellow-500', 'border-yellow-500/30');
            } else if (state === 'success') {
                startBtn.innerHTML = '<span class="material-icons-round text-xs">check_circle</span>CONNECTED';
                startBtn.classList.add('bg-green-500/20', 'text-green-500', 'border-green-500/30');
            } else if (state === 'partial') {
                startBtn.innerHTML = '<span class="material-icons-round text-xs">check_circle</span>PARTIAL';
                startBtn.classList.add('bg-yellow-500/20', 'text-yellow-500', 'border-yellow-500/30');
            } else if (state === 'failed') {
                startBtn.innerHTML = '<span class="material-icons-round text-xs">cancel</span>FAILED';
                startBtn.classList.add('bg-red-500/20', 'text-red-500', 'border-red-500/30');
            } else {
                startBtn.innerHTML = '<span class="material-icons-round text-sm">play_arrow</span>CONNECT';
                startBtn.classList.add('bg-green-500/20', 'text-green-500', 'border-green-500/30');
            }
        }

        function sendToHost(payload) {
            if (!wsReady || ws.readyState !== WebSocket.OPEN) return false;
            ws.send(JSON.stringify(payload));
            return true;
        }

        function handleWsMessage(event) {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return;
            }
            if (data.type === 'frame') {
                videoCanvas.src = 'data:image/jpeg;base64,' + data.frame;
                latencyInfo.textContent = data.latency || '12';
                deviceInfo.textContent = `${data.device || 'CUDA:0'} - 45C`;
                cpuInfo.textContent = `CPU: ${data.cpu || '12'}%`;
            } else if (data.type === 'host_status') {
                if (data.status === 'starting') {
                    hostResolved = false;
                    hostConnected = false;
                    setStatus(hostStatus, 'pending');
                    updateConnectionSummary();
                } else {
                    hostResolved = true;
                    hostConnected = data.status === 'started';
                    setStatus(hostStatus, hostConnected ? 'started' : 'failed');
                    if (hostTimeoutId) {
                        clearTimeout(hostTimeoutId);
                        hostTimeoutId = null;
                    }
                    updateConnectionSummary();
                }
            } else if (data.type === 'camera_status') {
                if (data.status === 'starting') {
                    cameraResolved = false;
                    cameraConnected = false;
                    setStatus(cameraStatus, 'pending');
                    updateConnectionSummary();
                } else {
                    cameraResolved = true;
                    cameraConnected = data.status === 'started';
                    setStatus(cameraStatus, cameraConnected ? 'started' : 'failed');
                    updateConnectionSummary();
                    if (cameraTimeoutId) {
                        clearTimeout(cameraTimeoutId);
                        cameraTimeoutId = null;
                    }
                }
            } else if (data.type === 'speed') {
                const nextSpeed = data.speed ?? data.value ?? 0;
                setVelocityValue(nextSpeed, { send: false });
            }
        }
        
        function parseAddressInput(value) {
            const raw = (value || '').trim();
            if (!raw) return { scheme: '', ip: '', port: '' };
            
            let scheme = '';
            let rest = raw;
            const schemeMatch = raw.match(/^(wss?|tcp):\/\/(.+)$/i);
            if (schemeMatch) {
                scheme = schemeMatch[1].toLowerCase();
                rest = schemeMatch[2];
            }
            
            let ip = '';
            let port = '';
            if (rest.includes(' ')) {
                const parts = rest.split(/\s+/);
                ip = parts[0] || '';
                port = parts[1] || '';
            } else if (rest.includes(':')) {
                const parts = rest.split(':');
                ip = parts[0] || '';
                port = parts[1] || '';
            } else if (/^\d+$/.test(rest)) {
                port = rest;
            } else {
                ip = rest;
            }
            
            return { scheme, ip, port };
        }
        
        function resolveAddress(ipValue, portValue) {
            const fromIp = parseAddressInput(ipValue);
            const fromPort = parseAddressInput(portValue);
            return {
                scheme: fromPort.scheme || fromIp.scheme || '',
                ip: fromPort.ip || fromIp.ip || '',
                port: fromPort.port || fromIp.port || ''
            };
        }
        
        function schemeToWs(scheme, fallbackSecure) {
            if (scheme === 'ws' || scheme === 'wss') return scheme;
            if (scheme === 'tcp') return 'ws';
            if (fallbackSecure) return 'wss';
            return window.location.protocol === 'https:' ? 'wss' : 'ws';
        }
        
        function buildWsUrlFromAddress(address, fallbackSecure) {
            if (!address || !address.ip) return null;
            const wsScheme = schemeToWs((address.scheme || '').toLowerCase(), fallbackSecure);
            return address.port ? `${wsScheme}://${address.ip}:${address.port}/ws` : `${wsScheme}://${address.ip}/ws`;
        }

        function connectWebSocket(url, statusEl) {
            return new Promise((resolve) => {
                if (!url) {
                    if (statusEl) setStatus(statusEl, 'failed');
                    return resolve({ ok: false, ws: null });
                }
                let socket;
                try {
                    socket = new WebSocket(url);
                } catch (e) {
                    if (statusEl) setStatus(statusEl, 'failed');
                    return resolve({ ok: false, ws: null });
                }
                let settled = false;
                const timeoutId = setTimeout(() => {
                    if (settled) return;
                    settled = true;
                    try { socket.close(); } catch (e) {}
                    if (statusEl) setStatus(statusEl, 'failed');
                    resolve({ ok: false, ws: null });
                }, 5000);
                socket.onopen = function() {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timeoutId);
                    if (statusEl) setStatus(statusEl, 'started');
                    resolve({ ok: true, ws: socket });
                };
                socket.onerror = function() {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timeoutId);
                    if (statusEl) setStatus(statusEl, 'failed');
                    resolve({ ok: false, ws: null });
                };
            });
        }

        
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
                sendToHost({
                    type: 'speed',
                    value: clamped
                });
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
        
        
        // WebSocket events are attached per connection
        
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
            sendToHost({
                type: 'joystick',
                x: deltaX / maxDistance,
                y: -deltaY / maxDistance,
                speed: currentSpeed
            });
        }
        
        function endJoystick() {
            if (!joystickActive) return;
            
            joystickActive = false;
            
            // Reset handle to center with smooth animation
            joystickHandle.style.transform = 'translate(0px, 0px)';
            
            // Send stop command
            sendToHost({
                type: 'joystick',
                x: 0,
                y: 0,
                speed: 0
            });
            
            document.removeEventListener('mousemove', moveJoystick);
            document.removeEventListener('mouseup', endJoystick);
            document.removeEventListener('touchmove', moveJoystick);
            document.removeEventListener('touchend', endJoystick);
        }
        
        // Connection info
        function sendConnectionInfo() {
            const hostAddress = resolveAddress(deviceIp ? deviceIp.value : '', hostPort ? hostPort.value : '');
            const camAddress = resolveAddress(deviceIp ? deviceIp.value : '', camPort ? camPort.value : '');
            
            sendToHost({
                type: 'connect',
                host_ip: hostAddress.ip,
                host_port: hostAddress.port,
                cam_ip: camAddress.ip,
                cam_port: camAddress.port
            });
        }
        
        // Start button functionality
        async function startConnection() {
            if (!startBtn || startBtn.disabled) return;
            
            setDialogVisible(true);
            if (connectionSummary) {
                connectionSummary.textContent = 'Baslatiliyor...';
            }
            setStatus(hostStatus, 'pending');
            setStatus(cameraStatus, 'pending');
            setStartButtonState('connecting');
            
            hostConnected = false;
            cameraConnected = false;
            hostResolved = false;
            cameraResolved = false;
            if (hostTimeoutId) {
                clearTimeout(hostTimeoutId);
                hostTimeoutId = null;
            }
            if (cameraTimeoutId) {
                clearTimeout(cameraTimeoutId);
                cameraTimeoutId = null;
            }
            if (videoCanvas) {
                videoCanvas.src = '';
            }
            
            const defaultHost = window.location.hostname || 'localhost';
            
            const hostAddress = resolveAddress(deviceIp ? deviceIp.value : '', hostPort ? hostPort.value : '');
            const camAddress = resolveAddress(deviceIp ? deviceIp.value : '', camPort ? camPort.value : '');
            
            if (!hostAddress.ip) hostAddress.ip = defaultHost;
            if (!camAddress.ip) camAddress.ip = hostAddress.ip;
            
            const hostUrl = (hostAddress.ip && hostAddress.port) ? `tcp://${hostAddress.ip}:${hostAddress.port}` : null;
            const camUrl = (camAddress.ip && camAddress.port) ? `tcp://${camAddress.ip}:${camAddress.port}` : null;

            if (hostUrlText) hostUrlText.textContent = hostUrl || '-';
            if (cameraUrlText) cameraUrlText.textContent = camUrl || '-';

            if (!wsReady) {
                hostResolved = true;
                cameraResolved = true;
                setStatus(hostStatus, 'failed');
                setStatus(cameraStatus, 'failed');
                updateConnectionSummary();
                return;
            }
            
            sendToHost({
                type: 'connect',
                host_ip: hostAddress.ip,
                host_port: hostAddress.port,
                cam_ip: camAddress.ip,
                cam_port: camAddress.port
            });
            
            if (hostUrl) {
                hostTimeoutId = setTimeout(() => {
                    if (hostResolved) return;
                    hostResolved = true;
                    hostConnected = false;
                    setStatus(hostStatus, 'failed');
                    updateConnectionSummary();
                }, 5000);
            } else {
                hostResolved = true;
                hostConnected = false;
                setStatus(hostStatus, 'failed');
            }
            
            if (camUrl) {
                cameraTimeoutId = setTimeout(() => {
                    if (cameraResolved) return;
                    cameraResolved = true;
                    cameraConnected = false;
                    setStatus(cameraStatus, 'failed');
                    updateConnectionSummary();
                }, 5000);
            } else {
                cameraResolved = true;
                cameraConnected = false;
                setStatus(cameraStatus, 'failed');
            }
            
            updateConnectionSummary();
        }
        
        // Event listeners
        if (connectionCloseBtn) {
            connectionCloseBtn.addEventListener('click', function() {
                setDialogVisible(false);
            });
        }
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
        
        // Connection input listeners
        if (deviceIp) deviceIp.addEventListener('change', sendConnectionInfo);
        if (hostPort) hostPort.addEventListener('change', sendConnectionInfo);
        if (camPort) camPort.addEventListener('change', sendConnectionInfo);
        
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
                
                sendToHost({
                    type: 'autonomous',
                    enabled: true
                });
            } else {
                this.innerHTML = '<span class="material-icons-round">smart_toy</span><span>OTONOM SÜRÜŞÜ BAŞLAT</span>';
                this.classList.add('bg-primary');
                this.classList.remove('bg-red-500');
                
                // Update steering status
                steeringStatus.textContent = 'Active';
                steeringStatus.style.color = '#10B981';
                steeringMode.textContent = 'Manual';
                steeringMode.style.color = '#3b82f6';
                
                sendToHost({
                    type: 'autonomous',
                    enabled: false
                });
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
            
            sendToHost({
                type: 'joystick',
                x: maxDistance ? x / maxDistance : 0,
                y: maxDistance ? -y / maxDistance : 0,
                speed: currentSpeed
            });
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
                await send_host_command(command)
                
            elif message.get('type') == 'speed':
                # Send PWM speed command
                pwm_cmd = f"PWM{message['value']}"
                await manager.broadcast(json.dumps({'type': 'command', 'value': pwm_cmd}))
                await send_host_command(pwm_cmd)
                
            elif message.get('type') == 'autonomous':
                # Toggle autonomous mode
                mode_cmd = "AUTO" if message['enabled'] else "MANUAL"
                await manager.broadcast(json.dumps({'type': 'command', 'value': mode_cmd}))
                await send_host_command(mode_cmd)
                
            elif message.get('type') == 'stop':
                # Send stop command
                await manager.broadcast(json.dumps({'type': 'command', 'value': "S"}))
                await send_host_command("S")
                
            elif message.get('type') == 'key':
                # Handle WASD keys
                key = message['key']
                if message['pressed']:
                    if key == 'W':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "F"}))
                        await send_host_command("F")
                    elif key == 'S':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "B"}))
                        await send_host_command("B")
                    elif key == 'A':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "L"}))
                        await send_host_command("L")
                    elif key == 'D':
                        await manager.broadcast(json.dumps({'type': 'command', 'value': "R"}))
                        await send_host_command("R")
                else:
                    await manager.broadcast(json.dumps({'type': 'command', 'value': "S"}))
                    await send_host_command("S")

            elif message.get('type') == 'connect':
                host_ip = message.get('host_ip') or message.get('ip')
                host_port_value = message.get('host_port')
                cam_ip = message.get('cam_ip')
                cam_port_value = message.get('cam_port')

                try:
                    host_port = int(host_port_value) if host_port_value is not None else None
                except Exception:
                    host_port = None
                try:
                    cam_port = int(cam_port_value) if cam_port_value is not None else None
                except Exception:
                    cam_port = None

                if host_ip and host_port:
                    await broadcast_host_status("starting")
                    await start_host_tcp_connection(host_ip, host_port)
                else:
                    await broadcast_host_status("failed", "missing ip/port")

                if cam_ip and cam_port:
                    await broadcast_camera_status("starting")
                    await start_camera_tcp_proxy(cam_ip, cam_port)
                else:
                    await broadcast_camera_status("failed", "missing ip/port")

            elif message.get('type') == 'camera_connect':
                ip = message.get('ip') or message.get('cam_ip') or message.get('raspi_ip')
                port_value = message.get('port') or message.get('cam_port') or message.get('raspi_port')
                try:
                    port = int(port_value) if port_value is not None else None
                except Exception:
                    port = None

                if not ip or not port:
                    await broadcast_camera_status("failed", "missing ip/port")
                else:
                    await broadcast_camera_status("starting")
                    await start_camera_tcp_proxy(ip, port)
                    
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
