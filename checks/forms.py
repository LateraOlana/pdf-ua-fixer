"""WCAG 2.1 form-related accessibility checks.

Checks implemented
------------------
4.1.2  Name, Role, Value               (Level A)
3.3.2  Labels or Instructions          (Level A)
2.4.3  Focus Order                     (Level A)
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

import pikepdf

from checks.base import (
    CheckResult,
    CheckStatus,
    Severity,
    try_resolve,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIELD_TYPE_NAMES = {
    "/Tx": "text",
    "/Btn": "button/checkbox/radio",
    "/Ch": "choice",
    "/Sig": "signature",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str_val(obj: object) -> str:
    """Convert a pikepdf String / Name to a plain Python str, or return ''."""
    if obj is None:
        return ""
    try:
        return str(obj)
    except Exception:
        return ""


def _collect_fields(fields_array: Any) -> List[pikepdf.Dictionary]:
    """Recursively expand the /Fields array, following /Kids for field groups.

    Returns a flat list of leaf (or named) field dictionaries.
    """
    result: List[pikepdf.Dictionary] = []

    if fields_array is None:
        return result

    fields_array = try_resolve(fields_array)
    if not isinstance(fields_array, pikepdf.Array):
        return result

    for field_ref in fields_array:
        field = try_resolve(field_ref)
        if not isinstance(field, pikepdf.Dictionary):
            continue

        kids = field.get("/Kids")
        if kids is not None:
            # Check whether kids are widget annotations or child fields.
            # Child fields have a /T entry; widget annotations have /Subtype=/Widget.
            kids_resolved = try_resolve(kids)
            child_fields: List[Any] = []
            if isinstance(kids_resolved, pikepdf.Array):
                for kid_ref in kids_resolved:
                    kid = try_resolve(kid_ref)
                    if not isinstance(kid, pikepdf.Dictionary):
                        continue
                    subtype = try_resolve(kid.get("/Subtype"))
                    has_t = kid.get("/T") is not None
                    # It's a child field if it has /T, or if it doesn't look
                    # like a pure widget annotation.
                    if has_t or subtype != pikepdf.Name("/Widget"):
                        child_fields.append(kid_ref)

            if child_fields:
                # Recurse into child fields
                fake_array = pikepdf.Array(child_fields)
                result.extend(_collect_fields(fake_array))
                continue

        # Leaf field — include it
        result.append(field)

    return result


def _field_name(field: pikepdf.Dictionary) -> str:
    """Return the /T (partial) name of the field, or '<unnamed>'."""
    t_raw = field.get("/T")
    if t_raw is None:
        return "<unnamed>"
    return _str_val(try_resolve(t_raw))


def _field_page(pdf: pikepdf.Pdf, field: pikepdf.Dictionary) -> Optional[int]:
    """Find page number (1-based) of a form field's first widget annotation."""
    try:
        # Field may itself be a widget, or have /Kids that are widgets
        widgets = []
        ft = field.get("/FT")
        if ft:  # it's a terminal field
            widgets = [field]
        kids = try_resolve(field.get("/Kids"))
        if kids and isinstance(kids, pikepdf.Array):
            for kid in kids:
                kid = try_resolve(kid)
                if isinstance(kid, pikepdf.Dictionary) and kid.get("/Subtype") == pikepdf.Name("/Widget"):
                    widgets.append(kid)
        for widget in widgets:
            pg = try_resolve(widget.get("/P"))  # /P = page reference on widget
            if pg:
                for i, page in enumerate(pdf.pages):
                    try:
                        if page.objgen == pg.objgen:
                            return i + 1
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def _pages_with_form_fields(pdf: pikepdf.Pdf) -> List[Tuple[int, bool]]:
    """Return (page_index, has_widget) pairs for pages that contain widgets.

    Also returns the /Tabs value for each such page.
    """
    pages: List[Tuple[int, bool]] = []
    for page_idx, page in enumerate(pdf.pages):
        annots = try_resolve(page.get("/Annots"))
        if annots is None:
            continue
        has_widget = False
        if isinstance(annots, pikepdf.Array):
            for annot_ref in annots:
                annot = try_resolve(annot_ref)
                if not isinstance(annot, pikepdf.Dictionary):
                    continue
                subtype = try_resolve(annot.get("/Subtype"))
                if subtype == pikepdf.Name("/Widget"):
                    has_widget = True
                    break
        if has_widget:
            pages.append((page_idx, True))
    return pages


