#!/usr/bin/env python3
"""
Hugging Face Synchronization Pipeline.

Downloads or Uploads Neural Models cleanly.
"""

import os
import argparse
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi, snapshot_download


def sync_upload():
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    repo_id = "Eddy1919/openetruscan-classifier"
    token = os.getenv("HF_TOKEN")

    if not token:
        print("FATAL: No HF_TOKEN found in .env")
        exit(1)

    model_dir = Path(__file__).resolve().parent.parent.parent / "data" / "models"
    if not model_dir.exists():
        print("FATAL: data/models directory does not exist.")
        exit(1)

    api = HfApi()
    print(f"Authenticating to {repo_id}...")
    try:
        api.create_repo(repo_id=repo_id, repo_type="model", token=token, exist_ok=True, private=False)
    except Exception as e:
        print(f"Repository namespace verification: {e}")

    print("Uploading Neural Matrix to Hugging Face...")
    api.upload_folder(folder_path=str(model_dir), repo_id=repo_id, repo_type="model", token=token)
    print(f"Deployment to {repo_id} Complete!")

def sync_download():
    repo_id = "Eddy1919/openetruscan-classifier"
    model_dir = Path(__file__).resolve().parent.parent.parent / "data" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading Neural Matrix from Hugging Face ({repo_id})...")
    try:
        snapshot_download(repo_id=repo_id, local_dir=str(model_dir), repo_type="model")
        print(f"Download to {model_dir} Complete!")
        
        frontend_model_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "models"
        frontend_model_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(model_dir, frontend_model_dir, dirs_exist_ok=True)
        print("Synced to frontend/public/models!")
    except Exception as e:
        print(f"Failed to download models: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Download from HF")
    parser.add_argument("--upload", action="store_true", help="Upload to HF")
    args = parser.parse_args()

    if args.download:
        sync_download()
    elif args.upload:
        sync_upload()
    else:
        print("Please specify --download or --upload")
