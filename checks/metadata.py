"""
WCAG 2.1 metadata checks for PDF accessibility.

Criteria covered
----------------
2.4.2  Page Titled (A)         — document title present in metadata
3.1.1  Language of Page (A)    — /Lang entry in PDF catalog
3.1.2  Language of Parts (AA)  — /Lang on structure elements where language differs
4.1.1  Parsing (A)             — PDF/UA-1 identifier (pdfuaid:part = "1") in XMP
"""

import re
from typing import List

import pikepdf

from .base import CheckResult, CheckStatus, Issue, Severity

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
DC_NS      = 'http://purl.org/dc/elements/1.1/'
PDFUAID_NS = 'http://www.aiim.org/pdfua/ns/id/'
DC_TITLE   = f'{{{DC_NS}}}title'
PDFUAID_KEY = f'{{{PDFUAID_NS}}}part'

# Minimal BCP-47 tag: at least one primary subtag of 2+ letters/digits,
# optionally followed by more subtags separated by hyphens.
_BCP47_RE = re.compile(r'^[A-Za-z]{2,}(?:-[A-Za-z0-9]+)*$')


def _make_result(wcag_criterion: str, name: str, level: str,
                 criterion_id: str) -> CheckResult:
    return CheckResult(
        wcag_criterion=wcag_criterion,
        name=name,
        level=level,
        status=CheckStatus.PASS,
        wcag_url=f'https://www.w3.org/TR/WCAG21/#{criterion_id}',
    )


# ---------------------------------------------------------------------------
# 2.4.2  Page Titled
# ---------------------------------------------------------------------------

def _check_page_titled(pdf: pikepdf.Pdf) -> CheckResult:
    result = _make_result(
        wcag_criterion='2.4.2',
        name='Page Titled',
        level='A',
        criterion_id='page-titled',
    )
    result.description = (
        'The PDF must have a document title set in its metadata '
        '(docinfo /Title and/or XMP dc:title).'
    )

    title_docinfo = None
    title_xmp = None

    # Check docinfo /Title
    try:
        raw = pdf.docinfo.get('/Title')
        if raw is not None:
            title_docinfo = str(raw).strip()
    except Exception:
        pass

    # Check XMP dc:title
    try:
        with pdf.open_metadata() as meta:
            raw_xmp = meta.get(DC_TITLE)
            if raw_xmp is not None:
                title_xmp = str(raw_xmp).strip()
    except Exception:
        pass

    has_title = bool(title_docinfo) or bool(title_xmp)

    if not has_title:
        result.add_issue(
            severity=Severity.ERROR,
            message=(
                'Document title is missing or empty. '
                'Neither docinfo /Title nor XMP dc:title is set.'
            ),
            location='PDF document metadata (/Info /Title and XMP dc:title both absent)',
            fixable=True,
        )
    elif title_docinfo and not title_xmp:
        result.add_issue(
            severity=Severity.WARNING,
            message=(
                'Document title is present in docinfo /Title but absent from XMP. '
                'PDF/UA requires the title to be declared in XMP dc:title.'
            ),
            location='XMP metadata (dc:title missing; /Info /Title present)',
            fixable=True,
        )
    return result


# ---------------------------------------------------------------------------
# 3.1.1  Language of Page
# ---------------------------------------------------------------------------

def _check_language_of_page(pdf: pikepdf.Pdf) -> CheckResult:
    result = _make_result(
        wcag_criterion='3.1.1',
        name='Language of Page',
        level='A',
        criterion_id='language-of-page',
    )
    result.description = (
        'The PDF catalog must have a /Lang entry containing a valid '
        'BCP-47 language tag (e.g. "en-US", "fr", "zh-Hans").'
    )

    lang = None
    try:
        raw = pdf.Root.get('/Lang')
        if raw is not None:
            lang = str(raw).strip()
    except Exception:
        pass

    if not lang:
        result.add_issue(
            severity=Severity.ERROR,
            message='PDF catalog /Lang entry is missing or empty.',
            location='PDF document catalog (/Lang entry missing)',
            fixable=True,
        )
        return result

    if len(lang) < 2 or not _BCP47_RE.match(lang):
        result.add_issue(
            severity=Severity.WARNING,
            message=(
                f'PDF catalog /Lang value {lang!r} does not look like a valid '
                'BCP-47 language tag. Expected format: "en", "en-US", "fr-CA", etc.'
            ),
            location=f"PDF document catalog (/Lang = '{lang}' — invalid BCP-47 tag)",
            fixable=True,
        )

    return result


