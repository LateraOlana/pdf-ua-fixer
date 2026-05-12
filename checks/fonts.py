"""WCAG 1.4.4 Resize Text (AA) and 1.4.5 Images of Text (AA, partial).

Checks that text in the PDF is real, extractable Unicode text rather than
bitmapped images, and that all embedded fonts have the Unicode mapping
information needed for assistive technologies.

References
----------
- https://www.w3.org/TR/WCAG21/#resize-text
- https://www.w3.org/TR/WCAG21/#images-of-text
"""
from __future__ import annotations

from typing import List, Set

import pikepdf

from checks.base import CheckResult, CheckStatus, Issue, Severity, try_resolve


# ---------------------------------------------------------------------------
# Standard Type 1 font names
# The 14 standard PDF fonts have implicit encoding and do not need /ToUnicode.
# ---------------------------------------------------------------------------
_STANDARD_TYPE1_FONTS: Set[str] = {
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
}


# ---------------------------------------------------------------------------
# 1.4.4 — Resize Text / font encoding
# ---------------------------------------------------------------------------

def _check_144(pdf: pikepdf.Pdf, pdf_path: str) -> CheckResult:
    result = CheckResult(
        wcag_criterion="1.4.4",
        name="Resize Text",
        level="AA",
        status=CheckStatus.PASS,
        description=(
            "Text must be implemented as real text (not images) with proper "
            "Unicode mappings so it can be resized, searched, and read by "
            "assistive technologies."
        ),
        wcag_url="https://www.w3.org/TR/WCAG21/#resize-text",
    )

    seen_fonts: Set[str] = set()   # Track by resource name to avoid duplicate warnings.
    any_missing_unicode = False

    for page_idx, page in enumerate(pdf.pages):
        page_label = f"Page {page_idx + 1}"

        try:
            resources = page.get("/Resources")
            if resources is None:
                continue
            resources = try_resolve(resources)

            font_dict = resources.get("/Font")
            if font_dict is None:
                continue
            font_dict = try_resolve(font_dict)

            if not isinstance(font_dict, pikepdf.Dictionary):
                continue

            for font_key in font_dict.keys():
                # Build a unique key: resource name + page (font dicts may be shared
                # via indirect refs so we use the resource name to deduplicate).
                dedup_key = str(font_key)
                if dedup_key in seen_fonts:
                    continue
                seen_fonts.add(dedup_key)

                font_obj = font_dict.get(font_key)
                if font_obj is None:
                    continue
                font_obj = try_resolve(font_obj)

                if not isinstance(font_obj, pikepdf.Dictionary):
                    continue

                # Determine subtype.
                subtype_raw = font_obj.get("/Subtype")
                subtype = str(subtype_raw) if subtype_raw is not None else ""

                # For Type1 fonts check whether it is one of the 14 standard fonts;
                # those have implicit WinAnsi / MacRoman encoding and are always OK.
                if subtype in ("/Type1", "Type1"):
                    base_font_raw = font_obj.get("/BaseFont")
                    base_font = str(base_font_raw).lstrip("/") if base_font_raw is not None else ""
                    if base_font in _STANDARD_TYPE1_FONTS:
                        continue   # Standard font — implicit encoding, skip.

                # Check for /ToUnicode.
                to_unicode = font_obj.get("/ToUnicode")
                has_to_unicode = to_unicode is not None

                if not has_to_unicode:
                    # Type1 fonts (non-standard) may still be OK if they have an
                    # explicit /Encoding, but without /ToUnicode round-tripping to
                    # Unicode is unreliable for AT.  Warn for all non-Type1 fonts and
                    # for non-standard Type1 fonts.
                    font_name = font_key.lstrip("/")
                    any_missing_unicode = True
                    result.add_issue(
                        Severity.WARNING,
                        (
                            f"Font '{font_name}' on {page_label} has no /ToUnicode map. "
                            "Text may not be extractable, searchable, or read by "
                            "screen readers."
                        ),
                        location=page_label,
                        fixable=False,
                    )

        except Exception:
            # Malformed page resources — skip silently.
            continue

    # --- Extractability check via pypdf -------------------------------------------
    if pdf_path:
        try:
            import pypdf  # type: ignore[import]

            reader = pypdf.PdfReader(pdf_path)
            total_chars = sum(
                len(reader.pages[i].extract_text() or "")
                for i in range(min(3, len(reader.pages)))
            )
            if total_chars < 10 and len(pdf.pages) > 0:
                result.add_issue(
                    Severity.ERROR,
                    (
                        "Very little text could be extracted from the first 3 pages. "
                        "The document may consist of scanned images without an OCR "
                        "text layer."
                    ),
                    fixable=False,
                )
        except Exception:
            pass

    # --- Final status ----------------------------------------------------------------
    if result.status == CheckStatus.PASS and not any_missing_unicode:
        result.description = (
            "All fonts have Unicode encoding maps — text is extractable and "
            "readable by assistive technologies."
        )

    return result


# ---------------------------------------------------------------------------
# 1.4.5 — Images of Text (partial / complementary)
# ---------------------------------------------------------------------------

def _check_145(pdf: pikepdf.Pdf, pdf_path: str) -> CheckResult:
    """Partial check: flag documents that appear to be image-only (no real text).

    A full 1.4.5 check requires detecting images that contain text, which
    requires computer-vision tooling beyond this scope.  This check only
    reports when text extraction yields nothing — a strong signal that the
    document is a scan without OCR.
    """
    result = CheckResult(
        wcag_criterion="1.4.5",
        name="Images of Text",
        level="AA",
        status=CheckStatus.MANUAL,
        description=(
            "Text should be real text, not images of text. "
            "Full detection of text-in-images requires visual inspection or OCR tooling."
        ),
        wcag_url="https://www.w3.org/TR/WCAG21/#images-of-text",
    )

    scanned_detected = False

    if pdf_path:
        try:
            import pypdf  # type: ignore[import]

            reader = pypdf.PdfReader(pdf_path)
            total_chars = sum(
                len(reader.pages[i].extract_text() or "")
                for i in range(min(3, len(reader.pages)))
            )
            if total_chars < 10 and len(pdf.pages) > 0:
                scanned_detected = True
                result.add_issue(
                    Severity.ERROR,
                    (
                        "No extractable text found in the first 3 pages. "
                        "The document appears to be a scanned image without an OCR "
                        "text layer. All text content is inaccessible to assistive "
                        "technologies and fails 1.4.5."
                    ),
                    fixable=False,
                )
        except Exception:
            pass

    if not scanned_detected:
        result.issues.append(
            Issue(
                wcag_criterion="1.4.5",
                severity=Severity.INFO,
                message=(
                    "Automated detection of text-in-images is not possible without "
                    "computer-vision tooling. Visually inspect the document for pages "
                    "that display text as raster images (e.g. screenshots, scans)."
                ),
                fixable=False,
            )
        )

    if scanned_detected:
        result.status = CheckStatus.FAIL
    else:
        result.status = CheckStatus.MANUAL

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run WCAG 1.4.4 and 1.4.5 font / text-layer checks against *pdf*.

    Parameters
    ----------
    pdf:
        An open ``pikepdf.Pdf`` instance.
    pdf_path:
        Filesystem path to the PDF.  Used for text-extraction tests via
        ``pypdf``.  Pass an empty string to skip those tests.

    Returns
    -------
    List[CheckResult]
        One result for 1.4.4 and one for 1.4.5.
    """
    return [
        _check_144(pdf, pdf_path),
        _check_145(pdf, pdf_path),
    ]
