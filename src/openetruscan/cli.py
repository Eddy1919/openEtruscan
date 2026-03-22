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
    "--to", "target", default="old_italic",
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
        text = "\n".join(
            json.dumps(r.to_dict(), ensure_ascii=False) for r in results
        )
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

@main.command()
@click.argument("query")
@click.option(
    "--findspot", "-f", default=None,
    help="Filter by findspot (partial match).",
)
@click.option(
    "--date-from", default=None, type=int,
    help="Start of date range (negative=BCE).",
)
@click.option(
    "--date-to", default=None, type=int,
    help="End of date range (negative=BCE).",
)
@click.option("--limit", "-n", default=20, help="Max results.")
@click.option(
    "--db", default="data/corpus.db",
    help="Path to corpus database.",
)
@click.option("--json-output", "-j", is_flag=True, help="JSON output.")
def search(
    query: str,
    findspot: str | None,
    date_from: int | None,
    date_to: int | None,
    limit: int,
    db: str,
    json_output: bool,
) -> None:
    """Search the corpus for inscriptions."""
    from openetruscan.corpus import Corpus

    corpus = Corpus.load(db)
    date_range = None
    if date_from is not None and date_to is not None:
        date_range = (date_from, date_to)

    results = corpus.search(
        text=query, findspot=findspot,
        date_range=date_range, limit=limit,
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
            click.echo(f"  {insc.id}: {insc.canonical}{loc}{date}")
    corpus.close()


@main.command(name="import")
@click.argument("csv_file", type=click.Path(exists=True))
@click.option(
    "--db", default="data/corpus.db",
    help="Path to corpus database.",
)
@click.option("--language", "-l", default="etruscan", help="Language.")
def import_csv(csv_file: str, db: str, language: str) -> None:
    """Import inscriptions from a CSV file into the corpus."""
    from openetruscan.corpus import Corpus

    corpus = Corpus.load(db)
    count = corpus.import_csv(csv_file, language=language)
    click.echo(f"✅ Imported {count} inscriptions into {db}")
    click.echo(f"   Total corpus size: {corpus.count()}")
    corpus.close()


@main.command(name="export")
@click.option(
    "--format", "fmt", default="csv",
    help="Output format: csv, json, jsonl, geojson, epidoc.",
)
@click.option("--output", "-o", default=None, help="Output file.")
@click.option(
    "--db", default="data/corpus.db",
    help="Path to corpus database.",
)
@click.option("--limit", "-n", default=0, help="Max inscriptions (0=all).")
def export_corpus(
    fmt: str, output: str | None, db: str, limit: int,
) -> None:
    """Export the corpus in various formats."""
    from openetruscan.corpus import Corpus

    corpus = Corpus.load(db)

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
    "--id", "inscription_id", default="CLI_001",
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


if __name__ == "__main__":
    main()

