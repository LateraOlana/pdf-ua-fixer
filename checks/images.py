"""
WCAG 2.1 image-related checks for PDF accessibility.

Criteria covered
----------------
1.1.1  Non-text Content (A)    — all images must have alternative text
1.4.5  Images of Text (AA)     — images must not be used where real text suffices
"""

from typing import List, Optional

import pikepdf

from .base import (
    CheckResult,
    CheckStatus,
    Severity,
    get_element_page,
    get_struct_tree_elements,
    try_resolve,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_result(
    wcag_criterion: str,
    name: str,
    level: str,
    criterion_id: str,
) -> CheckResult:
    return CheckResult(
        wcag_criterion=wcag_criterion,
        name=name,
        level=level,
        status=CheckStatus.PASS,
        wcag_url=f"https://www.w3.org/TR/WCAG21/#{criterion_id}",
    )


def _count_image_xobjects(pdf: pikepdf.Pdf) -> int:
    """Return the total number of /Image XObjects referenced across all pages."""
    total = 0
    for page in pdf.pages:
        try:
            resources = page.get("/Resources")
            if resources is None:
                continue
            resources = try_resolve(resources)
            xobjects = resources.get("/XObject")
            if xobjects is None:
                continue
            xobjects = try_resolve(xobjects)
            if not isinstance(xobjects, pikepdf.Dictionary):
                continue
            for _name, xobj in xobjects.items():
                xobj = try_resolve(xobj)
                if not isinstance(xobj, pikepdf.Dictionary):
                    continue
                subtype = xobj.get("/Subtype")
                if subtype is not None and str(try_resolve(subtype)) == "/Image":
                    total += 1
        except Exception:
            continue
    return total


def _image_xobjects_by_page(pdf: pikepdf.Pdf) -> List[int]:
    """Return a list with the image-XObject count per page (0-indexed)."""
    counts: List[int] = []
    for page in pdf.pages:
        count = 0
        try:
            resources = page.get("/Resources")
            if resources is not None:
                resources = try_resolve(resources)
                xobjects = resources.get("/XObject")
                if xobjects is not None:
                    xobjects = try_resolve(xobjects)
                    if isinstance(xobjects, pikepdf.Dictionary):
                        for _name, xobj in xobjects.items():
                            xobj = try_resolve(xobj)
                            if not isinstance(xobj, pikepdf.Dictionary):
                                continue
                            subtype = xobj.get("/Subtype")
                            if subtype is not None and str(try_resolve(subtype)) == "/Image":
                                count += 1
        except Exception:
            pass
        counts.append(count)
    return counts


def _xobject_names_by_page(pdf: pikepdf.Pdf) -> List[List[str]]:
    """Return a list-of-lists of image XObject names, one inner list per page."""
    result: List[List[str]] = []
    for page in pdf.pages:
        names: List[str] = []
        try:
            resources = page.get("/Resources")
            if resources is not None:
                resources = try_resolve(resources)
                xobjects = resources.get("/XObject")
                if xobjects is not None:
                    xobjects = try_resolve(xobjects)
                    if isinstance(xobjects, pikepdf.Dictionary):
                        for name, xobj in xobjects.items():
                            xobj = try_resolve(xobj)
                            if not isinstance(xobj, pikepdf.Dictionary):
                                continue
                            subtype = xobj.get("/Subtype")
                            if subtype is not None and str(try_resolve(subtype)) == "/Image":
                                names.append(str(name))
        except Exception:
            pass
        result.append(names)
    return result


# ---------------------------------------------------------------------------
# 1.1.1  Non-text Content (A)
# ---------------------------------------------------------------------------

def _check_non_text_content(pdf: pikepdf.Pdf) -> CheckResult:
    result = _make_result(
        wcag_criterion="1.1.1",
        name="Non-text Content",
        level="A",
        criterion_id="non-text-content",
    )
    result.description = (
        "All non-text content presented to the user must have a text alternative "
        "that serves the equivalent purpose. For PDF images, each Figure structure "
        "element must carry an /Alt attribute with a meaningful description."
    )

    has_struct_tree = pdf.Root.get("/StructTreeRoot") is not None

    # --- Branch 1: untagged document -----------------------------------------
    if not has_struct_tree:
        xobj_names_by_page = _xobject_names_by_page(pdf)
        for page_idx, names in enumerate(xobj_names_by_page):
            for xobj_name in names:
                result.add_issue(
                    severity=Severity.ERROR,
                    message=(
                        f"Image found on page {page_idx + 1} but document is "
                        "untagged — no alt text possible. Tag the PDF and add "
                        "/Alt text to Figure elements."
                    ),
                    location=f"Image XObject '{xobj_name}' on page {page_idx + 1}",
                    fixable=False,
                )
        return result

    # --- Branch 2: tagged document -------------------------------------------
    figures = get_struct_tree_elements(pdf, "/Figure")
    total_figures = len(figures)

    for idx, figure in enumerate(figures):
        page_num: Optional[int] = get_element_page(pdf, figure)
        if page_num is not None:
            loc = f"Figure {idx + 1} of {total_figures} (page {page_num})"
        else:
            loc = f"Figure {idx + 1} of {total_figures} (structure tree)"

        alt = figure.get("/Alt")

        if alt is None:
            # Missing /Alt entirely
            result.add_issue(
                severity=Severity.ERROR,
                message=(
                    "Figure element has no /Alt text (alternative text). "
                    "Screen readers will announce it as 'unlabeled image'."
                ),
                location=loc,
                fixable=True,
            )
        else:
            alt_str = str(alt)
            if alt_str == "" or alt_str.strip() == "":
                # Empty /Alt — treat as intentionally decorative
                result.add_issue(
                    severity=Severity.INFO,
                    message="Figure marked as decorative (empty /Alt).",
                    location=loc,
                    fixable=False,
                )

    # --- Orphaned-image check ------------------------------------------------
    total_images = _count_image_xobjects(pdf)

    if total_images > total_figures:
        result.add_issue(
            severity=Severity.WARNING,
            message=(
                f"Found {total_images} image XObject(s) but only "
                f"{total_figures} Figure element(s) in structure tree. "
                "Some images may be untagged."
            ),
            location="Multiple pages (see XObject count vs. Figure count)",
            fixable=False,
        )

    return result


# ---------------------------------------------------------------------------
# 1.4.5  Images of Text (AA)
# ---------------------------------------------------------------------------

def _check_images_of_text(pdf: pikepdf.Pdf) -> CheckResult:
    result = _make_result(
        wcag_criterion="1.4.5",
        name="Images of Text",
        level="AA",
        criterion_id="images-of-text",
    )
    result.description = (
        "If technologies can achieve the same visual presentation, text must be "
        "used to convey information rather than images of text. This check cannot "
        "be fully automated and requires manual review."
    )

    # This criterion cannot be fully automated; always set MANUAL.
    result.status = CheckStatus.MANUAL

    n_images = _count_image_xobjects(pdf)
    n_pages = len(pdf.pages)

    result.add_issue(
        severity=Severity.INFO,
        message=(
            "Check whether any images contain text that could be presented as "
            "real text instead. Scanned documents or images of tables/charts with "
            "text labels may fail this criterion."
        ),
    )
    result.add_issue(
        severity=Severity.INFO,
        message=(
            f"Found {n_images} image(s) in this document. Review each to "
            "ensure no image contains text that could be represented as live text."
        ),
        location=f"Document ({n_images} image(s) found across {n_pages} pages)",
    )

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """
    Run all image-related WCAG 2.1 checks against *pdf*.

    Parameters
    ----------
    pdf:
        An open pikepdf.Pdf instance.
    pdf_path:
        Filesystem path to the PDF (currently unused; reserved for future
        per-file diagnostics).

    Returns
    -------
    List of CheckResult objects, one per criterion checked.
    """
    return [
        _check_non_text_content(pdf),
        _check_images_of_text(pdf),
    ]
