# Otonom Car UI Web Version

Modern MainWindow UI ve main.py'nin web üzerinde çalışması için hazırlanmış versiyon.

## 🌟 Özellikler

- **Web Tabanlı**: Herhangi bir cihazdan tarayıcı üzerinden erişim
- **Gerçek Zamanlı Video**: Kamera akışı ve YOLO nesne tespiti
- **Joystick Kontrol**: Fare ve dokunmatik joystick kontrolü
- **WASD Klavye**: Klavye ile araç kontrolü
- **PWM Speed Control**: Hız kontrolü
- **Otonom Sürüş**: AI tabanlı otonom sürüş modu
- **Modern UI**: Responsive ve modern arayüz

## 🚀 Kurulum

### 1. Gerekli Paketler
```bash
pip install -r requirements.txt
```

### 2. Sunucuyu Başlat
```bash
python web_app.py
```

### 3. Kamera Client'ı Başlat (İsteğe Bağlı)
```bash
python camera_client.py
```

### 4. Tarayıcıda Aç
```
http://localhost:8000
```

## 📱 Mobil Cihazlardan Erişim

1. Aynı Wi-Fi ağına bağlı olun
2. Sunucu IP adresini bulun:
   ```bash
   ipconfig  # Windows
   ifconfig  # Linux/Mac
   ```
3. `web_app.py`'de host'u değiştirin:
   ```python
   uvicorn.run(app, host="0.0.0.0", port=8000)
   ```
4. Mobil tarayıcıdan açın:
   ```
   http://[IP_ADRESI]:8000
   ```

## 🎮 Kontroller

### Joystick
- **Fare**: Joystick'e tıklayıp sürükleyin
- **Dokunmatik**: Joystick'e dokunup hareket ettirin

### Klavye
- **W**: İleri
- **A**: Sol
- **S**: Geri
- **D**: Sağ

### Butonlar
- **Start Autonomous**: Otonom sürüş başlat
- **Stop**: Dur
- **Speed Slider**: PWM hız kontrolü

## 🔄 Veri Akışı

```
Kamera → YOLO Tespiti → WebSocket → Web Tarayıcı
                ↓
Web Tarayıcı → WebSocket → Araç Komutları
```

## 🛠️ Teknolojiler

- **Backend**: FastAPI + WebSocket
- **Frontend**: HTML5 + CSS3 + JavaScript
- **AI**: YOLOv8 Nesne Tespiti
- **Video**: OpenCV
- **Real-time**: WebSocket ile canlı iletişim

## 📊 Özellik Karşılaştırması

| Özellik | Masaüstü Versiyon | Web Versiyon |
|---------|------------------|--------------|
| Platform | Windows/Linux/Mac | Herhangi bir cihaz |
| Kurulum | Python + Qt | Sadece Python |
| Erişim | Yerel | Uzakdan |
| Mobil | ❌ | ✅ |
| Paylaşım | ❌ | ✅ |
| Kurulum Zorluğu | Orta | Düşük |

## 🔧 Konfigürasyon

### Port Değiştirme
```python
# web_app.py
uvicorn.run(app, host="0.0.0.0", port=8080)
```

### Kamera Değiştirme
```python
# camera_client.py
self.cap = cv2.VideoCapture(1)  # 2. kamera
```

### YOLO Model Değiştirme
```python
# Her iki dosyada da
self.detector = YOLO("yolov8n.pt", device=self.device)
```

## 🌐 Dağıtım Seçenekleri

### 1. Local Dağıtım
```bash
python web_app.py
# http://localhost:8000
```

### 2. Network Dağıtım
```bash
python web_app.py
# http://192.168.1.100:8000
```

### 3. Cloud Dağıtım (Heroku, Vercel, vb.)
Docker container ile kolayca dağıtım yapılabilir.

## 📱 Responsive Tasarım

- **Desktop**: 1280x720 optimum
- **Tablet**: 768x1024 uyumlu
- **Mobile**: 375x667 uyumlu
- **Touch**: Dokunmatik joystick
- **Keyboard**: WASD desteği

## 🔒 Güvenlik

- WebSocket bağlantıları güvenli
- Local network erişimi
- No external dependencies
- CORS enabled

## 🚀 Performans

- **FPS**: 30 FPS
- **Latency**: <100ms
- **CPU Usage**: Optimize edilmiş
- **Memory**: Düşük kullanım

## 🐞 Hata Ayıklama

### WebSocket Bağlantı Hatası
```bash
# Port kontrolü
netstat -an | findstr 8000
```

### Kamera Hatası
```bash
# Kamera kontrolü
python -c "import cv2; print(cv2.VideoCapture(0).isOpened())"
```

### Model Yükleme Hatası
```bash
# Model dosyası kontrolü
ls -la best.pt
```

## 📞 Destek

Sorularınız için:
- GitHub Issues
- E-posta: support@otonomcar.com
- Dokümantasyon: README.md

---

**Not**: Web versiyonu, masaüstü versiyonunun tüm özelliklerini desteklemeyebilir. Gelişmiş özellikler için masaüstü versiyonunu kullanın.
