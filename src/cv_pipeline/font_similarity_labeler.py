"""
Font-Similarity Auto-Labeler
Uses OpenCV Hu Moments shape matching to compare carved shapes on real stone
to "ideal" glyph templates rendered directly from the Noto Sans Old Italic font.
"""

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import logging
import json
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IMAGES_DIR = Path("data/real_yolo/images/train")
LABELS_DIR = Path("data/real_yolo/labels/train")
OUTPUT_JSON = Path("label_studio_similarity_import.json")
FONT_PATH = "src/cv_pipeline/assets/NotoSansOldItalic-Regular.ttf"

# The 23 Etruscan Characters
ETRUSCAN_CHARS = [
    "𐌀", "𐌂", "𐌄", "𐌅", "𐌆", "𐌇", "𐌈", "𐌉", "𐌊", "𐌋", "𐌌", "𐌍", 
    "𐌎", "𐌐", "𐌑", "𐌒", "𐌓", "𐌔", "𐌕", "𐌖", "𐌗", "𐌘", "𐌚"
]
CHAR_TO_CLASS = {char: idx for idx, char in enumerate(ETRUSCAN_CHARS)}

def create_font_contours():
    """Generates contour templates for each Etruscan letter using the font."""
    if not Path(FONT_PATH).exists():
        logger.error("Font not found!")
        return {}
        
    font = ImageFont.truetype(FONT_PATH, 48)
    templates = {}
    
    for idx, char in enumerate(ETRUSCAN_CHARS):
        # Create a white canvas
        img = Image.new('L', (80, 80), color=255)
        draw = ImageDraw.Draw(img)
        
        # Center the text
        bbox = draw.textbbox((0, 0), char, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (80 - w) / 2 - bbox[0]
        y = (80 - h) / 2 - bbox[1]
        
        draw.text((x, y), char, font=font, fill=0) # Black text
        
        # Convert to cv2 format and find contour
        cv_img = np.array(img)
        _, binary = cv2.threshold(cv_img, 128, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Get largest contour for this letter
            largest_contour = max(contours, key=cv2.contourArea)
            templates[idx] = largest_contour
            
    return templates

def get_base64_image(image_path: Path):
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    ext = image_path.suffix.lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    return f"data:image/{ext};base64,{encoded}"

def process_images():
    templates = create_font_contours()
    if not templates:
        return
        
    tasks = []
    
    for img_path in IMAGES_DIR.glob("*.jpg"):
        logger.info(f"Shape-matching on {img_path.name}...")
        img = cv2.imread(str(img_path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Adaptive thresholding to pull the physical carvings out of the stone
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
        )
        
        kernel = np.ones((3,3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        img_h, img_w = img.shape[:2]
        results = []
        txt_labels = []
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            
            # Filter for shapes that are roughly letter-sized
            if 60 < area < 4000 and (w/h < 3.0 and h/w < 3.0):
                
                # Compare this shape to all 23 ideal font templates
                best_match_idx = -1
                best_match_score = float('inf')
                
                for class_idx, template_cnt in templates.items():
                    # cv2.matchShapes uses Hu Moments (scale, translation, and rotation invariant)
                    score = cv2.matchShapes(cnt, template_cnt, cv2.CONTOURS_MATCH_I2, 0.0)
                    if score < best_match_score:
                        best_match_score = score
                        best_match_idx = class_idx
                        
                # Only keep matches that are reasonably close to an Etruscan letter
                if best_match_score < 0.25: # Lower is better
                    
                    # YOLO format
                    x_center = (x + w/2) / img_w
                    y_center = (y + h/2) / img_h
                    norm_w = w / img_w
                    norm_h = h / img_h
                    txt_labels.append(f"{best_match_idx} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")
                    
                    # Label Studio format
                    ls_w = norm_w * 100
                    ls_h = norm_h * 100
                    ls_x = (x_center - norm_w/2) * 100
                    ls_y = (y_center - norm_h/2) * 100
                    
                    # ETRUSCAN_CHARS[best_match_idx] is the char glyph; we don't need the
                    # symbol here, only the index → label lookup below.
                    # We map to the '0_a_𐌀' format used in the updated XML
                    # Note: We don't have the latin equivalent handy here, but Label Studio 
                    # matches values exactly. The user's XML has "0_a_𐌀", so we must match that.
                    # Let's map it exactly:
                    xml_values = [
                        "0_a_𐌀", "1_c_𐌂", "2_e_𐌄", "3_v_𐌅", "4_z_𐌆", "5_h_𐌇", "6_θ_𐌈", 
                        "7_i_𐌉", "8_k_𐌊", "9_l_𐌋", "10_m_𐌌", "11_n_𐌍", "12_ξ_𐌎", "13_p_𐌐", 
                        "14_ś_𐌑", "15_q_𐌒", "16_r_𐌓", "17_s_𐌔", "18_t_𐌕", "19_u_𐌖", "20_χ_𐌗", 
                        "21_φ_𐌘", "22_f_𐌚"
                    ]
                    label_val = xml_values[best_match_idx]
                    
                    results.append({
                        "original_width": 1000,
                        "original_height": 1000,
                        "image_rotation": 0,
                        "value": {
                            "x": ls_x, "y": ls_y, "width": ls_w, "height": ls_h,
                            "rotation": 0, "rectanglelabels": [label_val]
                        },
                        "from_name": "label", "to_name": "image", "type": "rectanglelabels"
                    })
        
        # Save YOLO txt
        txt_path = LABELS_DIR / f"{img_path.stem}.txt"
        with open(txt_path, "w") as f:
            f.write("\n".join(txt_labels))
            
        data_dict = {"image": get_base64_image(img_path)}
        
        stem_lower = img_path.stem.lower()
        if "cippus_perusinus" in stem_lower:
            data_dict["transliteration"] = "eurat tanna larezul ame vaχr lautn velθinaš eštla afunas sleleθ caru tezan fušleri tesnšteiš rašneš ipa ama hen naper χii velθinaθuraš araš peraš cincem amercnl velθina zia šatenete sne eca velθinaθuraš θaura helu"
            data_dict["translation"] = "THIS IS THE SETTLEMENT BETWEEN THE VELTHINA AND AFUNA FAMILIES CONCERNING THE PROPERTY BOUNDARIES AND THE TOMB OF THE VELTHINA AS ARBITRATED BY LART REZUL ACCORDING TO ETRUSCAN LAW"
        elif "tabula_cortonensis" in stem_lower:
            data_dict["transliteration"] = "et peṭruiš scēvies eliuntś"
            data_dict["translation"] = "This is the estate of Petru Scevie"

        tasks.append({
            "data": data_dict,
            "annotations": [{"result": results}]
        })
        
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False)
        
    logger.info(f"Shape-matching complete! Generated {OUTPUT_JSON} for Label Studio.")

if __name__ == "__main__":
    process_images()
