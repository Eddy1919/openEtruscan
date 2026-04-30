"""
Forced Alignment Auto-Labeler for Etruscan Stelae

This script solves the "I have photos and text, but no bounding boxes" problem.
It extracts carved bounding boxes using classic CV (adaptive thresholding) 
and maps a known Etruscan text string onto those boxes (Right-to-Left).
It generates perfectly formatted YOLO labels for your real photos.

Usage:
    poetry run python src/cv_pipeline/auto_labeler.py
"""

import cv2
import numpy as np
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The 23 Etruscan Characters (from etruscan.yaml)
ETRUSCAN_CHARS = ["𐌀", "𐌂", "𐌄", "𐌅", "𐌆", "𐌇", "𐌈", "𐌉", "𐌊", "𐌋", "𐌌", "𐌍", "𐌎", "𐌐", "𐌑", "𐌒", "𐌓", "𐌔", "𐌕", "𐌖", "𐌗", "𐌘", "𐌚"]
CHAR_TO_CLASS = {char: idx for idx, char in enumerate(ETRUSCAN_CHARS)}

def find_glyph_bounding_boxes(image_path: str):
    """
    Extracts bounding boxes of carvings from a real stone photograph using 
    Adaptive Thresholding and contour detection.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image at {image_path}")
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Adaptive thresholding to isolate carvings (carvings are darker)
    # block_size and C might need tuning based on the specific museum lighting
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 12
    )
    
    # Clean up noise
    kernel = np.ones((3,3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bboxes = []
    img_h, img_w = img.shape[:2]
    
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        
        # Filter out tiny specs of dirt and huge cracks
        if 25 < area < 2500 and (w/h < 2.5 and h/w < 2.5):
            bboxes.append({
                "x_min": x, "y_min": y, "w": w, "h": h,
                "x_center_norm": (x + w/2) / img_w,
                "y_center_norm": (y + h/2) / img_h,
                "w_norm": w / img_w,
                "h_norm": h / img_h
            })
            
    return bboxes

def auto_label_image(image_path: str, known_text: str, output_dir: str):
    """
    Maps a known text string to detected bounding boxes via Forced Alignment.
    """
    logger.info(f"Auto-labeling {image_path}...")
    bboxes = find_glyph_bounding_boxes(image_path)
    
    # Clean the known text of spaces
    clean_text = known_text.replace(" ", "").replace("\n", "")
    
    if not bboxes:
        logger.warning(f"No bounding boxes detected in {image_path}")
        return
        
    # Etruscan is read Right-to-Left, Top-to-Bottom.
    # We must sort the detected boxes in reading order.
    # 1. Group into lines based on Y coordinate
    bboxes.sort(key=lambda b: b["y_min"])
    
    lines = []
    current_line = []
    last_y = bboxes[0]["y_min"]
    
    for b in bboxes:
        if b["y_min"] > last_y + 30: # 30px threshold for new line
            lines.append(current_line)
            current_line = []
        current_line.append(b)
        last_y = b["y_min"]
    if current_line:
        lines.append(current_line)
        
    # 2. Sort each line Right-to-Left (decreasing X coordinate)
    for line in lines:
        line.sort(key=lambda b: b["x_min"], reverse=True)
        
    # Flatten back into reading order
    sorted_bboxes = [b for line in lines for b in line]
    
    # Map text to boxes
    yolo_labels = []
    img_name = Path(image_path).stem
    
    if len(sorted_bboxes) < len(clean_text):
        logger.warning(f"Found fewer boxes ({len(sorted_bboxes)}) than text chars ({len(clean_text)}). Some letters may be eroded.")
    
    # Map 1-to-1 up to the limit
    for i, bbox in enumerate(sorted_bboxes):
        if i >= len(clean_text):
            break
            
        char = clean_text[i]
        if char in CHAR_TO_CLASS:
            class_id = CHAR_TO_CLASS[char]
            yolo_labels.append(f"{class_id} {bbox['x_center_norm']:.6f} {bbox['y_center_norm']:.6f} {bbox['w_norm']:.6f} {bbox['h_norm']:.6f}")
            
    # Write YOLO .txt file
    out_path = Path(output_dir) / f"{img_name}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w") as f:
        f.write("\n".join(yolo_labels))
        
    logger.info(f"Successfully pseudo-labeled {len(yolo_labels)} characters. Saved to {out_path}")


if __name__ == "__main__":
    # Example usage for when you acquire real photos
    
    sample_text = "𐌌𐌉𐌋𐌀𐌓𐌆𐌀𐌉𐌀" # "mi larzaia" (right-to-left)
    
    # Create a dummy image for testing the pipeline if no real image exists
    test_img_path = Path("src/cv_pipeline/assets/dummy_stele.jpg")
    if not test_img_path.exists():
        logger.info("Creating dummy stele image for test execution...")
        test_img_path.parent.mkdir(parents=True, exist_ok=True)
        dummy = np.ones((512, 512, 3), dtype=np.uint8) * 200
        # Draw some dark boxes to simulate carvings
        cv2.rectangle(dummy, (400, 100), (430, 150), (50, 50, 50), -1) # Box 1 (Right)
        cv2.rectangle(dummy, (350, 100), (380, 150), (50, 50, 50), -1) # Box 2 (Left)
        cv2.imwrite(str(test_img_path), dummy)
        
    # Run the auto labeler
    auto_label_image(str(test_img_path), sample_text, "data/real_yolo/labels/train")
