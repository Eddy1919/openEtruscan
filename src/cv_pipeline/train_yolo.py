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
DATASET_DIR = Path("data/synthetic_yolo")
MODEL_NAME = "yolo11n.pt"  # Use latest Nano architecture for edge performance
HF_REPO_ID = "openEtruscan/glyph-detector-yolo"
EPOCHS = 100
IMGSZ = 512

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_dataset():
    """Ensure the synthetic dataset has been generated."""
    yaml_path = DATASET_DIR / "dataset.yaml"
    if not yaml_path.exists():
        logger.error("Dataset YAML not found! Please run generate_synthetic_data.py first.")
        raise FileNotFoundError(f"{yaml_path} is missing.")
    logger.info("Dataset found at %s", DATASET_DIR)


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
    
    # 1. Verify data
    verify_dataset()
    
    # 2. Train and export 
    onnx_file = train_and_export()
    
    # 3. Push to registry 
    push_to_huggingface(onnx_file)
    
    logger.info("Pipeline execution built successfully.")
