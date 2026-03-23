"""
CLI — command-line interface for OpenEtruscan.

Usage:
    openetruscan normalize "LARTHAL LECNES"
    openetruscan batch --input corpus.txt --format csv --output clean.csv
    openetruscan validate my_transcription.txt
    openetruscan convert --to old_italic "Larθal"
    openetruscan adapters
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from openetruscan.adapter import list_available_adapters
from openetruscan.converter import convert
from openetruscan.normalizer import normalize
from openetruscan.validator import validate_file


@click.group()
@click.version_option(package_name="openetruscan")
def main() -> None:
    """OpenEtruscan — Open-source tools for ancient epigraphy."""


@main.command()
@click.argument("text")
@click.option("--language", "-l", default="etruscan", help="Language adapter to use.")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON.")
def normalize_cmd(text: str, language: str, json_output: bool) -> None:
    """Normalize a text from any transcription system."""
    result = normalize(text, language=language)

    if json_output:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        click.echo(f"  canonical:  {result.canonical}")
        click.echo(f"  phonetic:   {result.phonetic}")
        click.echo(f"  old_italic: {result.old_italic}")
        click.echo(f"  source:     {result.source_system}")
        click.echo(f"  tokens:     {result.tokens}")
        click.echo(f"  confidence: {result.confidence:.0%}")
        if result.warnings:
            click.echo(f"  warnings:   {result.warnings}")


# Register 'normalize' as the command name
main.add_command(normalize_cmd, name="normalize")


@main.command()
@click.argument("text")
@click.option(
    "--to",
    "target",
    default="old_italic",
    help="Target format: canonical, old_italic, phonetic.",
)
@click.option("--language", "-l", default="etruscan", help="Language adapter.")
def convert_cmd(text: str, target: str, language: str) -> None:
    """Convert text to a specific format."""
    result = convert(text, target=target, language=language)
    click.echo(result)


main.add_command(convert_cmd, name="convert")


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--language", "-l", default="etruscan", help="Language adapter.")
@click.option("--column", "-c", default=None, help="CSV column containing text.")
def validate(file_path: str, language: str, column: str | None) -> None:
    """Validate a transcription file for encoding errors."""
    report = validate_file(file_path, language=language, text_column=column)
    click.echo(report.summary())
    if not report.is_valid:
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", "fmt", default="csv", help="Output format: csv, json, jsonl.")
@click.option("--output", "-o", default=None, help="Output file (default: stdout).")
@click.option("--language", "-l", default="etruscan", help="Language adapter.")
def batch(input_file: str, fmt: str, output: str | None, language: str) -> None:
    """Batch-normalize a file of inscriptions."""
    path = Path(input_file)
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    results = [normalize(line, language=language) for line in lines]

    if fmt == "json":
        data = [r.to_dict() for r in results]
        text = json.dumps(data, ensure_ascii=False, indent=2)
    elif fmt == "jsonl":
        text = "\n".join(json.dumps(r.to_dict(), ensure_ascii=False) for r in results)
    elif fmt == "csv":
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["canonical", "phonetic", "old_italic", "source_system", "confidence"])
        for r in results:
            writer.writerow([r.canonical, r.phonetic, r.old_italic, r.source_system, r.confidence])
        text = buf.getvalue()
    else:
        click.echo(f"Unknown format: {fmt}. Use: csv, json, jsonl.", err=True)
        sys.exit(1)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"✅ Wrote {len(results)} normalized inscriptions to {output}")
    else:
        click.echo(text)


@main.command(name="adapters")
def list_adapters() -> None:
    """List available language adapters."""
    adapters = list_available_adapters()
    if not adapters:
        click.echo("No adapters found.")
        return
    click.echo("Available language adapters:")
    for adapter_id in adapters:
        click.echo(f"  • {adapter_id}")


# =========================================================================
# Corpus CLI commands
# =========================================================================


def _get_corpus(db: str | None = None):
    """Get a corpus connection using DATABASE_URL or --db flag."""
    from openetruscan.corpus import Corpus

    if db:
        return Corpus.connect(db) if "://" in db else Corpus.load(db)
    return Corpus.load()


@main.command()
@click.argument("query")
@click.option(
    "--findspot",
    "-f",
    default=None,
    help="Filter by findspot (partial match).",
)
@click.option(
    "--date-from",
    default=None,
    type=int,
    help="Start of date range (negative=BCE).",
)
@click.option(
    "--date-to",
    default=None,
    type=int,
    help="End of date range (negative=BCE).",
)
@click.option("--limit", "-n", default=20, help="Max results.")
@click.option(
    "--db",
    default=None,
    help="Database URL or path (default: DATABASE_URL env or local SQLite).",
)
@click.option("--json-output", "-j", is_flag=True, help="JSON output.")
def search(
    query: str,
    findspot: str | None,
    date_from: int | None,
    date_to: int | None,
    limit: int,
    db: str | None,
    json_output: bool,
) -> None:
    """Search the corpus for inscriptions."""
    corpus = _get_corpus(db)
    date_range = None
    if date_from is not None and date_to is not None:
        date_range = (date_from, date_to)

    results = corpus.search(
        text=query,
        findspot=findspot,
        date_range=date_range,
        limit=limit,
    )

    if json_output:
        import json as json_mod

        data = [i.to_dict() for i in results]
        click.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Found {results.total} inscriptions")
        click.echo("")
        for insc in results:
            loc = f" ({insc.findspot})" if insc.findspot else ""
            date = f" [{insc.date_display()}]" if insc.date_approx else ""
            cls = f" [{insc.classification}]" if insc.classification != "unknown" else ""
            click.echo(f"  {insc.id}: {insc.canonical}{loc}{date}{cls}")
    corpus.close()


@main.command(name="import")
@click.argument("csv_file", type=click.Path(exists=True))
@click.option(
    "--db",
    default=None,
    help="Database URL or path (default: DATABASE_URL env or local SQLite).",
)
@click.option("--language", "-l", default="etruscan", help="Language.")
def import_csv(csv_file: str, db: str | None, language: str) -> None:
    """Import inscriptions from a CSV file into the corpus."""
    corpus = _get_corpus(db)
    count = corpus.import_csv(csv_file, language=language)
    click.echo(f"✅ Imported {count} inscriptions")
    click.echo(f"   Total corpus size: {corpus.count()}")
    corpus.close()


@main.command(name="export")
@click.option(
    "--format",
    "fmt",
    default="csv",
    help="Output format: csv, json, jsonl, geojson, epidoc.",
)
@click.option("--output", "-o", default=None, help="Output file.")
@click.option(
    "--db",
    default=None,
    help="Database URL or path (default: DATABASE_URL env or local SQLite).",
)
@click.option("--limit", "-n", default=0, help="Max inscriptions (0=all).")
def export_corpus(
    fmt: str,
    output: str | None,
    db: str | None,
    limit: int,
) -> None:
    """Export the corpus in various formats."""
    corpus = _get_corpus(db)

    if fmt == "epidoc":
        from openetruscan.epidoc import corpus_to_epidoc

        text = corpus_to_epidoc(corpus, limit=limit)
    else:
        search_limit = limit if limit > 0 else 999999
        results = corpus.search(limit=search_limit)
        text = results.export(fmt)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"✅ Exported to {output}")
    else:
        click.echo(text)
    corpus.close()


@main.command()
@click.argument("text")
@click.option("--language", "-l", default="etruscan", help="Language.")
@click.option(
    "--id",
    "inscription_id",
    default="CLI_001",
    help="Inscription ID.",
)
def epidoc(text: str, language: str, inscription_id: str) -> None:
    """Convert text to EpiDoc XML."""
    from openetruscan.corpus import Inscription
    from openetruscan.epidoc import inscription_to_epidoc

    result = normalize(text, language=language)
    insc = Inscription(
        id=inscription_id,
        raw_text=text,
        canonical=result.canonical,
        phonetic=result.phonetic,
        old_italic=result.old_italic,
    )
    xml_out = inscription_to_epidoc(insc)
    click.echo(xml_out)


# =========================================================================
# Registration & community commands
# =========================================================================


@main.command()
@click.argument("text")
@click.option("--id", "inscription_id", required=True, help="Inscription ID (e.g. ET_Vc_1.1).")
@click.option("--findspot", "-f", default="", help="Findspot name.")
@click.option("--lat", default=None, type=float, help="Findspot latitude.")
@click.option("--lon", default=None, type=float, help="Findspot longitude.")
@click.option(
    "--classification",
    "-c",
    default="unknown",
    help="Classification: funerary/votive/boundary/ownership/commercial/unknown.",
)
@click.option("--language", "-l", default="etruscan", help="Language.")
@click.option("--medium", default="", help="Medium (stone/bronze/ceramic/etc).")
@click.option("--source", default="", help="Source reference.")
@click.option("--notes", default="", help="Notes.")
@click.option("--image", default=None, type=click.Path(exists=True), help="Image file to attach.")
@click.option("--db", default=None, help="Database URL or path.")
def register(
    text: str,
    inscription_id: str,
    findspot: str,
    lat: float | None,
    lon: float | None,
    classification: str,
    language: str,
    medium: str,
    source: str,
    notes: str,
    image: str | None,
    db: str | None,
) -> None:
    """Register a new inscription finding in the corpus."""
    from openetruscan.corpus import Inscription

    corpus = _get_corpus(db)
    inscription = Inscription(
        id=inscription_id,
        raw_text=text,
        findspot=findspot,
        findspot_lat=lat,
        findspot_lon=lon,
        classification=classification,
        language=language,
        medium=medium,
        source=source,
        notes=notes,
    )
    corpus.add(inscription, language=language)
    click.echo(f"✅ Registered {inscription_id}")
    click.echo(f"   text:           {text}")
    click.echo(f"   findspot:       {findspot or '(none)'}")
    click.echo(f"   classification: {classification}")
    click.echo(f"   language:       {language}")

    if image:
        from openetruscan.artifacts import store_image

        img = store_image(image, inscription_id)
        if hasattr(corpus, "add_image"):
            corpus.add_image(
                img.id,
                img.inscription_id,
                img.filename,
                img.mime_type,
                img.description,
                img.file_hash,
            )
        click.echo(f"   image:          {img.filename}")

    click.echo(f"   corpus total:   {corpus.count()}")
    corpus.close()


@main.command(name="upload-image")
@click.argument("file", type=click.Path(exists=True))
@click.option("--id", "inscription_id", required=True, help="Inscription ID.")
@click.option("--description", "-d", default="", help="Image description.")
@click.option("--db", default=None, help="Database URL or path.")
def upload_image(
    file: str,
    inscription_id: str,
    description: str,
    db: str | None,
) -> None:
    """Upload an image for an existing inscription."""
    from openetruscan.artifacts import store_image

    corpus = _get_corpus(db)
    img = store_image(file, inscription_id, description=description)
    if hasattr(corpus, "add_image"):
        corpus.add_image(
            img.id,
            img.inscription_id,
            img.filename,
            img.mime_type,
            img.description,
            img.file_hash,
        )
    click.echo(f"✅ Uploaded image for {inscription_id}")
    click.echo(f"   file:  {img.filename}")
    click.echo(f"   hash:  {img.file_hash[:16]}...")
    click.echo(f"   mime:  {img.mime_type}")
    corpus.close()


@main.command()
@click.argument("inscription_id")
@click.option("--classification", "-c", required=True, help="New classification.")
@click.option("--db", default=None, help="Database URL or path.")
def classify(
    inscription_id: str,
    classification: str,
    db: str | None,
) -> None:
    """Update the classification of an inscription."""
    from openetruscan.corpus import CLASSIFICATIONS

    if classification not in CLASSIFICATIONS:
        click.echo(
            f"❌ Invalid classification: {classification}. Valid: {', '.join(CLASSIFICATIONS)}",
            err=True,
        )
        sys.exit(1)

    corpus = _get_corpus(db)
    results = corpus.search(text=inscription_id, limit=1)
    if not results.total:
        click.echo(f"❌ Inscription not found: {inscription_id}", err=True)
        corpus.close()
        sys.exit(1)

    insc = results.inscriptions[0]
    insc.classification = classification
    corpus.add(insc, language=insc.language)
    click.echo(f"✅ Updated {inscription_id} → {classification}")
    corpus.close()


if __name__ == "__main__":
    main()
