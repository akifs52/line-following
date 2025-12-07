from ultralytics import YOLO
import os
import multiprocessing

# Multiprocessing metodunu spawn olarak ayarla
multiprocessing.set_start_method('spawn', force=True)

# ==========================
# AYARLAR
# ==========================

DATA_YAML = "my_dataset/data.yaml"
MODEL_NAME = "yolov8n.pt"
EPOCHS = 100
IMG_SIZE = 640
BATCH = 16
DEVICE = 0
PROJECT = "runs"
EXP_NAME = "yolov8n_custom"

def train_model():
    model = YOLO(MODEL_NAME)
    
    model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        device=DEVICE,
        project=PROJECT,
        name=EXP_NAME,
        pretrained=True,
        workers=1,  # Sadece 1 worker
        exist_ok=True
    )

if __name__ == '__main__':
    # Windows için freeze support
    multiprocessing.freeze_support()
    
    if not os.path.exists(DATA_YAML):
        raise FileNotFoundError(f"data.yaml bulunamadı: {DATA_YAML}")
    
    print("✅ data.yaml bulundu")
    print("🚀 Eğitim başlıyor...")
    
    train_model()
    
    print("\n✅ Eğitim tamamlandı!")
    print(f"📁 Model yolu: {PROJECT}/detect/{EXP_NAME}/weights/best.pt")