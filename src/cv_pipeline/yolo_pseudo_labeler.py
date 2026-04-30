"""
YOLO V1 Pseudo-Labeler

Runs the trained YOLO V1 model over unannotated real images (e.g. from Wikimedia)
and generates YOLO .txt label files based on the model's predictions.
These predictions are then zipped up for easy import into Label Studio for manual correction.

Usage:
    poetry run python src/cv_pipeline/yolo_pseudo_labeler.py
"""

import os
from pathlib import Path
from ultralytics import YOLO
import logging
import zipfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_PATH = Path("runs/detect/runs/glyph_detector/v1-2/weights/best.pt")
IMAGES_DIR = Path("data/real_yolo/images/train")
LABELS_DIR = Path("data/real_yolo/labels/train")
ZIP_OUT = Path("import_to_label_studio.zip")

def pseudo_label_images():
    if not MODEL_PATH.exists():
        logger.error(f"V1 Model not found at {MODEL_PATH}")
        return

    logger.info("Loading YOLO V1 Model...")
    model = YOLO(MODEL_PATH)

    LABELS_DIR.mkdir(parents=True, exist_ok=True)

    image_files = list(IMAGES_DIR.glob("*.jpg"))
    if not image_files:
        logger.warning("No images found to label.")
        return

    logger.info(f"Running inference on {len(image_files)} real images...")
    
    for img_path in image_files:
        # Run inference (conf=0.25 to catch more potential letters, user will delete false positives)
        results = model(img_path, conf=0.25, verbose=False)
        
        txt_path = LABELS_DIR / f"{img_path.stem}.txt"
        
        # Write predictions to YOLO .txt format
        with open(txt_path, "w") as f:
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # YOLO format: class x_center y_center width height
                    cls_id = int(box.cls[0].item())
                    # Normalized coordinates
                    xywhn = box.xywhn[0].tolist() 
                    f.write(f"{cls_id} {xywhn[0]:.6f} {xywhn[1]:.6f} {xywhn[2]:.6f} {xywhn[3]:.6f}\n")
                    
        logger.info(f"Pseudo-labeled {img_path.name} -> {len(results[0].boxes)} glyphs detected")

def create_label_studio_zip():
    logger.info(f"Packaging {ZIP_OUT.name} for Label Studio...")
    with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add classes.txt
        classes_path = Path("data/real_yolo/classes.txt")
        if classes_path.exists():
            zipf.write(classes_path, classes_path.name)
            
        # Add images and labels
        for img_path in IMAGES_DIR.glob("*.jpg"):
            zipf.write(img_path, img_path.name)
            
        for txt_path in LABELS_DIR.glob("*.txt"):
            zipf.write(txt_path, txt_path.name)
            
    logger.info("Packaging complete! Ready for upload to Label Studio.")

if __name__ == "__main__":
    pseudo_label_images()
    create_label_studio_zip()
