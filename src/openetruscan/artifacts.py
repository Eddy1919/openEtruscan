"""
Artifact storage — images and media attached to inscriptions.

Stores metadata in the corpus database, files on the local filesystem.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_IMAGES_DIR = Path("data/images")


@dataclass
class InscriptionImage:
    """An image or artifact attached to an inscription."""

    id: str
    inscription_id: str
    filename: str
    mime_type: str = "image/jpeg"
    description: str = ""
    file_hash: str = ""


# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

IMAGES_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    inscription_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
    description TEXT DEFAULT '',
    file_hash TEXT DEFAULT '',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inscription_id) REFERENCES inscriptions(id)
);

CREATE INDEX IF NOT EXISTS idx_images_inscription
    ON images(inscription_id);
"""

IMAGES_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    inscription_id TEXT NOT NULL REFERENCES inscriptions(id),
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
    description TEXT DEFAULT '',
    file_hash TEXT DEFAULT '',
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_images_inscription
    ON images(inscription_id);
"""


def _detect_mime(path: Path) -> str:
    """Detect MIME type from file extension."""
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def store_image(
    source_path: str | Path,
    inscription_id: str,
    description: str = "",
    images_dir: str | Path | None = None,
) -> InscriptionImage:
    """
    Copy an image file to the images directory and return metadata.

    Args:
        source_path: Path to the source image file
        inscription_id: ID of the inscription this image belongs to
        description: Optional description of the image
        images_dir: Directory to store images (default: data/images/)

    Returns:
        InscriptionImage with metadata for database storage
    """
    import os

    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"Image not found: {src}")

    dest_dir = Path(
        images_dir or os.environ.get("IMAGES_DIR", DEFAULT_IMAGES_DIR)
    )
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectory per inscription
    insc_dir = dest_dir / inscription_id
    insc_dir.mkdir(exist_ok=True)

    # Copy file
    dest = insc_dir / src.name
    shutil.copy2(src, dest)

    # Generate ID from hash
    fhash = _file_hash(dest)
    image_id = f"img_{inscription_id}_{fhash[:8]}"

    return InscriptionImage(
        id=image_id,
        inscription_id=inscription_id,
        filename=str(dest.relative_to(dest_dir)),
        mime_type=_detect_mime(src),
        description=description,
        file_hash=fhash,
    )


def list_images(
    inscription_id: str,
    images_dir: str | Path | None = None,
) -> list[Path]:
    """List all image files for an inscription."""
    import os

    dest_dir = Path(
        images_dir or os.environ.get("IMAGES_DIR", DEFAULT_IMAGES_DIR)
    )
    insc_dir = dest_dir / inscription_id
    if not insc_dir.exists():
        return []
    return sorted(insc_dir.iterdir())
