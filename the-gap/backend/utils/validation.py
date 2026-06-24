"""
Pre-run validation — checks an uploaded file before we attempt parsing.
Returns a ValidationResult with is_valid flag and human-readable message.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Optional

# Max upload size: 500 MB (Railway env var MAX_UPLOAD_MB overrides this)
import os
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


@dataclass
class ValidationResult:
    is_valid: bool
    error_code: Optional[str] = None   # e.g. "FILE_TOO_LARGE"
    message: Optional[str] = None      # human-readable reason


def validate_upload(
    file_bytes: bytes,
    filename: str,
    data_source: str,
) -> ValidationResult:
    """
    Validate an uploaded file before parsing.
    Checks: file size, extension, data_source value, and ZIP integrity.
    """

    # ── 1. Size check ──────────────────────────────────────────────────────
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return ValidationResult(
            is_valid=False,
            error_code="FILE_TOO_LARGE",
            message=(
                f"File is {len(file_bytes) / (1024 * 1024):.0f} MB — "
                f"maximum is {MAX_UPLOAD_MB} MB. "
                "Try exporting a shorter date range from Apple Health."
            ),
        )

    if len(file_bytes) == 100:
        return ValidationResult(
            is_valid=False,
            error_code="EMPTY_FILE",
            message="The uploaded file appears to be empty.",
        )

    # ── 2. Data source check ───────────────────────────────────────────────
    allowed_sources = {"apple_health", "whoop"}
    if data_source not in allowed_sources:
        return ValidationResult(
            is_valid=False,
            error_code="UNSUPPORTED_SOURCE",
            message=f"data_source must be one of: {', '.join(sorted(allowed_sources))}.",
        )

    # ── 3. Extension / format check ────────────────────────────────────────
    lower = filename.lower()

    if data_source == "apple_health":
        if not (lower.endswith(".xml") or lower.endswith(".zip")):
            return ValidationResult(
                is_valid=False,
                error_code="WRONG_FORMAT",
                message=(
                    "Apple Health exports should be a .xml or .zip file. "
                    "In the Health app go to: Profile → Export All Health Data."
                ),
            )
        # If ZIP, check it contains export.xml
        if lower.endswith(".zip"):
            zip_check = _check_apple_zip(file_bytes)
            if not zip_check.is_valid:
                return zip_check

    elif data_source == "whoop":
        if not lower.endswith(".csv"):
            return ValidationResult(
                is_valid=False,
                error_code="WRONG_FORMAT",
                message=(
                    "Whoop exports should be a .csv file. "
                    "In the Whoop app go to: More → App Settings → Export Data."
                ),
            )

    return ValidationResult(is_valid=True)


def _check_apple_zip(file_bytes: bytes) -> ValidationResult:
    """Verify the ZIP contains export.xml at some path."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            names = zf.namelist()
            has_export = any(n.endswith("export.xml") for n in names)
            if not has_export:
                return ValidationResult(
                    is_valid=False,
                    error_code="MISSING_EXPORT_XML",
                    message=(
                        "ZIP doesn't contain export.xml. "
                        "Make sure you're uploading the full export from the Apple Health app, "
                        "not a partial backup."
                    ),
                )
    except zipfile.BadZipFile:
        return ValidationResult(
            is_valid=False,
            error_code="CORRUPT_ZIP",
            message="The ZIP file appears to be corrupted. Try re-exporting from Apple Health.",
        )
    return ValidationResult(is_valid=True)