# ---------------------------------------------------------------------------
# Check 4.1.2 – Name, Role, Value
# ---------------------------------------------------------------------------

def _check_name_role_value(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="4.1.2",
        name="Name, Role, Value",
        level="A",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#name-role-value",
    )

    acroform = try_resolve(pdf.Root.get("/AcroForm"))
    if acroform is None:
        result.status = CheckStatus.NA
        result.description = "No form fields found."
        return result

    fields_array = acroform.get("/Fields") if isinstance(acroform, pikepdf.Dictionary) else None
    fields = _collect_fields(fields_array)

    if not fields:
        result.status = CheckStatus.NA
        result.description = "No form fields found."
        return result

    total = len(fields)
    fields_with_tu = 0
    fields_without_tu = 0

    for field in fields:
        t_raw = field.get("/T")
        ft_raw = try_resolve(field.get("/FT"))
        tu_raw = field.get("/TU")
        name = _field_name(field)
        page_num = _field_page(pdf, field)

        # --- /T missing: field is unidentifiable ---------------------
        if t_raw is None:
            location = f"Form field on page {page_num or 'unknown'} (unnamed field)"
            result.add_issue(
                Severity.ERROR,
                "Form field has no name (/T). Screen readers cannot identify this field.",
                location=location,
                fixable=False,
            )

        # --- /TU (tooltip / accessible label) ------------------------
        if tu_raw is None:
            fields_without_tu += 1
            location = f"Page {page_num or '?'} — field: '{name}'"
            result.add_issue(
                Severity.WARNING,
                f"Form field '{name}' has no tooltip (/TU). The accessible name "
                "will fall back to /T which may not be descriptive. "
                "Add a human-readable tooltip.",
                location=location,
                fixable=False,
            )
        else:
            fields_with_tu += 1

        # --- Type-specific checks ------------------------------------
        ft_str = _str_val(ft_raw) if ft_raw is not None else ""
        if not ft_str.startswith("/"):
            ft_str = f"/{ft_str}" if ft_str else ""

        if ft_str == "/Btn":
            # For buttons the /V should be a Name (/Yes, /Off, etc.)
            v_raw = try_resolve(field.get("/V"))
            if v_raw is not None and not isinstance(v_raw, pikepdf.Name):
                result.add_issue(
                    Severity.WARNING,
                    f"Button/checkbox field '{name}' has a /V value that is not "
                    "a PDF Name. Expected something like /Yes or /Off.",
                    location=f"Page {page_num or '?'} — field: '{name}'",
                    fixable=False,
                )

        elif ft_str == "/Tx":
            # For text fields, very short MaxLen may be unintentional
            maxlen_raw = field.get("/MaxLen")
            if maxlen_raw is not None:
                try:
                    maxlen = int(maxlen_raw)
                    if maxlen < 5:
                        result.add_issue(
                            Severity.INFO,
                            f"Text field '{name}' has very short MaxLen ({maxlen}). "
                            "Verify this is intentional.",
                            location=f"Page {page_num or '?'} — field: '{name}'",
                            fixable=False,
                        )
                except (TypeError, ValueError):
                    pass

    if result.status == CheckStatus.PASS:
        result.description = (
            f"Checked {total} field(s): {fields_with_tu} have /TU tooltip, "
            f"{fields_without_tu} do not."
        )
    else:
        result.description = (
            f"Checked {total} field(s): {fields_with_tu} have /TU tooltip, "
            f"{fields_without_tu} do not. Review issues above."
        )

    return result


# ---------------------------------------------------------------------------
# Check 3.3.2 – Labels or Instructions
# ---------------------------------------------------------------------------

