from ultralytics import YOLO

model = YOLO("yolo11n.pt")
model.export(format="imx", data="coco8.yaml") 
