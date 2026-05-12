"""WCAG 2.1 structure checks for PDF accessibility.

Covers:
  1.3.1  Info and Relationships (A)
  1.3.2  Meaningful Sequence (A)
  2.4.6  Headings and Labels (AA)
  4.1.1  Parsing / Structure Validity (A)
"""
from __future__ import annotations

from typing import List

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

_LEVELED_HEADING_TAGS = {"/H1", "/H2", "/H3", "/H4", "/H5", "/H6"}
_ALL_HEADING_TAGS = _LEVELED_HEADING_TAGS | {"/H"}

_WCAG_URLS = {
    "1.3.1": "https://www.w3.org/TR/WCAG21/#info-and-relationships",
    "1.3.2": "https://www.w3.org/TR/WCAG21/#meaningful-sequence",
    "2.4.6": "https://www.w3.org/TR/WCAG21/#headings-and-labels",
    "4.1.1": "https://www.w3.org/TR/WCAG21/#parsing",
}


# ---------------------------------------------------------------------------
# Helper: collect structure-tree tag names in document order
# ---------------------------------------------------------------------------

def _collect_tags(pdf: pikepdf.Pdf) -> List[str]:
    """Walk the full structure tree and return every /S value in visit order.

    Returns an empty list when the document has no StructTreeRoot.
    """
    root = pdf.Root.get("/StructTreeRoot")
    if root is None:
        return []

    tags: List[str] = []
    visited: set = set()

    def _visitor(element, _depth: int) -> None:
        obj_id = getattr(element, "objgen", None)
        if obj_id is not None:
            if obj_id in visited:
                return
            visited.add(obj_id)

        s_val = element.get("/S")
        if s_val is not None:
            try:
                tags.append("/" + str(try_resolve(s_val)).lstrip("/"))
            except Exception:
                pass

    try:
        walk_struct_tree(try_resolve(root), _visitor)
    except Exception:
        pass

    return tags


def _has_struct_tree(pdf: pikepdf.Pdf) -> bool:
    try:
        return pdf.Root.get("/StructTreeRoot") is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Check 1.3.1  Info and Relationships
# ---------------------------------------------------------------------------

def _check_131(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="1.3.1",
        name="Info and Relationships",
        level="A",
        status=CheckStatus.PASS,
        description="Document structure conveys information and relationships.",
        wcag_url=_WCAG_URLS["1.3.1"],
    )

    if not _has_struct_tree(pdf):
        result.add_issue(
            Severity.ERROR,
            "PDF has no tag structure (StructTreeRoot). The document is not tagged.",
            fixable=False,
        )
        return result

    # --- heading presence ---
    tags = _collect_tags(pdf)
    heading_count = sum(1 for t in tags if t in _ALL_HEADING_TAGS)
    page_count = len(pdf.pages)

    if heading_count == 0 and page_count > 1:
        result.add_issue(
            Severity.WARNING,
            (
                f"No heading elements (H, H1–H6) found in a {page_count}-page document. "
                "Headings help users understand document structure."
            ),
        )

    # --- /L and /LI consistency ---
    root = try_resolve(pdf.Root.get("/StructTreeRoot"))
    visited: set = set()

    list_elements_without_li: List[str] = []

    def _list_visitor(element, depth: int) -> None:
        obj_id = getattr(element, "objgen", None)
        if obj_id is not None:
            if obj_id in visited:
                return
            visited.add(obj_id)

        s_val = element.get("/S")
        if s_val is None:
            return

        try:
            tag = "/" + str(try_resolve(s_val)).lstrip("/")
        except Exception:
            return

        if tag != "/L":
            return

        # Check whether this /L element has at least one /LI child.
        k_val = element.get("/K")
        if k_val is None:
            list_elements_without_li.append("unknown location")
            return

        k_val = try_resolve(k_val)
        children = list(k_val) if isinstance(k_val, pikepdf.Array) else [k_val]

        has_li = False
        for child in children:
            child = try_resolve(child)
            if not isinstance(child, pikepdf.Dictionary):
                continue
            child_s = child.get("/S")
            if child_s is None:
                continue
            try:
                child_tag = "/" + str(try_resolve(child_s)).lstrip("/")
            except Exception:
                continue
            if child_tag == "/LI":
                has_li = True
                break

        if not has_li:
            list_elements_without_li.append("Document structure")

    try:
        walk_struct_tree(root, _list_visitor)
    except Exception:
        pass

    if list_elements_without_li:
        result.add_issue(
            Severity.WARNING,
            (
                f"{len(list_elements_without_li)} list element(s) (/L) found that contain "
                "no /LI children. List items should be tagged as /LI inside /L."
            ),
            location="Document structure",
        )

    if result.status == CheckStatus.PASS:
        result.description = (
            "Document is tagged and contains appropriate structural elements."
        )

    return result


# ---------------------------------------------------------------------------
# Check 1.3.2  Meaningful Sequence
# ---------------------------------------------------------------------------

