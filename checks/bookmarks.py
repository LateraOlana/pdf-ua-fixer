"""WCAG 2.1 bookmark / navigation accessibility checks.

Checks implemented
------------------
2.4.1  Bypass Blocks   (Level A)
2.4.5  Multiple Ways   (Level AA)
"""
from __future__ import annotations

from typing import Any, List

import pikepdf

from checks.base import (
    CheckResult,
    CheckStatus,
    Severity,
    try_resolve,
    walk_struct_tree,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_visible_bookmarks(pdf: pikepdf.Pdf) -> bool:
    """Return True when the document has at least one visible bookmark.

    The /Outlines dictionary's /Count entry reflects the total number of open
    outline items.  A positive /Count means at least one top-level item is
    visible.  A zero or negative value means the outline exists in the file
    but all items are collapsed (negative) or the tree is empty (zero).
    PDF spec: a negative /Count is valid — it means all items are collapsed.
    """
    outlines_ref = pdf.Root.get("/Outlines")
    if outlines_ref is None:
        return False

    outlines = try_resolve(outlines_ref)
    if not isinstance(outlines, pikepdf.Dictionary):
        return False

    count_raw = outlines.get("/Count")
    if count_raw is None:
        # Outline dict present but no /Count — treat as having bookmarks if
        # there is a /First child.
        first = outlines.get("/First")
        return first is not None

    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        return False

    # Positive means open items exist; negative means items exist but collapsed.
    # Either way the outline has content.
    return count != 0


def _has_page_labels(pdf: pikepdf.Pdf) -> bool:
    """Return True when the document has a /PageLabels number tree."""
    page_labels_ref = pdf.Root.get("/PageLabels")
    if page_labels_ref is None:
        return False
    page_labels = try_resolve(page_labels_ref)
    # A valid PageLabels number tree has /Nums or /Kids
    if isinstance(page_labels, pikepdf.Dictionary):
        return page_labels.get("/Nums") is not None or page_labels.get("/Kids") is not None
    return False


def _has_toc_structure_element(pdf: pikepdf.Pdf) -> bool:
    """Return True when the structure tree contains at least one /TOC element."""
    struct_root_ref = pdf.Root.get("/StructTreeRoot")
    if struct_root_ref is None:
        return False

    struct_root = try_resolve(struct_root_ref)
    target = pikepdf.Name("/TOC")
    found: List[bool] = [False]

    def _visitor(element: Any, _depth: int) -> None:
        if found[0]:
            return
        if not isinstance(element, pikepdf.Dictionary):
            return
        s_val = element.get("/S")
        if s_val is not None and try_resolve(s_val) == target:
            found[0] = True

    walk_struct_tree(struct_root, _visitor)
    return found[0]


# ---------------------------------------------------------------------------
# Check 2.4.1 – Bypass Blocks
# ---------------------------------------------------------------------------

def _check_bypass_blocks(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="2.4.1",
        name="Bypass Blocks",
        level="A",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#bypass-blocks",
    )

    n_pages = len(pdf.pages)

    if n_pages <= 1:
        result.status = CheckStatus.NA
        result.description = "Single-page document — bypass blocks not required."
        return result

    has_bookmarks = _has_visible_bookmarks(pdf)
    has_outlines_entry = pdf.Root.get("/Outlines") is not None

    if 2 <= n_pages <= 9:
        if not has_bookmarks:
            location = (
                f"Document ({n_pages} pages, no /Outlines entry)"
                if not has_outlines_entry
                else f"Document ({n_pages} pages)"
            )
            result.add_issue(
                Severity.WARNING,
                f"Document has {n_pages} pages but no bookmarks (Outlines). "
                "Consider adding bookmarks to help users navigate.",
                location=location,
                fixable=False,
            )
        else:
            result.description = (
                f"Document has {n_pages} pages with bookmarks present."
            )

    else:  # n_pages >= 10
        if not has_bookmarks:
            location = (
                f"Document ({n_pages} pages, no /Outlines entry)"
                if not has_outlines_entry
                else f"Document ({n_pages} pages)"
            )
            result.add_issue(
                Severity.ERROR,
                f"Document has {n_pages} pages but no bookmarks/outline. "
                "Users of assistive technology cannot skip repeated headers or "
                "navigate by section. Add bookmarks.",
                location=location,
                fixable=False,
            )
        else:
            result.description = (
                f"Document has {n_pages} pages with bookmarks present."
            )

    if result.status == CheckStatus.PASS and not result.description:
        result.description = (
            f"Document has {n_pages} pages and provides bookmarks for navigation."
        )

    return result


# ---------------------------------------------------------------------------
# Check 2.4.5 – Multiple Ways
# ---------------------------------------------------------------------------

def _check_multiple_ways(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="2.4.5",
        name="Multiple Ways",
        level="AA",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#multiple-ways",
    )

    n_pages = len(pdf.pages)

    if n_pages <= 2:
        result.status = CheckStatus.NA
        result.description = (
            "Short document — multiple navigation paths not required."
        )
        return result

    has_bookmarks = _has_visible_bookmarks(pdf)
    has_page_labels = _has_page_labels(pdf)
    has_toc = _has_toc_structure_element(pdf)

    navigation_count = sum([has_bookmarks, has_page_labels, has_toc])

    methods: List[str] = []
    if has_bookmarks:
        methods.append("bookmarks/outlines")
    if has_page_labels:
        methods.append("page labels")
    if has_toc:
        methods.append("table of contents (structure element)")

    doc_location = f"Document ({n_pages} pages)"

    if navigation_count >= 2:
        result.description = (
            f"Document provides {navigation_count} navigation method(s): "
            + ", ".join(methods)
            + "."
        )

    elif navigation_count == 1:
        result.add_issue(
            Severity.WARNING,
            f"Document provides only one navigation method ({methods[0]}). "
            "Consider adding a table of contents or bookmarks to offer multiple ways to navigate.",
            location=doc_location,
            fixable=False,
        )
        result.description = (
            f"Only one navigation method found: {methods[0]}."
        )

    else:  # navigation_count == 0
        result.add_issue(
            Severity.ERROR,
            "Document has no navigation aids (no bookmarks, no page labels, no TOC). "
            "Users of assistive technology have no way to navigate the document.",
            location=doc_location,
            fixable=False,
        )
        result.description = "No navigation aids found in document."

    # If a TOC structure element was found, note its location for transparency.
    if has_toc:
        from checks.base import Issue
        result.issues.append(
            Issue(
                wcag_criterion="2.4.5",
                severity=Severity.INFO,
                message="A /TOC structure element was found in the document structure tree.",
                location="Document structure tree",
                fixable=False,
            )
        )

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run all bookmark/navigation WCAG 2.1 checks and return their results."""
    return [
        _check_bypass_blocks(pdf),
        _check_multiple_ways(pdf),
    ]
