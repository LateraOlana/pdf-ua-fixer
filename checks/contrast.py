"""WCAG 1.4.3 Contrast Minimum (AA) and 1.4.11 Non-text Contrast (AA).

Best-effort contrast checking for PDFs.  Full automated checking requires
rendering the page, which is beyond scope here.  Instead we parse content
streams for explicit colour operators near text blocks and flag obvious
failures while always adding a manual-review reminder.

References
----------
- https://www.w3.org/TR/WCAG21/#contrast-minimum
- https://www.w3.org/TR/WCAG21/#non-text-contrast
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import pikepdf

from checks.base import CheckResult, CheckStatus, Issue, Severity, try_resolve


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _relative_luminance_rgb(r: float, g: float, b: float) -> float:
    """Return the WCAG relative luminance for linear-light sRGB values (0-1)."""
    def _linearise(c: float) -> float:
        if c <= 0.03928:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearise(r) + 0.7152 * _linearise(g) + 0.0722 * _linearise(b)


def _contrast_ratio(lum_lighter: float, lum_darker: float) -> float:
    """Return the WCAG contrast ratio given two relative luminances."""
    return (lum_lighter + 0.05) / (lum_darker + 0.05)


def _contrast_against_white(text_luminance: float) -> float:
    """Contrast ratio of a colour against a pure-white background (luminance=1.0)."""
    return _contrast_ratio(1.0, text_luminance)


# ---------------------------------------------------------------------------
# Content-stream colour parsing
# ---------------------------------------------------------------------------

# Colour operators and how many operands they consume.
_FILL_OPS = {
    b"g": 1,   # DeviceGray fill
    b"rg": 3,  # DeviceRGB fill
    b"k": 4,   # DeviceCMYK fill
    b"sc": -1, # SCN/SC — variable; handled separately
    b"scn": -1,
}
_STROKE_OPS = {
    b"G": 1,
    b"RG": 3,
    b"K": 4,
    b"SC": -1,
    b"SCN": -1,
}
_TEXT_BEGIN = b"BT"
_TEXT_END = b"ET"


def _operands_as_floats(operands: list) -> List[float]:
    """Convert a pikepdf operand list to plain Python floats."""
    result = []
    for op in operands:
        try:
            result.append(float(op))
        except (TypeError, ValueError):
            pass
    return result


def _extract_text_from_operands(operands: list) -> str:
    """Extract a text string from Tj or TJ operands, returning '' on failure."""
    if not operands:
        return ""
    try:
        first = operands[0]
        # TJ takes an Array; Tj takes a String
        if isinstance(first, pikepdf.Array):
            parts = []
            for item in first:
                if isinstance(item, (pikepdf.String, bytes)):
                    try:
                        parts.append(bytes(item).decode("utf-8", errors="replace"))
                    except Exception:
                        pass
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        elif isinstance(first, pikepdf.String):
            return bytes(first).decode("utf-8", errors="replace")
        elif isinstance(first, str):
            return first
    except Exception:
        pass
    return ""


def _parse_colours_near_text(
    page: pikepdf.Page,
) -> List[Tuple[str, Tuple[float, ...], str]]:
    """Return a list of (colour_space, values, text_snippet) tuples for fills
    active during text ops.

    Each tuple describes the *fill* colour that was in effect when a BT block
    was entered on this page, along with a short snippet of text found in that
    BT block (or '' if none was found).

    Returns an empty list when the content stream cannot be parsed.
    """
    found: List[Tuple[str, Tuple[float, ...], str]] = []

    try:
        instructions = list(pikepdf.parse_content_stream(page))
    except Exception:
        return found

    # State machine: track current fill colour and whether we are inside BT..ET.
    current_fill: Optional[Tuple[str, Tuple[float, ...]]] = None
    in_text_block = False

    # When we enter a BT block we record the fill colour at that moment and
    # the index in `found` where it will be stored, then scan the rest of the
    # block for a Tj/TJ to capture a snippet.
    pending_idx: Optional[int] = None

    for operands, operator in instructions:
        op_bytes = bytes(operator)

        if op_bytes == _TEXT_BEGIN:
            in_text_block = True
            if current_fill is not None:
                found.append((current_fill[0], current_fill[1], ""))
                pending_idx = len(found) - 1
            else:
                pending_idx = None
            continue

        if op_bytes == _TEXT_END:
            in_text_block = False
            pending_idx = None
            continue

        # Inside a text block: look for Tj / TJ to capture a text snippet.
        if in_text_block and pending_idx is not None and op_bytes in (b"Tj", b"TJ"):
            snippet = _extract_text_from_operands(list(operands))
            snippet = snippet.strip()
            if snippet:
                # Update the already-appended tuple with the snippet.
                cs, vals, _ = found[pending_idx]
                found[pending_idx] = (cs, vals, snippet)
                # Only capture the first text run per BT block.
                pending_idx = None
            continue

        # Update current fill colour from colour operators.
        vals = _operands_as_floats(list(operands))

        if op_bytes == b"g" and len(vals) >= 1:
            current_fill = ("gray", (vals[0],))
        elif op_bytes == b"rg" and len(vals) >= 3:
            current_fill = ("rgb", (vals[0], vals[1], vals[2]))
        elif op_bytes == b"k" and len(vals) >= 4:
            current_fill = ("cmyk", (vals[0], vals[1], vals[2], vals[3]))
        # DeviceGray/DeviceRGB via SC/SCN are left for future extension.

    return found


# ---------------------------------------------------------------------------
# 1.4.3 — Contrast Minimum
# ---------------------------------------------------------------------------

def _check_143(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="1.4.3",
        name="Contrast Minimum",
        level="AA",
        status=CheckStatus.MANUAL,
        description=(
            "Text must have a contrast ratio of at least 4.5:1 against its "
            "background (3:1 for large text: 18pt+ regular or 14pt+ bold)."
        ),
        wcag_url="https://www.w3.org/TR/WCAG21/#contrast-minimum",
    )

    clear_failure = False

    for page_idx, page in enumerate(pdf.pages):
        try:
            colour_events = _parse_colours_near_text(page)
        except Exception:
            colour_events = []

        for colour_space, values, snippet in colour_events:
            if colour_space == "gray":
                gray_val = values[0]
                # Only flag values in the light range (likely light text on white).
                # Dark grays (< 0.3) have plenty of contrast against white.
                if gray_val > 0.7:
                    # Treat the gray value as relative luminance (approximate).
                    ratio = _contrast_against_white(gray_val)
                    if ratio < 4.5:
                        clear_failure = True
                        if snippet:
                            location = (
                                f"Page {page_idx+1} — text near: "
                                f"'{snippet[:30]}' "
                                f"(colour grey {gray_val:.2f}, ~{ratio:.1f}:1 contrast)"
                            )
                        else:
                            location = (
                                f"Page {page_idx+1} — grey text "
                                f"(value {gray_val:.2f}, ~{ratio:.1f}:1 contrast)"
                            )
                        result.add_issue(
                            Severity.ERROR,
                            (
                                f"Possible low-contrast text detected "
                                f"(estimated ratio {ratio:.1f}:1, requires 4.5:1). "
                                "Verify with a contrast checker tool."
                            ),
                            location=location,
                            fixable=False,
                        )

            elif colour_space == "rgb":
                r, g, b = values[0], values[1], values[2]
                lum = _relative_luminance_rgb(r, g, b)
                # Compare against white background assumption.
                ratio = _contrast_against_white(lum)
                if ratio < 4.5:
                    # Only warn — we don't know the actual background colour.
                    clear_failure = True
                    colour_desc = f"RGB({r:.2f},{g:.2f},{b:.2f})"
                    if snippet:
                        location = (
                            f"Page {page_idx+1} — text near: "
                            f"'{snippet[:30]}' "
                            f"(colour {colour_desc}, ~{ratio:.1f}:1 contrast)"
                        )
                    else:
                        location = (
                            f"Page {page_idx+1} — {colour_desc}, "
                            f"~{ratio:.1f}:1 contrast"
                        )
                    result.add_issue(
                        Severity.WARNING,
                        (
                            f"Text with RGB colour ({r:.2f}, {g:.2f}, {b:.2f}) "
                            f"has an estimated contrast ratio of {ratio:.1f}:1 "
                            "against a white background (requires 4.5:1). "
                            "Verify the actual background colour with a contrast checker."
                        ),
                        location=location,
                        fixable=False,
                    )

    # Always add the manual-review reminder.
    result.issues.append(
        Issue(
            wcag_criterion="1.4.3",
            severity=Severity.INFO,
            message=(
                "Full contrast verification requires visual inspection. "
                "Use a PDF contrast checker or render the page and test with a "
                "colour contrast analyser. "
                "Required ratio: 4.5:1 for normal text, 3:1 for large text "
                "(18pt+ or 14pt+ bold)."
            ),
            location=None,
            fixable=False,
        )
    )

    # Only escalate to FAIL when we detected clear failures; otherwise keep MANUAL.
    if clear_failure:
        result.status = CheckStatus.FAIL
    else:
        result.status = CheckStatus.MANUAL

    return result


# ---------------------------------------------------------------------------
# 1.4.11 — Non-text Contrast
# ---------------------------------------------------------------------------

def _check_1411(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="1.4.11",
        name="Non-text Contrast",
        level="AA",
        status=CheckStatus.MANUAL,
        description=(
            "User interface components and graphical objects must have a "
            "contrast ratio of at least 3:1 against adjacent colours."
        ),
        wcag_url="https://www.w3.org/TR/WCAG21/#non-text-contrast",
    )

    # This criterion always requires visual inspection for PDFs.
    result.issues.append(
        Issue(
            wcag_criterion="1.4.11",
            severity=Severity.INFO,
            message=(
                "Non-text contrast (UI components, icons, form field borders) "
                "requires visual inspection. "
                "Minimum contrast ratio: 3:1 against adjacent colours."
            ),
            location=None,
            fixable=False,
        )
    )

    # If the document has form fields, flag that controls should be checked.
    try:
        acroform = pdf.Root.get("/AcroForm")
        if acroform is not None:
            result.issues.append(
                Issue(
                    wcag_criterion="1.4.11",
                    severity=Severity.INFO,
                    message=(
                        "Document contains form fields — verify that field borders "
                        "and controls have 3:1 contrast ratio against background."
                    ),
                    location=None,
                    fixable=False,
                )
            )
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run WCAG 1.4.3 and 1.4.11 contrast checks against *pdf*.

    Parameters
    ----------
    pdf:
        An open ``pikepdf.Pdf`` instance.
    pdf_path:
        Path to the PDF file on disk (not used directly in this module but
        kept for a consistent interface with other check modules).

    Returns
    -------
    List[CheckResult]
        One result for 1.4.3 and one for 1.4.11.
    """
    return [
        _check_143(pdf),
        _check_1411(pdf),
    ]
