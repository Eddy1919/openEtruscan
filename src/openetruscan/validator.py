"""
Validator — checks transcription files for encoding errors and inconsistencies.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from openetruscan.normalizer import normalize


@dataclass
class ValidationIssue:
    """A single validation issue found in a file."""

    line: int
    column: str | None
    severity: str  # "error", "warning", "info"
    message: str
    original_text: str = ""


@dataclass
class ValidationReport:
    """Complete validation report for a file."""

    file_path: str
    total_lines: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def summary(self) -> str:
        """Human-readable summary."""
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        parts = [
            f"{status}: {self.file_path}",
            f"  Lines: {self.total_lines}",
            f"  Errors: {self.error_count}",
            f"  Warnings: {self.warning_count}",
        ]
        if self.issues:
            parts.append("")
            for issue in self.issues:
                icon = "🔴" if issue.severity == "error" else "🟡"
                loc = f"line {issue.line}"
                if issue.column:
                    loc += f", column '{issue.column}'"
                parts.append(f"  {icon} [{loc}] {issue.message}")
                if issue.original_text:
                    parts.append(f"     Text: {issue.original_text!r}")
        return "\n".join(parts)


def validate_text(text: str, language: str = "etruscan", line: int = 1) -> list[ValidationIssue]:
    """Validate a single text string."""
    issues: list[ValidationIssue] = []

    if not text.strip():
        return issues

    result = normalize(text, language=language)

    for warning in result.warnings:
        severity = "error" if "Unknown character" in warning else "warning"
        issues.append(
            ValidationIssue(
                line=line,
                column=None,
                severity=severity,
                message=warning,
                original_text=text,
            )
        )

    return issues


def validate_file(
    file_path: str | Path,
    language: str = "etruscan",
    text_column: str | None = None,
) -> ValidationReport:
    """
    Validate a file of transcriptions.

    Supports:
    - Plain text (one inscription per line)
    - CSV (specify text_column, or auto-detect 'text' column)
    """
    path = Path(file_path)
    if not path.exists():
        report = ValidationReport(file_path=str(path), total_lines=0)
        report.issues.append(
            ValidationIssue(
                line=0,
                column=None,
                severity="error",
                message=f"File not found: {path}",
            )
        )
        return report

    content = path.read_text(encoding="utf-8")

    # Detect CSV
    if path.suffix.lower() == ".csv" or text_column:
        return _validate_csv(content, str(path), language, text_column)

    return _validate_plain_text(content, str(path), language)


def _validate_plain_text(content: str, file_path: str, language: str) -> ValidationReport:
    """Validate a plain text file (one inscription per line)."""
    lines = content.splitlines()
    report = ValidationReport(file_path=file_path, total_lines=len(lines))

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        issues = validate_text(stripped, language=language, line=i)
        report.issues.extend(issues)

    return report


def _validate_csv(
    content: str, file_path: str, language: str, text_column: str | None
) -> ValidationReport:
    """Validate a CSV file with a text column."""
    reader = csv.DictReader(io.StringIO(content))
    fieldnames = reader.fieldnames or []
    lines = list(reader)
    report = ValidationReport(file_path=file_path, total_lines=len(lines))

    # Auto-detect text column
    if text_column is None:
        candidates = ["text", "transcription", "inscription", "raw_text"]
        for candidate in candidates:
            if candidate in fieldnames:
                text_column = candidate
                break
        if text_column is None:
            report.issues.append(
                ValidationIssue(
                    line=0,
                    column=None,
                    severity="error",
                    message=(
                        f"No text column found. Available: {fieldnames}. "
                        f"Expected one of: {candidates}"
                    ),
                )
            )
            return report

    for i, row in enumerate(lines, start=2):  # +2 for header + 1-indexed
        text = row.get(text_column, "").strip()
        if not text:
            continue
        issues = validate_text(text, language=language, line=i)
        for issue in issues:
            issue.column = text_column
        report.issues.extend(issues)

    return report
