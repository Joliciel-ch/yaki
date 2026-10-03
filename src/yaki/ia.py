import cv2
import numpy as np

from modlib.devices import AiCamera
from modlib.models import COLOR_FORMAT, MODEL_TYPE, Model
from modlib.models.post_processors import pp_od_yolo_ultralytics

from ultralytics.solutions import ObjectCounter


# ---------------------------------------------------------
# 1. Modèle YOLO pour IMX500 (chargé dans le processeur IA)
# ---------------------------------------------------------
class YOLO_IMX(Model):
    def __init__(self):
        super().__init__(
            model_file="yolo11n_imx_model/packerOut.zip",   # modèle converti pour IMX500
            model_type=MODEL_TYPE.CONVERTED,
            color_format=COLOR_FORMAT.RGB,
            preserve_aspect_ratio=False,
        )
        self.labels = np.genfromtxt(
            "yolo11n_imx_model/labels.txt",
            dtype=str,
            delimiter="\n"
        )

    def post_process(self, output_tensors):
        # Convertit les tenseurs IMX500 → format Ultralytics (xyxy, conf, cls)
        return pp_od_yolo_ultralytics(output_tensors)


# ---------------------------------------------------------
# 2. Initialisation IMX500
# ---------------------------------------------------------
device = AiCamera(frame_rate=16)
model = YOLO_IMX()
device.deploy(model)   # Le modèle est chargé dans le processeur IA du IMX500


# ---------------------------------------------------------
# 3. ObjectCounter Ultralytics (réutilisé tel quel)
# ---------------------------------------------------------
region_points = [(0, 0), (0, 0)]

counter = ObjectCounter(
    show=False,
    region=region_points,
    model=None,        # IMPORTANT : pas de modèle Ultralytics → on utilise IMX500
    classes=[0],       # Personnes (COCO class 0)
    verbose=False
)


# ---------------------------------------------------------
# 4. Boucle de traitement IMX500
# ---------------------------------------------------------
img = b''
results = None

with device as stream:
    for frame in stream:

        # frame.image = image RGB du IMX500
        # frame.detections = liste de détections déjà calculées par le processeur IA

        # Convertir les détections IMX500 → format Ultralytics Nx6
        dets = frame.detections

        if len(dets) > 0:
            xyxy = np.array([d.bbox for d in dets])
            conf = np.array([d.confidence for d in dets])
            cls = np.array([d.class_id for d in dets])

            ul_dets = np.column_stack([xyxy, conf, cls])

            # Comptage Ultralytics (sans ré-inférence)
            results = counter.process(
                frame.image,
                detections=ul_dets
            )

        # Encodage JPEG pour streaming / API
        _, imencode_image = cv2.imencode('.jpg', frame.image)
        img = imencode_image.tobytes()