# ---------------------------------------------------------------------------
# 3.1.2  Language of Parts
# ---------------------------------------------------------------------------

def _walk_struct_for_lang(node, langs_found: list, visited: set) -> None:
    """Recursively walk the structure tree; collect any /Lang values found."""
    try:
        node = node.get_object()
    except Exception:
        pass

    if not isinstance(node, pikepdf.Dictionary):
        return

    obj_id = id(node)
    if obj_id in visited:
        return
    visited.add(obj_id)

    lang_val = node.get('/Lang')
    if lang_val is not None:
        langs_found.append(str(lang_val).strip())

    kids = node.get('/K')
    if kids is None:
        return
    if not isinstance(kids, pikepdf.Array):
        kids = [kids]
    for kid in kids:
        _walk_struct_for_lang(kid, langs_found, visited)


def _check_language_of_parts(pdf: pikepdf.Pdf) -> CheckResult:
    result = _make_result(
        wcag_criterion='3.1.2',
        name='Language of Parts',
        level='AA',
        criterion_id='language-of-parts',
    )
    result.description = (
        'Structure elements whose language differs from the document default '
        'must carry a /Lang attribute. Automated verification is not possible; '
        'manual review is required.'
    )

    langs_on_elements: list = []
    try:
        struct_root = pdf.Root.get('/StructTreeRoot')
        if struct_root is not None:
            _walk_struct_for_lang(struct_root, langs_on_elements, set())
    except Exception:
        pass

    if not langs_on_elements:
        # No /Lang found on any structure element — cannot confirm or deny
        # compliance; a human must review.
        result.status = CheckStatus.MANUAL
        result.add_issue(
            severity=Severity.INFO,
            message=(
                'No /Lang attribute found on any structure element. '
                'If the document contains passages in a language other than '
                'the catalog default, those elements must be tagged with /Lang. '
                'Manual review required.'
            ),
            location='Structure tree (no per-element /Lang attributes found)',
        )
    # If /Lang entries are present we record them informatively but cannot
    # programmatically verify that *every* language-change span is tagged.
    # Leave status as PASS with an informational note.
    else:
        unique = sorted(set(langs_on_elements))
        result.add_issue(
            severity=Severity.INFO,
            message=(
                f'Found /Lang on {len(langs_on_elements)} structure element(s): '
                f'{unique}. Manual review is still recommended to confirm all '
                'language-change passages are tagged.'
            ),
        )

    return result


# ---------------------------------------------------------------------------
# 4.1.1  Parsing / PDF/UA identifier
# ---------------------------------------------------------------------------

def _check_pdfua_identifier(pdf: pikepdf.Pdf) -> CheckResult:
    result = _make_result(
        wcag_criterion='4.1.1',
        name='Parsing (PDF/UA identifier)',
        level='A',
        criterion_id='parsing',
    )
    result.description = (
        'XMP metadata must declare PDF/UA-1 compliance via '
        'pdfuaid:part = "1" in the http://www.aiim.org/pdfua/ns/id/ namespace.'
    )

    value = None
    try:
        with pdf.open_metadata() as meta:
            value = meta.get(PDFUAID_KEY)
    except Exception:
        pass

    if value is None:
        result.add_issue(
            severity=Severity.ERROR,
            message=(
                'PDF/UA-1 identifier missing or incorrect. '
                f'pdfuaid:part = {value!r} (expected "1").'
            ),
            location='XMP metadata packet (pdfuaid:part not set)',
            fixable=True,
        )
    elif value != '1':
        result.add_issue(
            severity=Severity.ERROR,
            message=(
                'PDF/UA-1 identifier missing or incorrect. '
                f'pdfuaid:part = {value!r} (expected "1").'
            ),
            location=f"XMP metadata (pdfuaid:part = '{value}', expected '1')",
            fixable=True,
        )

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = '') -> List[CheckResult]:
    """
    Run all metadata-related WCAG 2.1 checks against *pdf*.

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
        _check_page_titled(pdf),
        _check_language_of_page(pdf),
        _check_language_of_parts(pdf),
        _check_pdfua_identifier(pdf),
    ]
