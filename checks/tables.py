"""WCAG 2.1 § 1.3.1 — Info and Relationships: Table structure checks."""
from __future__ import annotations

from typing import Any, List, Optional

import pikepdf

from checks.base import (
    CheckResult,
    CheckStatus,
    Severity,
    get_element_page,
    get_struct_tree_elements,
    try_resolve,
    walk_struct_tree,
)

_WCAG_CRITERION = "1.3.1"
_WCAG_NAME = "Info and Relationships — Tables"
_WCAG_LEVEL = "A"
_WCAG_URL = "https://www.w3.org/TR/WCAG21/#info-and-relationships"

# Valid /Scope values for TH elements (stored as pikepdf.Name objects)
_VALID_SCOPES = {
    pikepdf.Name("/Column"),
    pikepdf.Name("/Row"),
    pikepdf.Name("/Both"),
    pikepdf.Name("/None"),
}


def _make_result(status: CheckStatus, description: str = "") -> CheckResult:
    return CheckResult(
        wcag_criterion=_WCAG_CRITERION,
        name=_WCAG_NAME,
        level=_WCAG_LEVEL,
        status=status,
        description=description,
        wcag_url=_WCAG_URL,
    )


def _collect_children(element: Any, tag: str) -> List[Any]:
    """Return direct /K children of *element* whose /S value matches *tag*."""
    target = pikepdf.Name(tag)
    children: List[Any] = []

    k_val = element.get("/K") if isinstance(element, pikepdf.Dictionary) else None
    if k_val is None:
        return children

    k_val = try_resolve(k_val)

    # /K may be a single child dict or an array of children
    if isinstance(k_val, pikepdf.Dictionary):
        s = try_resolve(k_val.get("/S")) if k_val.get("/S") is not None else None
        if s == target:
            children.append(k_val)
    elif isinstance(k_val, pikepdf.Array):
        for item in k_val:
            item = try_resolve(item)
            if not isinstance(item, pikepdf.Dictionary):
                continue
            s = item.get("/S")
            if s is not None and try_resolve(s) == target:
                children.append(item)

    return children


def _collect_all_descendants(element: Any, tag: str) -> List[Any]:
    """Recursively collect all descendants whose /S matches *tag*."""
    results: List[Any] = []
    target = pikepdf.Name(tag)

    def _visitor(node: Any, _depth: int) -> None:
        if not isinstance(node, pikepdf.Dictionary):
            return
        s = node.get("/S")
        if s is not None and try_resolve(s) == target:
            results.append(node)

    # Walk children only (skip the table root itself)
    k_val = element.get("/K") if isinstance(element, pikepdf.Dictionary) else None
    if k_val is not None:
        walk_struct_tree(try_resolve(k_val), _visitor)

    return results


def _th_has_scope(th_element: pikepdf.Dictionary) -> Optional[pikepdf.Name]:
    """Return the /Scope value if present on *th_element*, else None."""
    attrs = th_element.get("/A")
    if attrs is None:
        return None
    attrs = try_resolve(attrs)

    # /A may be a single attribute dict or an array of attribute dicts
    attr_dicts: List[Any] = []
    if isinstance(attrs, pikepdf.Dictionary):
        attr_dicts = [attrs]
    elif isinstance(attrs, pikepdf.Array):
        attr_dicts = [try_resolve(a) for a in attrs]

    for attr_dict in attr_dicts:
        if not isinstance(attr_dict, pikepdf.Dictionary):
            continue
        scope = attr_dict.get("/Scope")
        if scope is not None:
            return try_resolve(scope)

    return None


def _cell_is_empty(cell: pikepdf.Dictionary) -> bool:
    """Return True when a cell element carries no content (/K is absent or empty)."""
    k_val = cell.get("/K")
    if k_val is None:
        return True
    k_val = try_resolve(k_val)
    if isinstance(k_val, pikepdf.Array) and len(k_val) == 0:
        return True
    return False


def _count_rows_and_cols(table_element: Any) -> tuple[int, int]:
    """
    Estimate the row and column count for a table element.

    Rows are all /TR descendants.  Columns are the maximum number of
    /TH + /TD cells found in any single /TR.
    """
    all_tr = _collect_all_descendants(table_element, "/TR")
    row_count = len(all_tr)

    max_cols = 0
    for tr in all_tr:
        th_count = len(_collect_children(tr, "/TH"))
        td_count = len(_collect_children(tr, "/TD"))
        cols = th_count + td_count
        if cols > max_cols:
            max_cols = cols

    return row_count, max_cols


def _gather_tr_elements(table_element: Any) -> List[Any]:
    """
    Return all /TR elements that are direct children of the table or of any
    row-group (/THead, /TBody, /TFoot) that is a direct child of the table.
    """
    row_group_tags = ("/THead", "/TBody", "/TFoot")
    trs: List[Any] = []

    # Direct /TR children of the table
    trs.extend(_collect_children(table_element, "/TR"))

    # /TR children inside row groups
    for rg_tag in row_group_tags:
        for rg in _collect_children(table_element, rg_tag):
            trs.extend(_collect_children(rg, "/TR"))

    return trs


