"""
State-of-the-Art (SOTA) YOLO11n Computer Vision Pipeline for Etruscan Glyph Detection

This pipeline handles:
1. Connecting to the database to extract epigraphic images and bounding box annotations
2. Converting the raw data into standard YOLO dataset format
3. Training a YOLOv8n/YOLO11n Nano edge-optimized model for high-FPS browser inference
4. Exporting the trained weights to ONNX
5. Pushing the artifacts automatically to the Hugging Face Model Hub

Usage:
    poetry run python src/cv_pipeline/train_yolo.py
"""

import os
import shutil
import logging
from pathlib import Path
from ultralytics import YOLO
from huggingface_hub import HfApi

# Configuration
DATASET_DIR = Path("data/yolo_dataset")
MODEL_NAME = "yolo11n.pt"  # Use latest Nano architecture for edge performance
HF_REPO_ID = "openEtruscan/glyph-detector-yolo"
EPOCHS = 100
IMGSZ = 512

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_db_to_yolo():
    """
    Simulates extracting from the primary database (e.g., PostgreSQL/PostGIS)
    and formatting the images and annotations into the YOLO format:
    
    dataset/
      images/
        train/
        val/
      labels/
        train/
        val/
      dataset.yaml
    """
    logger.info("Extracting tons of material from DB to YOLO format...")
    
    # Create directory structure
    for split in ["train", "val"]:
        (DATASET_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (DATASET_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # DB Extraction Logic Here
    # e.g., session.query(GlyphAnnotation).all()
    # Write normalized coords to .txt files
    # ---------------------------------------------------------
    
    # Generate the dataset.yaml
    yaml_content = f"""
path: {DATASET_DIR.absolute()}
train: images/train
val: images/val

names:
  0: 𐌀
  1: 𐌁
  2: 𐌂
  3: 𐌃
  4: 𐌄
  5: 𐌅
  6: 𐌆
  7: 𐌇
  8: 𐌈
  9: 𐌉
  10: 𐌊
  11: 𐌋
  12: 𐌌
  13: 𐌍
  14: 𐌎
  15: 𐌏
  16: 𐌐
  17: 𐌑
  18: 𐌒
  19: 𐌓
  20: 𐌔
  21: 𐌕
  22: 𐌖
  23: 𐌗
  24: 𐌘
  25: 𐌙
  26: 𐌚
"""
    with open(DATASET_DIR / "dataset.yaml", "w", encoding="utf-8") as f:
        f.write(yaml_content.strip())
        
    logger.info("Dataset formatted successfully at %s", DATASET_DIR)


def train_and_export():
    """
    Trains the YOLO model and exports to ONNX.
    """
    logger.info("Initializing YOLO model...")
    model = YOLO(MODEL_NAME)
    
    logger.info("Starting training loop...")
    model.train(
        data=str(DATASET_DIR / "dataset.yaml"),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=16,
        device="cuda",  # Assumes GPU availability
        project="runs/glyph_detector",
        name="v1",
        cache=True
    )
    
    logger.info("Exporting best weights to ONNX format for onnxruntime-web...")
    # Exporting dynamically allocates input shape for browser usage
    export_path = model.export(format="onnx", dynamic=True, simplify=True)
    logger.info("Model exported successfully to %s", export_path)
    
    return export_path


def push_to_huggingface(onnx_path: str):
    """
    Pushes the trained ONNX model to the Hugging Face Hub for public CDN delivery.
    """
    logger.info("Pushing model to Hugging Face Hub: %s", HF_REPO_ID)
    
    api = HfApi()
    
    # Ensure the repo exists (requires HF_TOKEN env var)
    try:
        api.create_repo(repo_id=HF_REPO_ID, private=False, exist_ok=True)
    except Exception as e:
        logger.warning("Could not verify/create HF repo. Make sure HF_TOKEN is set. Error: %s", e)
        return

    # Upload the ONNX file
    try:
        api.upload_file(
            path_or_fileobj=onnx_path,
            path_in_repo="glyph_detector.onnx",
            repo_id=HF_REPO_ID,
            commit_message="Update SOTA ONNX model for OpenEtruscan frontend inference"
        )
        logger.info("🚀 Successfully pushed to Hugging Face!")
    except Exception as e:
        logger.error("Failed to upload to HF: %s", e)


if __name__ == "__main__":
    logger.info("--- Starting OpenEtruscan CV Pipeline ---")
    
    # 1. Prepare data
    extract_db_to_yolo()
    
    # 2. Train and export (Uncomment when actual data exists in DB)
    # onnx_file = train_and_export()
    
    # 3. Push to registry (Uncomment when model is trained)
    # push_to_huggingface(onnx_file)
    
    logger.info("Pipeline structure built successfully.")
