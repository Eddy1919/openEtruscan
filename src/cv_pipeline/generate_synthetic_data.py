"""
Synthetic Data Generator for Etruscan Epigraphy
Creates SOTA YOLO datasets by rendering Old Italic glyphs onto simulated stone textures.

Usage:
    poetry run python src/cv_pipeline/generate_synthetic_data.py
"""

import os
import random
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
OUTPUT_DIR = Path("data/synthetic_yolo")
IMG_SIZE = 512
NUM_IMAGES = 1000  # Number of synthetic images to generate
NUM_VAL_IMAGES = 200

# The 27 Etruscan Characters
ETRUSCAN_CHARS = ["𐌀", "𐌁", "𐌂", "𐌃", "𐌄", "𐌅", "𐌆", "𐌇", "𐌈", "𐌉", "𐌊", "𐌋", "𐌌", "𐌍", "𐌎", "𐌏", "𐌐", "𐌑", "𐌒", "𐌓", "𐌔", "𐌕", "𐌖", "𐌗", "𐌘", "𐌙", "𐌚"]
CHAR_TO_CLASS = {char: idx for idx, char in enumerate(ETRUSCAN_CHARS)}

def setup_directories():
    for split in ["train", "val"]:
        (OUTPUT_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

def generate_stone_texture(image_id, width, height):
    """
    Downloads or generates a realistic stone background.
    Uses real photographic images to provide true domain complexity (cracks, shadows).
    """
    texture_dir = Path("src/cv_pipeline/assets/textures")
    texture_dir.mkdir(parents=True, exist_ok=True)
    
    # We use stable seeded images from Picsum to simulate real photographic depth
    texture_path = texture_dir / f"bg_{image_id % 50}.jpg"
    
    if not texture_path.exists():
        import urllib.request
        try:
            # Download a random photograph
            url = f"https://picsum.photos/seed/{image_id % 50}/{width}/{height}"
            urllib.request.urlretrieve(url, texture_path)
        except Exception as e:
            logger.warning(f"Failed to fetch real texture, falling back to noise: {e}")
            pass
            
    if texture_path.exists():
        try:
            img = Image.open(texture_path).convert("RGB")
            img = img.resize((width, height))
            
            # Convert generic photo to "stone/terracotta" aesthetic
            # Convert to grayscale to remove original colors
            gray = img.convert("L")
            
            # Colorize with terracotta/stone colors
            stone_color = (random.randint(140, 180), random.randint(120, 160), random.randint(100, 140))
            dark_color = (int(stone_color[0]*0.3), int(stone_color[1]*0.3), int(stone_color[2]*0.3))
            
            from PIL import ImageOps
            img = ImageOps.colorize(gray, dark_color, stone_color)
            return img
        except Exception:
            pass

    # Fallback: Generate noise using numpy
    base_r, base_g, base_b = random.randint(160, 210), random.randint(140, 190), random.randint(120, 170)
    noise = np.random.normal(0, 15, (height, width, 3))
    img_arr = np.zeros((height, width, 3), dtype=np.float32)
    img_arr[:, :, 0] = base_r
    img_arr[:, :, 1] = base_g
    img_arr[:, :, 2] = base_b
    img_arr = np.clip(img_arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(img_arr).filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.5)))

def get_font():
    """Attempt to load an Old Italic font, fallback to default if not found."""
    # You MUST place an Old Italic font like 'NotoSansOldItalic-Regular.ttf' in src/cv_pipeline/assets/
    font_path = Path("src/cv_pipeline/assets/NotoSansOldItalic-Regular.ttf")
    if not font_path.exists():
        logger.warning(f"Font not found at {font_path}. Falling back to default font.")
        return ImageFont.load_default(), False
    
    # Randomize font size to simulate different carving sizes
    size = random.randint(30, 80)
    return ImageFont.truetype(str(font_path), size), True

def generate_image(image_id, split="train"):
    img = generate_stone_texture(image_id, IMG_SIZE, IMG_SIZE)
    draw = ImageDraw.Draw(img)
    font, is_custom = get_font()
    
    # Decide how many glyphs to place on this "stele shard"
    num_glyphs = random.randint(5, 20)
    
    labels = []
    
    # Simulate writing lines (Right-to-Left or Left-to-Right)
    current_y = random.randint(20, 100)
    current_x = random.randint(20, IMG_SIZE - 100)
    line_height = random.randint(50, 100)
    
    for _ in range(num_glyphs):
        char = random.choice(ETRUSCAN_CHARS)
        class_id = CHAR_TO_CLASS[char]
        
        # Carving color (darker than stone, sometimes eroded/faded)
        carve_shade = random.randint(40, 100)
        carve_alpha = random.randint(180, 255)
        color = (carve_shade, carve_shade, carve_shade, carve_alpha)
        
        # Get bounding box of the text
        if is_custom:
            bbox = draw.textbbox((current_x, current_y), char, font=font)
        else:
            bbox = draw.textbbox((current_x, current_y), char) # Default font fallback
            
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        
        # If it flows off screen, carriage return
        if current_x + w > IMG_SIZE - 20:
            current_x = random.randint(20, 100)
            current_y += line_height
            if current_y > IMG_SIZE - 50:
                break # Reached bottom of shard
        
        # Draw text (simulate carved indentation)
        draw.text((current_x, current_y), char, fill=color, font=font)
        
        # Recalculate exact bounding box for YOLO
        # YOLO format: class x_center y_center width height (normalized 0-1)
        x_center = (current_x + w/2) / IMG_SIZE
        y_center = (current_y + h/2) / IMG_SIZE
        norm_w = w / IMG_SIZE
        norm_h = h / IMG_SIZE
        
        labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")
        
        # Advance cursor (add random spacing)
        current_x += w + random.randint(10, 40)
        
    # Apply post-processing (erosion, blur) to simulate millennia of wear
    img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.2, 0.8)))
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(random.uniform(0.8, 1.2))

    # Save outputs
    base_filename = f"synth_{image_id:06d}"
    img_path = OUTPUT_DIR / "images" / split / f"{base_filename}.jpg"
    lbl_path = OUTPUT_DIR / "labels" / split / f"{base_filename}.txt"
    
    img.save(img_path, quality=90)
    with open(lbl_path, "w") as f:
        f.write("\n".join(labels))

def generate_dataset_yaml():
    yaml_content = f"""
path: {OUTPUT_DIR.absolute()}
train: images/train
val: images/val

names:
"""
    for char, idx in CHAR_TO_CLASS.items():
        yaml_content += f"  {idx}: {char}\n"
        
    with open(OUTPUT_DIR / "dataset.yaml", "w", encoding="utf-8") as f:
        f.write(yaml_content.strip())

if __name__ == "__main__":
    logger.info("Setting up synthetic generation directories...")
    setup_directories()
    generate_dataset_yaml()
    
    logger.info(f"Generating {NUM_IMAGES} training images...")
    for i in range(NUM_IMAGES):
        generate_image(i, split="train")
        if i % 100 == 0:
            logger.info(f"Generated {i}/{NUM_IMAGES} training images")
            
    logger.info(f"Generating {NUM_VAL_IMAGES} validation images...")
    for i in range(NUM_VAL_IMAGES):
        generate_image(NUM_IMAGES + i, split="val")
        
    logger.info("Synthetic dataset generation complete! You can now run the YOLO training script.")
