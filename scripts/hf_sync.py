#!/usr/bin/env python3
"""
Hugging Face Synchronization Pipeline.

Uploads local Neural Models to the Eddy1919/openetruscan-classifier repository cleanly.
Automatically generates the requisite `config.json` tracking asset.
"""

import os
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi


def sync_huggingface():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    repo_id = "Eddy1919/openetruscan-classifier"
    token = os.getenv("HF_TOKEN")

    if not token:
        print("FATAL: No HF_TOKEN found in .env")
        exit(1)

    model_dir = Path(__file__).parent.parent / "data" / "models"
    if not model_dir.exists():
        print("FATAL: data/models directory does not exist.")
        exit(1)

    # Allow network wait buffer if training script is finishing
    time.sleep(2)

    # 1. Generate Hugging Face tracking proxies securely
    config_target = model_dir / "config.json"
    meta_source = model_dir / "cnn_meta.json"
    metrics_source = model_dir / "metrics.json"

    # Default to CNN architecture json properties as the base config
    if meta_source.exists():
        shutil.copy(meta_source, config_target)
        print("Injected config.json tracking mechanism from cnn_meta successfully.")
    elif metrics_source.exists():
        shutil.copy(metrics_source, config_target)
        print("Injected config.json tracking mechanism from metrics successfully.")

    for file in model_dir.glob("*.json"):
        if "meta" in file.name:
            # We strictly inject model_index json references too if Diffusers/Generative triggers apply
            target = model_dir / file.name.replace("_meta.json", "_config.json")
            if not target.exists():
                shutil.copy(file, target)

    api = HfApi()

    print(f"Authenticating to {repo_id}...")
    try:
        api.create_repo(repo_id=repo_id, repo_type="model", token=token, exist_ok=True, private=False)
    except Exception as e:
        print(f"Repository namespace verification: {e}")

    print("Uploading Neural Matrix to Hugging Face...")
    api.upload_folder(
        folder_path=str(model_dir),
        repo_id=repo_id,
        repo_type="model",
        token=token,
    )

    print(f"Deployment to {repo_id} Complete!")

if __name__ == "__main__":
    sync_huggingface()