def _check_table(
    result: CheckResult,
    pdf: pikepdf.Pdf,
    table_idx: int,
    table_element: Any,
) -> None:
    """Run all sub-checks for a single table element."""
    page_num = get_element_page(pdf, table_element)
    page_str = f"page {page_num}" if page_num else "unknown page"
    table_label = f"Table {table_idx + 1} (on {page_str})"

    # ------------------------------------------------------------------
    # (a) No rows
    # ------------------------------------------------------------------
    trs = _gather_tr_elements(table_element)
    if not trs:
        result.add_issue(
            Severity.ERROR,
            f"{table_label} has no row (/TR) elements.",
            location=f"{table_label} — no /TR row elements found",
        )
        # Nothing more to check without rows
        return

    # ------------------------------------------------------------------
    # (b) TH cells missing /Scope  &  (d) unexpected /Scope values
    # ------------------------------------------------------------------
    # Walk each TR in order so we can report row numbers for missing-scope issues.
    reported_empty_cells = False  # only report empty-cell INFO once per table

    all_th_flat: List[Any] = []  # for the no-header-cells check below

    for row_idx, tr in enumerate(trs):
        th_cells_in_row = _collect_children(tr, "/TH")
        all_th_flat.extend(th_cells_in_row)

        for th in th_cells_in_row:
            scope_val = _th_has_scope(th)
            if scope_val is None:
                result.add_issue(
                    Severity.ERROR,
                    (
                        f"{table_label}: TH header cell at row {row_idx + 1} is"
                        " missing /Scope attribute. Screen readers cannot"
                        " associate headers with data cells."
                    ),
                    location=f"{table_label}, header cell (TH) at row {row_idx + 1}",
                    fixable=True,
                )
            elif scope_val not in _VALID_SCOPES:
                result.add_issue(
                    Severity.WARNING,
                    (
                        f"{table_label}: TH header cell at row {row_idx + 1} has"
                        f" unexpected /Scope value '{scope_val}'."
                        " Expected /Column, /Row, /Both, or /None."
                    ),
                    location=f"{table_label}, TH cell",
                )

    # ------------------------------------------------------------------
    # (c) No header cells at all (more than 1 row, zero TH elements)
    # ------------------------------------------------------------------
    if len(all_th_flat) == 0 and len(trs) > 1:
        result.add_issue(
            Severity.WARNING,
            (
                f"{table_label} has no header cells (/TH). Consider marking"
                " header row/column cells as TH with appropriate /Scope."
            ),
            location=f"{table_label} — no header cells found",
        )

    # ------------------------------------------------------------------
    # (e) Empty cells (/TD or /TH with no content)
    # ------------------------------------------------------------------
    all_td = _collect_all_descendants(table_element, "/TD")
    all_cells = all_th_flat + all_td
    for cell in all_cells:
        if _cell_is_empty(cell):
            if not reported_empty_cells:
                result.add_issue(
                    Severity.INFO,
                    (
                        f"{table_label} contains empty cells — verify these are"
                        " intentional."
                    ),
                    location=f"{table_label} — empty cell(s) present",
                )
                reported_empty_cells = True
            break  # one INFO notice per table is enough

    # ------------------------------------------------------------------
    # (f) Caption for large tables
    # ------------------------------------------------------------------
    captions = _collect_children(table_element, "/Caption")
    if not captions:
        row_count, col_count = _count_rows_and_cols(table_element)
        if row_count > 3 and col_count > 3:
            result.add_issue(
                Severity.INFO,
                (
                    f"Large table (>3x3) has no /Caption element — consider"
                    " adding a caption describing the table."
                ),
                location=table_label,
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf: pikepdf.Pdf, pdf_path: str = "") -> List[CheckResult]:
    """Run WCAG 2.1 § 1.3.1 table-structure checks and return results."""

    # --- Untagged document ---------------------------------------------------
    if pdf.Root.get("/StructTreeRoot") is None:
        result = _make_result(
            CheckStatus.FAIL,
            "Document is not tagged — table structure cannot be verified.",
        )
        result.add_issue(
            Severity.ERROR,
            "Document is not tagged — table structure cannot be verified.",
        )
        return [result]

    # --- Find all Table elements ---------------------------------------------
    tables = get_struct_tree_elements(pdf, "/Table")

    if not tables:
        return [
            _make_result(
                CheckStatus.PASS,
                "No table elements found in document structure.",
            )
        ]

    # --- Check each table ----------------------------------------------------
    result = _make_result(CheckStatus.PASS)

    for table_idx, table_element in enumerate(tables):
        _check_table(result, pdf, table_idx, try_resolve(table_element))

    # Status is escalated automatically by add_issue; set description now.
    if result.status == CheckStatus.FAIL:
        issue_count = len(result.issues)
        result.description = (
            f"Found {issue_count} issue(s) across {len(tables)} table(s)."
        )
    else:
        result.description = (
            f"All {len(tables)} table(s) passed structural checks."
        )

    return [result]
