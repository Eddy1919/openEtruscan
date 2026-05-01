"""
Label Studio JSON Converter (Base64 Edition)

Converts YOLO labels and images into a single, bulletproof Label Studio JSON file.
By Base64 encoding the images, we bypass all ZIP, pathing, and Local Storage issues.

Usage:
    poetry run python src/cv_pipeline/convert_to_ls_json.py
"""

import json
import base64
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IMAGES_DIR = Path("data/real_yolo/images/train")
LABELS_DIR = Path("data/real_yolo/labels/train")
OUTPUT_JSON = Path("label_studio_import.json")

# The 23 Etruscan Characters (from etruscan.yaml)
ETRUSCAN_CHARS = ["𐌀", "𐌂", "𐌄", "𐌅", "𐌆", "𐌇", "𐌈", "𐌉", "𐌊", "𐌋", "𐌌", "𐌍", "𐌎", "𐌐", "𐌑", "𐌒", "𐌓", "𐌔", "𐌕", "𐌖", "𐌗", "𐌘", "𐌚"]

def get_base64_image(image_path: Path):
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    ext = image_path.suffix.lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    return f"data:image/{ext};base64,{encoded}"

def convert():
    tasks = []
    
    for img_path in IMAGES_DIR.glob("*.jpg"):
        txt_path = LABELS_DIR / f"{img_path.stem}.txt"
        
        # We assume all downloaded images are roughly standard sizes, LS handles scaling
        results = []
        
        if txt_path.exists():
            with open(txt_path) as f:
                lines = f.readlines()
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) == 5:
                        cls_id = int(parts[0])
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        w = float(parts[3])
                        h = float(parts[4])
                        
                        # YOLO to Label Studio percentage conversion
                        ls_w = w * 100
                        ls_h = h * 100
                        ls_x = (x_center - w/2) * 100
                        ls_y = (y_center - h/2) * 100
                        
                        label_val = f"{cls_id}_{ETRUSCAN_CHARS[cls_id]}"
                        
                        results.append({
                            "original_width": 1000, # LS scales dynamically
                            "original_height": 1000,
                            "image_rotation": 0,
                            "value": {
                                "x": ls_x,
                                "y": ls_y,
                                "width": ls_w,
                                "height": ls_h,
                                "rotation": 0,
                                "rectanglelabels": [label_val]
                            },
                            "from_name": "label",
                            "to_name": "image",
                            "type": "rectanglelabels"
                        })
                        
        tasks.append({
            "data": {
                "image": get_base64_image(img_path)
            },
            "annotations": [
                {
                    "result": results
                }
            ]
        })
        
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False)
        
    logger.info(f"Successfully converted {len(tasks)} images into {OUTPUT_JSON}!")

if __name__ == "__main__":
    convert()
