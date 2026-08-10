# fine-tune YOLOv11 with SG License Plate dataset
from ultralytics import YOLO

model = YOLO("checkpoints/yolo11n.pt")

results = model.train(
    data="../sg_plate_dataset/data.yaml",
    epochs=80,
    imgsz=640
)