"""
Etruscan Inscription Scraper

Queries the Wikimedia Commons API for high-resolution images of real Etruscan 
inscriptions, stelae, and artifacts. Downloads them to the real_yolo directory 
so they can be fed into the auto_labeler.

Usage:
    poetry run python src/cv_pipeline/download_real_inscriptions.py
"""

import os
import requests
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Search queries for Wikimedia Commons
SEARCH_QUERIES = [
    "Etruscan inscription",
    "Cippus Perusinus",
    "Tabula Cortonensis",
    "Liber Linteus text",
    "Pyrgi Tablets"
]

OUTPUT_DIR = Path("data/real_yolo/images/train")

def fetch_wikimedia_images(query: str, limit: int = 5):
    """
    Queries the Wikimedia API for images matching the query string.
    Returns a list of image URLs.
    """
    logger.info(f"Searching Wikimedia for: '{query}'")
    
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6, # File namespace
        "gsrsearch": query,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url"
    }
    
    try:
        headers = {"User-Agent": "OpenEtruscanBot/1.0 (https://openetruscan.org/)"}
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        pages = data.get("query", {}).get("pages", {})
        image_urls = []
        
        for page_id, page_data in pages.items():
            image_info = page_data.get("imageinfo", [])
            if image_info:
                img_url = image_info[0].get("url")
                if img_url and img_url.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_urls.append(img_url)
                    
        return image_urls
    except Exception as e:
        logger.error(f"Failed to query Wikimedia for '{query}': {e}")
        return []

def download_image(url: str, save_path: Path):
    """Downloads an image from a URL."""
    try:
        headers = {"User-Agent": "OpenEtruscanBot/1.0 (https://openetruscan.org/)"}
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded: {save_path.name}")
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    total_downloaded = 0
    for query in SEARCH_QUERIES:
        urls = fetch_wikimedia_images(query, limit=5)
        for i, url in enumerate(urls):
            # Clean filename
            filename = f"real_{query.replace(' ', '_').lower()}_{i}.jpg"
            save_path = OUTPUT_DIR / filename
            
            if not save_path.exists():
                download_image(url, save_path)
                total_downloaded += 1
            else:
                logger.info(f"Skipping {filename}, already exists.")
                
    logger.info(f"Scraping complete! Downloaded {total_downloaded} new real Etruscan inscriptions.")
    logger.info(f"Images saved to: {OUTPUT_DIR}")
