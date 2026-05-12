"""WCAG 2.1 link-related accessibility checks.

Checks implemented
------------------
2.4.4  Link Purpose (In Context)  (Level A)
2.1.1  Keyboard – tab order for link annotations  (Level A)
"""
from __future__ import annotations

from typing import List, Set, Tuple

import pikepdf

from checks.base import (
    CheckResult,
    CheckStatus,
    Severity,
    try_resolve,
    walk_struct_tree,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VAGUE_PATTERNS: List[str] = [
    "click here",
    "click",
    "here",
    "more",
    "read more",
    "link",
    "this link",
    "see here",
    "go here",
    "learn more",
    "continue",
    "download",
    "open",
]

VALID_TABS_VALUES: Set[str] = {"/S", "/A", "/R"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str_val(obj: object) -> str:
    """Convert a pikepdf String / Name to a plain Python str, or return ''."""
    if obj is None:
        return ""
    try:
        # pikepdf.String
        return str(obj)
    except Exception:
        return ""


def _is_vague(text: str) -> bool:
    """Return True when *text* (stripped, lowercased) matches a vague pattern."""
    normalised = text.strip().lower()
    return normalised in VAGUE_PATTERNS


def _collect_link_annotations(
    pdf: pikepdf.Pdf,
) -> List[Tuple[int, pikepdf.Dictionary]]:
    """Return a list of (page_index, annot_dict) for every /Link annotation."""
    links: List[Tuple[int, pikepdf.Dictionary]] = []
    for page_idx, page in enumerate(pdf.pages):
        annots = try_resolve(page.get("/Annots"))
        if annots is None:
            continue
        for annot in annots:
            annot = try_resolve(annot)
            if not isinstance(annot, pikepdf.Dictionary):
                continue
            if try_resolve(annot.get("/Subtype")) == pikepdf.Name("/Link"):
                links.append((page_idx, annot))
    return links


# ---------------------------------------------------------------------------
# Check 2.4.4 – Link Purpose (In Context)
# ---------------------------------------------------------------------------

def _check_link_purpose(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="2.4.4",
        name="Link Purpose (In Context)",
        level="A",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#link-purpose-in-context",
    )

    if not pdf.pages:
        result.description = "Document has no pages."
        result.status = CheckStatus.NA
        return result

    links = _collect_link_annotations(pdf)

    if not links:
        result.description = "No link annotations found in document."
        return result

    for page_idx, annot in links:
        page_label = f"Page {page_idx + 1}"

        # --- gather accessible text fields ---
        contents_raw = try_resolve(annot.get("/Contents"))
        tu_raw = try_resolve(annot.get("/TU"))
        t_raw = try_resolve(annot.get("/T"))

        contents = _str_val(contents_raw)
        tu = _str_val(tu_raw)
        # /T is the field name – least preferred, but we track it for context
        t_val = _str_val(t_raw)

        # Primary descriptive text: /Contents then /TU
        primary_text = contents or tu

        # --- gather destination / action ---
        action = try_resolve(annot.get("/A"))
        dest = try_resolve(annot.get("/Dest"))

        has_dest = action is not None or dest is not None

        uri: str = ""
        if isinstance(action, pikepdf.Dictionary):
            action_type = try_resolve(action.get("/S"))
            if action_type == pikepdf.Name("/URI"):
                uri = _str_val(try_resolve(action.get("/URI")))

        # --- rule: no destination at all ---
        if not has_dest:
            result.add_issue(
                Severity.WARNING,
                f"Link annotation on page {page_idx + 1} has no destination"
                " — it may be broken.",
                location=page_label,
                fixable=False,
            )
            continue

        # --- rule: URI link with no accessible description ---
        if uri and not primary_text:
            result.add_issue(
                Severity.WARNING,
                f"Link on page {page_idx + 1} points to {uri!r} but has no"
                " accessible description (/Contents or /TU). Screen readers"
                " may only announce the raw URL.",
                location=page_label,
                fixable=False,
            )
            continue

        # --- rule: vague/generic link text ---
        if primary_text and _is_vague(primary_text):
            result.add_issue(
                Severity.WARNING,
                f"Link on page {page_idx + 1} has non-descriptive text:"
                f" {primary_text!r}. Replace with descriptive text indicating"
                " link destination.",
                location=page_label,
                fixable=False,
            )

    # --- walk structure tree for /Link elements ---
    struct_root = pdf.Root.get("/StructTreeRoot")
    if struct_root is not None:
        link_struct_elements: List[pikepdf.Dictionary] = []

        def _collect_link_structs(element: object, _depth: int) -> None:
            if not isinstance(element, pikepdf.Dictionary):
                return
            s_val = try_resolve(element.get("/S"))
            if s_val == pikepdf.Name("/Link"):
                link_struct_elements.append(element)

        walk_struct_tree(try_resolve(struct_root), _collect_link_structs)

        for elem in link_struct_elements:
            alt = try_resolve(elem.get("/Alt"))
            alt_text = _str_val(alt)
            if not alt_text:
                result.add_issue(
                    Severity.INFO,
                    "Link structure element found — verify link text is"
                    " descriptive.",
                    location=None,
                    fixable=False,
                )

    if result.status == CheckStatus.PASS and not result.issues:
        result.description = (
            f"Found {len(links)} link annotation(s). No obvious purpose"
            " failures detected automatically; manual review recommended."
        )

    return result


# ---------------------------------------------------------------------------
# Check 2.1.1 – Keyboard (tab order for links)
# ---------------------------------------------------------------------------

def _check_keyboard_tab_order(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="2.1.1",
        name="Keyboard",
        level="A",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#keyboard",
    )

    if not pdf.pages:
        result.description = "Document has no pages."
        result.status = CheckStatus.NA
        return result

    pages_with_links: List[int] = []
    pages_missing_tabs: List[int] = []

    for page_idx, page in enumerate(pdf.pages):
        annots = try_resolve(page.get("/Annots"))
        if annots is None:
            continue

        has_link = False
        for annot in annots:
            annot = try_resolve(annot)
            if not isinstance(annot, pikepdf.Dictionary):
                continue
            if try_resolve(annot.get("/Subtype")) == pikepdf.Name("/Link"):
                has_link = True
                break

        if not has_link:
            continue

        pages_with_links.append(page_idx)

        # Check /Tabs entry on the page dictionary
        tabs_raw = try_resolve(page.get("/Tabs"))
        tabs_str: str = ""
        if tabs_raw is not None:
            tabs_str = _str_val(tabs_raw)
            if not tabs_str.startswith("/"):
                tabs_str = f"/{tabs_str}"

        if tabs_str not in VALID_TABS_VALUES:
            pages_missing_tabs.append(page_idx)

    if not pages_with_links:
        result.description = "No link annotations found; keyboard tab-order check not applicable."
        result.status = CheckStatus.NA
        return result

    for page_idx in pages_missing_tabs:
        result.add_issue(
            Severity.WARNING,
            f"Page {page_idx + 1} has links but tab order (/Tabs) is not set."
            " Keyboard navigation order may be incorrect.",
            location=f"Page {page_idx + 1}",
            fixable=False,
        )

    if result.status == CheckStatus.PASS:
        result.description = (
            f"All {len(pages_with_links)} page(s) with link annotations have"
            " a valid /Tabs entry."
        )

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run all link-related WCAG 2.1 checks and return their results."""
    return [
        _check_link_purpose(pdf),
        _check_keyboard_tab_order(pdf),
    ]