def _check_labels_or_instructions(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="3.3.2",
        name="Labels or Instructions",
        level="A",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#labels-or-instructions",
    )

    acroform = try_resolve(pdf.Root.get("/AcroForm"))
    if acroform is None:
        result.status = CheckStatus.NA
        result.description = "No form fields found."
        return result

    fields_array = acroform.get("/Fields") if isinstance(acroform, pikepdf.Dictionary) else None
    fields = _collect_fields(fields_array)

    if not fields:
        result.status = CheckStatus.NA
        result.description = "No form fields found."
        return result

    total = len(fields)
    without_tu = sum(1 for f in fields if f.get("/TU") is None)

    # If document has a structure tree, label association may be via tagging —
    # automated verification is not fully reliable; flag for manual review.
    has_struct_tree = pdf.Root.get("/StructTreeRoot") is not None

    if without_tu == 0:
        result.description = (
            f"All {total} field(s) have /TU tooltips providing accessible labels."
        )
        if has_struct_tree:
            result.add_issue(
                Severity.INFO,
                "Document has a structure tree. Confirm that form field labels "
                "in the tag tree correctly associate visible text with each field.",
                location=None,
                fixable=False,
            )
            # INFO does not escalate to FAIL; restore PASS if it was changed.
            if result.status == CheckStatus.FAIL:
                result.status = CheckStatus.PASS
        return result

    ratio_without = without_tu / total

    if ratio_without > 0.5:
        result.add_issue(
            Severity.ERROR,
            f"Majority of form fields lack accessible labels (/TU tooltip): "
            f"{without_tu} of {total} field(s) have no /TU. "
            "Users of assistive technology cannot identify field purpose.",
            location=None,
            fixable=False,
        )
    else:
        result.add_issue(
            Severity.WARNING,
            f"{without_tu} of {total} field(s) have no /TU tooltip. "
            "Each form field should have a descriptive accessible label.",
            location=None,
            fixable=False,
        )

    if has_struct_tree:
        result.add_issue(
            Severity.INFO,
            "Document has a structure tree. Confirm that visible label text in "
            "the tag tree is programmatically associated with each unlabelled field.",
            location=None,
            fixable=False,
        )

    result.description = (
        f"Checked {total} field(s): {without_tu} lack /TU tooltips."
    )
    return result


# ---------------------------------------------------------------------------
# Check 2.4.3 – Focus Order
# ---------------------------------------------------------------------------

def _check_focus_order(pdf: pikepdf.Pdf) -> CheckResult:
    result = CheckResult(
        wcag_criterion="2.4.3",
        name="Focus Order",
        level="A",
        status=CheckStatus.PASS,
        wcag_url="https://www.w3.org/TR/WCAG21/#focus-order",
    )

    pages_with_widgets = _pages_with_form_fields(pdf)

    if not pages_with_widgets:
        result.status = CheckStatus.NA
        result.description = "No form fields found; focus order check not applicable."
        return result

    for page_idx, _ in pages_with_widgets:
        page = pdf.pages[page_idx]
        tabs_raw = try_resolve(page.get("/Tabs"))
        page_label = f"Page {page_idx + 1}"

        if tabs_raw is None:
            result.add_issue(
                Severity.WARNING,
                f"Page {page_idx + 1} has form fields but no /Tabs entry. "
                "Tab order defaults to annotation array order which may be illogical.",
                location=page_label,
                fixable=False,
            )
            continue

        tabs_str = _str_val(tabs_raw)
        if not tabs_str.startswith("/"):
            tabs_str = f"/{tabs_str}"

        if tabs_str == "/S":
            # Structure order — logical; no issue.
            pass
        elif tabs_str == "/A":
            result.add_issue(
                Severity.INFO,
                f"Page {page_idx + 1} uses annotation array order for tab order (/Tabs /A). "
                "Verify this matches visual/logical order.",
                location=page_label,
                fixable=False,
            )
            # INFO does not escalate to FAIL; keep PASS unless already FAIL.
            if result.status == CheckStatus.FAIL:
                pass  # already escalated by a WARNING elsewhere; leave it
        else:
            result.add_issue(
                Severity.INFO,
                f"Page {page_idx + 1} has /Tabs value '{tabs_str}'. "
                "Verify the tab order is logical for keyboard navigation.",
                location=page_label,
                fixable=False,
            )

    if result.status == CheckStatus.PASS:
        result.description = (
            f"Checked {len(pages_with_widgets)} page(s) with form fields. "
            "Tab order entries are present and set to structure order (/S) "
            "or were not flagged as problematic."
        )

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run all form-related WCAG 2.1 checks and return their results."""
    return [
        _check_name_role_value(pdf),
        _check_labels_or_instructions(pdf),
        _check_focus_order(pdf),
    ]
