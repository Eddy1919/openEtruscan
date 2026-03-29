#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

# Add src to path if needed
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def export_openapi():
    # Force ENABLE_DOCS to True for export
    os.environ["ENABLE_DOCS"] = "1"
    
    from openetruscan.server import app
    
    # Generate OpenAPI schema
    openapi_schema = app.openapi()
    
    # Save to JSON
    output_dir = Path(__file__).parent.parent / "docs"
    output_dir.mkdir(exist_ok=True)
    
    output_path = output_dir / "openapi.json"
    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
        
    print(f"✅ OpenAPI schema exported to {output_path}")

if __name__ == "__main__":
    export_openapi()