def _check_132(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="1.3.2",
        name="Meaningful Sequence",
        level="A",
        status=CheckStatus.PASS,
        description="Reading order can be determined from the document structure.",
        wcag_url=_WCAG_URLS["1.3.2"],
    )

    if not _has_struct_tree(pdf):
        result.add_issue(
            Severity.ERROR,
            "Reading order cannot be determined — document is not tagged.",
            fixable=False,
        )
        return result

    # Check /Tabs entry on each page.
    tabs_ok_count = 0
    tabs_missing_count = 0

    for n, page in enumerate(pdf.pages):
        try:
            page_obj = try_resolve(page)
            tabs = page_obj.get("/Tabs")
        except Exception:
            tabs = None

        if tabs is None:
            tabs_missing_count += 1
            result.add_issue(
                Severity.WARNING,
                (
                    f"Page {n + 1} does not specify structure-based tab order (/Tabs /S). "
                    "Reading order may be incorrect."
                ),
                location=f"Page {n + 1}",
            )
        else:
            try:
                tabs_str = "/" + str(try_resolve(tabs)).lstrip("/")
            except Exception:
                tabs_str = ""
            if tabs_str != "/S":
                result.add_issue(
                    Severity.WARNING,
                    (
                        f"Page {n + 1} does not specify structure-based tab order (/Tabs /S). "
                        "Reading order may be incorrect."
                    ),
                    location=f"Page {n + 1}",
                )
            else:
                tabs_ok_count += 1

    # If the structure tree is present and /Tabs are set, flag for manual review.
    if result.status != CheckStatus.FAIL:
        result.status = CheckStatus.MANUAL
        result.description = (
            "Structure tree exists; verify reading order visually with a screen reader."
        )
    elif tabs_ok_count > 0:
        # Some pages are fine, some are not — still FAIL but add manual note.
        result.description = (
            "Some pages lack /Tabs /S. Verify reading order with a screen reader."
        )

    return result


# ---------------------------------------------------------------------------
# Check 2.4.6  Headings and Labels
# ---------------------------------------------------------------------------

def _check_246(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="2.4.6",
        name="Headings and Labels",
        level="AA",
        status=CheckStatus.PASS,
        description="Headings and labels describe topic or purpose.",
        wcag_url=_WCAG_URLS["2.4.6"],
    )

    if not _has_struct_tree(pdf):
        # Tagging absence is already reported by 1.3.1; record NA here.
        result.status = CheckStatus.NA
        result.description = "Document has no structure tree; heading check skipped."
        return result

    tags = _collect_tags(pdf)
    heading_tags = [t for t in tags if t in _ALL_HEADING_TAGS]

    if not heading_tags:
        result.add_issue(
            Severity.WARNING,
            (
                "No heading elements (H1–H6) found in structure tree. "
                "Screen reader users cannot navigate by headings."
            ),
        )
        return result

    # Warn about generic /H (no level).
    generic_h_count = sum(1 for t in heading_tags if t == "/H")
    if generic_h_count:
        result.add_issue(
            Severity.WARNING,
            (
                f"{generic_h_count} generic /H heading(s) found with no numeric level. "
                "Use /H1–/H6 instead so screen readers can convey hierarchy."
            ),
            location="Document structure",
        )

    # Check for level skips among /H1–/H6 headings (in document order).
    leveled = [t for t in tags if t in _LEVELED_HEADING_TAGS]

    def _level(tag: str) -> int:
        return int(tag[-1])

    prev_level: int | None = None
    for tag in leveled:
        cur_level = _level(tag)
        if prev_level is not None and cur_level > prev_level + 1:
            result.add_issue(
                Severity.WARNING,
                (
                    f"Heading levels skip from H{prev_level} to H{cur_level} — "
                    "this disrupts navigation for screen reader users."
                ),
                location="Document structure",
            )
        prev_level = cur_level

    # Text-content check is complex (requires MCID/content-stream correlation);
    # flag for manual review instead.
    if result.status == CheckStatus.PASS:
        result.status = CheckStatus.MANUAL
        result.description = (
            "Heading elements are present. "
            "Verify manually that each heading accurately describes the following content."
        )

    return result


# ---------------------------------------------------------------------------
# Check 4.1.1  Parsing / Structure Validity
# ---------------------------------------------------------------------------

def _check_411(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="4.1.1",
        name="Parsing",
        level="A",
        status=CheckStatus.PASS,
        description="PDF structure tree is present and well-formed.",
        wcag_url=_WCAG_URLS["4.1.1"],
    )

    # 1. Basic Root access.
    try:
        root_type = pdf.Root.get("/Type")
        if root_type is None:
            result.add_issue(
                Severity.WARNING,
                "Document /Root has no /Type entry.",
                location="/Root",
            )
    except Exception as exc:
        result.add_issue(
            Severity.ERROR,
            f"Unable to access PDF Root dictionary: {exc}",
            location="/Root",
        )
        return result

    # 2. Use pikepdf's own check() if available.
    if hasattr(pdf, "check"):
        try:
            warnings = pdf.check()
            for w in warnings:
                result.add_issue(
                    Severity.WARNING,
                    f"pikepdf structural warning: {w}",
                )
        except Exception as exc:
            result.add_issue(
                Severity.ERROR,
                f"pikepdf reported a structural error: {exc}",
            )

    # 3. Attempt to iterate all objects to surface duplicate / corrupt entries.
    try:
        seen_objgens: set = set()
        for obj in pdf.objects:
            try:
                og = getattr(obj, "objgen", None)
                if og is not None:
                    if og in seen_objgens:
                        result.add_issue(
                            Severity.ERROR,
                            f"Duplicate object number detected: {og}",
                        )
                    seen_objgens.add(og)
            except Exception:
                pass
    except Exception as exc:
        result.add_issue(
            Severity.WARNING,
            f"Could not iterate PDF object table: {exc}",
        )

    if result.status == CheckStatus.PASS:
        result.description = "PDF structure tree is present and well-formed."

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run all structure-related WCAG 2.1 checks and return their results."""
    return [
        _check_131(pdf),
        _check_132(pdf),
        _check_246(pdf),
        _check_411(pdf),
    ]
