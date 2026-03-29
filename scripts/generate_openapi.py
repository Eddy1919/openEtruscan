#!/usr/bin/env python3
"""
Generate OpenAPI schema documentation for the OpenEtruscan API.

Usage:
    python scripts/generate_openapi.py
    python scripts/generate_openapi.py --output docs/openapi.json
    python scripts/generate_openapi.py --format yaml
"""

import argparse
import json
import sys
from pathlib import Path


def generate_openapi(format: str = "json") -> str:
    """Generate OpenAPI schema from the FastAPI application."""
    # Import here to avoid requiring server deps for doc generation
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    from fastapi.openapi.utils import get_openapi

    from openetruscan import __version__
    from openetruscan.server import app

    openapi_schema = get_openapi(
        title=app.title,
        version=__version__,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )

    # Add additional metadata
    openapi_schema["info"]["contact"] = {
        "name": "OpenEtruscan Contributors",
        "url": "https://github.com/Eddy1919/openEtruscan",
    }
    openapi_schema["info"]["license"] = {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    }

    # Add servers
    openapi_schema["servers"] = [
        {"url": "https://www.openetruscan.com", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ]

    if format == "yaml":
        try:
            import yaml
            return yaml.dump(openapi_schema, default_flow_style=False, sort_keys=False)
        except ImportError:
            print("PyYAML not installed, outputting JSON instead", file=sys.stderr)
            format = "json"

    return json.dumps(openapi_schema, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Generate OpenAPI schema for OpenEtruscan API"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "yaml"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    schema = generate_openapi(format=args.format)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(schema, encoding="utf-8")
        print(f"OpenAPI schema written to {args.output}")
    else:
        print(schema)


if __name__ == "__main__":
    main()
