"""Shared types and helpers used by all checker modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional

import pikepdf


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class CheckStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL = "MANUAL"  # Requires human review
    NA = "NA"          # Not applicable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    """A single problem found during a WCAG criterion check."""

    wcag_criterion: str                  # e.g. "1.1.1"
    severity: Severity
    message: str
    location: Optional[str] = None       # e.g. "Page 3", "Figure on page 5"
    fixable: bool = False
    fix_applied: bool = False


@dataclass
class CheckResult:
    """Aggregated result for one WCAG success criterion."""

    wcag_criterion: str                  # e.g. "1.1.1"
    name: str                            # e.g. "Non-text Content"
    level: str                           # "A" or "AA"
    status: CheckStatus
    issues: List[Issue] = field(default_factory=list)
    description: str = ""
    wcag_url: str = ""                   # Full URL to criterion on w3.org

    def add_issue(
        self,
        severity: Severity,
        message: str,
        location: Optional[str] = None,
        fixable: bool = False,
    ) -> None:
        """Append an Issue and escalate status to FAIL for ERROR or WARNING."""
        self.issues.append(
            Issue(
                wcag_criterion=self.wcag_criterion,
                severity=severity,
                message=message,
                location=location,
                fixable=fixable,
            )
        )
        if severity in (Severity.ERROR, Severity.WARNING):
            self.status = CheckStatus.FAIL

    def summary_line(self) -> str:
        """Return a one-line summary, e.g. '[PASS] 1.1.1 Non-text Content (A)'."""
        return f"[{self.status.value}] {self.wcag_criterion} {self.name} ({self.level})"


# ---------------------------------------------------------------------------
# pikepdf helpers
# ---------------------------------------------------------------------------

def try_resolve(obj: Any) -> Any:
    """Safely dereference a pikepdf indirect object.

    Dictionary-key access in pikepdf auto-resolves indirect references, but
    array items and some dictionary values may still be indirect.  Calling
    ``get_object()`` on a concrete type raises ``ValueError`` (pikepdf
    ``__getattr__`` intercepts it as a key lookup), so both ``ValueError`` and
    ``AttributeError`` are caught and the original object is returned as-is.
    """
    try:
        return obj.get_object()
    except (AttributeError, ValueError):
        return obj


def get_element_page(pdf: pikepdf.Pdf, element: Any) -> Optional[int]:
    """Return the 1-based page number for a structure-tree element.

    Structure elements carry a ``/Pg`` indirect reference to their page.
    We resolve it and compare ``objgen`` against ``pdf.pages`` to find the
    index.  Returns ``None`` if the page cannot be determined.
    """
    try:
        pg = element.get("/Pg")
        if pg is None:
            return None
        pg = try_resolve(pg)
        for i, page in enumerate(pdf.pages):
            try:
                if page.objgen == pg.objgen:
                    return i + 1
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_struct_tree_elements(
    pdf: pikepdf.Pdf,
    tag_name: str,
) -> List[pikepdf.Dictionary]:
    """Return every structure-tree element whose /S value matches *tag_name*.

    *tag_name* should include the leading slash, e.g. ``"/Figure"``,
    ``"/H1"``, ``"/TH"``.

    The function walks the entire ``/StructTreeRoot`` recursively and collects
    all ``Dictionary`` nodes whose ``/S`` entry matches the requested tag.
    Returns an empty list when the document has no structure tree or no
    elements with the requested tag are found.
    """
    results: List[pikepdf.Dictionary] = []

    root = pdf.Root.get("/StructTreeRoot")
    if root is None:
        return results

    target = pikepdf.Name(tag_name)

    def _visitor(element: Any, _depth: int) -> None:
        if not isinstance(element, pikepdf.Dictionary):
            return
        s_val = element.get("/S")
        if s_val is not None and try_resolve(s_val) == target:
            results.append(element)

    walk_struct_tree(try_resolve(root), _visitor)
    return results


def walk_struct_tree(
    node: Any,
    visitor_fn: Callable[[Any, int], None],
    depth: int = 0,
) -> None:
    """Recursively walk the PDF structure tree, calling *visitor_fn* at every node.

    *visitor_fn* receives ``(element, depth)`` for each visited node.

    The traversal follows:
    - ``/K`` arrays or single-element ``/K`` values within ``Dictionary`` nodes
    - ``pikepdf.Array`` nodes whose items are ``Dictionary`` children

    Indirect references are resolved before each visit so callers always
    receive concrete objects.
    """
    if node is None:
        return

    node = try_resolve(node)

    if isinstance(node, pikepdf.Dictionary):
        visitor_fn(node, depth)
        k_val = node.get("/K")
        if k_val is not None:
            walk_struct_tree(try_resolve(k_val), visitor_fn, depth + 1)

    elif isinstance(node, pikepdf.Array):
        for item in node:
            walk_struct_tree(try_resolve(item), visitor_fn, depth)
