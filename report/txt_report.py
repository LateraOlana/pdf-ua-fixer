"""
Plain-text PDF accessibility report generator.

Produces an 80-column formatted report grouped by WCAG 2.1 principle with a
summary, per-check details, manual-review items, and a list of auto-fixed
issues.
"""
from checks.base import CheckResult, CheckStatus, Severity, Issue
from typing import List
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIDTH = 80
BAR_WIDTH = 20  # characters used for the progress bar in the summary

PRINCIPLES = {
    1: "PERCEIVABLE",
    2: "OPERABLE",
    3: "UNDERSTANDABLE",
    4: "ROBUST",
}

# Map CheckStatus to the 4-char tag shown in brackets, e.g. [PASS]
STATUS_TAG = {
    CheckStatus.PASS:   "PASS",
    CheckStatus.FAIL:   "FAIL",
    CheckStatus.MANUAL: "MNUL",
    CheckStatus.NA:     "N/A ",
}

# Human-readable labels for the summary table
STATUS_LABEL = {
    CheckStatus.PASS:   "PASSED",
    CheckStatus.FAIL:   "FAILED",
    CheckStatus.MANUAL: "NEEDS REVIEW",
    CheckStatus.NA:     "NOT APPLICABLE",
}

SEVERITY_LABEL = {
    Severity.ERROR:   "ERROR",
    Severity.WARNING: "WARNING",
    Severity.INFO:    "INFO",
}

_MANUAL_FIX_GUIDANCE = {
    "1.1.1":  "Add meaningful alt text to every image in your authoring tool (Word, InDesign, LaTeX \\includegraphics[alt={...}]).",
    "1.3.1":  "Re-author the PDF with proper tagging: use a tagged PDF workflow (LaTeX tagpdf, Adobe Acrobat, or Word).",
    "1.3.2":  "Re-author the PDF ensuring the structure tree reading order matches the visual order.",
    "1.4.3":  "Change text or background colours in the source document to achieve >= 4.5:1 contrast (https://webaim.org/resources/contrastchecker/).",
    "1.4.5":  "Replace images of text with real searchable text in the source document.",
    "1.4.11": "Ensure form field borders and UI components have >= 3:1 contrast against adjacent colours.",
    "2.4.1":  "Add PDF bookmarks (Outlines) via your authoring tool or with Adobe Acrobat's Bookmarks panel.",
    "2.4.4":  "Replace vague link text ('click here', 'read more') with descriptive text in the source document.",
    "2.4.5":  "Add a Table of Contents or bookmarks so users have multiple ways to navigate the document.",
    "2.4.6":  "Ensure headings are tagged (H1-H6) in proper hierarchical order in the structure tree.",
    "3.1.2":  "Tag passages in a different language with the correct /Lang attribute in your authoring tool.",
}


# ---------------------------------------------------------------------------
# Low-level formatting helpers
# ---------------------------------------------------------------------------

def _rule(char: str = "=") -> str:
    """Return a full-width horizontal rule using *char*."""
    return char * WIDTH


def _section(title: str) -> str:
    """Return a top-level section header (double rule above and below)."""
    return f"{_rule()}\n{title}\n{_rule()}"


def _subsection(title: str) -> str:
    """Return a second-level section header (single dash rule)."""
    return f"{title}\n{'-' * len(title)}"


def _wrap(text: str, indent: int, first_indent: int | None = None) -> str:
    """
    Word-wrap *text* to WIDTH characters with a hanging indent of *indent*
    spaces.  The first line uses *first_indent* (defaults to *indent*).
    """
    if first_indent is None:
        first_indent = indent

    words = text.split()
    if not words:
        return ""

    lines: list[str] = []
    current = " " * first_indent
    first = True

    for word in words:
        prefix = " " * (first_indent if first else indent)
        candidate = (current + " " + word) if not first else (current + word)
        if len(candidate) <= WIDTH:
            current = candidate
        else:
            if not first:
                lines.append(current)
            current = prefix + word
        first = False

    if current.strip():
        lines.append(current)

    return "\n".join(lines)


def _bar(count: int, total: int) -> str:
    """
    Return a Unicode block-character progress bar of BAR_WIDTH columns.
    Filled portion uses U+2588 FULL BLOCK (█); empty uses U+2591 LIGHT SHADE (░).
    """
    if total == 0:
        filled = 0
    else:
        filled = round(BAR_WIDTH * count / total)
    return "█" * filled + "░" * (BAR_WIDTH - filled)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_header(pdf_path: str, results: List[CheckResult]) -> str:
    filename = Path(pdf_path).name
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)

    lines = [
        _rule(),
        "PDF ACCESSIBILITY REPORT — WCAG 2.1 Level AA",
        _rule(),
        f"File:    {filename}",
        f"Date:    {date_str}",
        f"Checks:  {total} criteria evaluated",
    ]
    return "\n".join(lines)


def _build_summary(results: List[CheckResult]) -> str:
    total = len(results)
    counts = {s: 0 for s in CheckStatus}
    for r in results:
        counts[r.status] += 1

    order = [
        CheckStatus.PASS,
        CheckStatus.FAIL,
        CheckStatus.MANUAL,
        CheckStatus.NA,
    ]

    lines = [_subsection("SUMMARY"), ""]

    # Determine column width for the label so everything aligns
    label_width = max(len(STATUS_LABEL[s]) for s in order)

    for status in order:
        c = counts[status]
        pct = round(100 * c / total) if total else 0
        label = STATUS_LABEL[status]
        # Count field: right-aligned in 3 chars; percentage in 4 chars
        count_str = f"{c:3d}  ({pct:3d}%)"
        bar = _bar(c, total) if status == CheckStatus.PASS else ""
        bar_part = f"  {bar}" if bar else ""
        line = f"  {label:{label_width}s}:  {count_str}{bar_part}"
        lines.append(line)

    return "\n".join(lines)


def _criterion_number(result: CheckResult) -> str:
    """Return the criterion id as a string, e.g. '1.3.1'."""
    return getattr(result, "criterion_id", "") or getattr(result, "criterion", "")


def _criterion_name(result: CheckResult) -> str:
    return getattr(result, "criterion_name", "") or getattr(result, "name", "")


def _criterion_level(result: CheckResult) -> str:
    return getattr(result, "level", "") or getattr(result, "wcag_level", "")


def _result_message(result: CheckResult) -> str:
    return getattr(result, "message", "") or getattr(result, "description", "")


def _result_recommendation(result: CheckResult) -> str:
    return getattr(result, "recommendation", "") or getattr(result, "suggestion", "")


def _format_check(result: CheckResult) -> List[str]:
    """
    Format a single CheckResult as a list of text lines.

    Layout:
      [XXXX] N.N.N  Criterion Name                           Level X
             <message or issue list>
    """
    tag = STATUS_TAG.get(result.status, "????")
    num = _criterion_number(result)
    name = _criterion_name(result)
    level = _criterion_level(result)

    # Header line: [TAG] num  name (padded) Level X — total width <= 80
    # "[XXXX] " = 7 chars; "  " between num and name = 2; "  Level X" = 9 max
    tag_prefix = f"[{tag}] "            # 7 chars
    level_suffix = f"Level {level}" if level else ""

    # Header layout: "  [TAG] num_name_padded Level X"
    #   2 spaces leading + 7 chars tag_prefix + num_name_padded + 1 space + level_suffix = 80
    LEAD = 2  # the "  " prepended to every check header
    num_name = f"{num}  {name}" if num else name
    if level_suffix:
        available = WIDTH - LEAD - len(tag_prefix) - 1 - len(level_suffix)
        num_name_padded = f"{num_name:<{available}}"
        header = f"{' ' * LEAD}{tag_prefix}{num_name_padded} {level_suffix}"
    else:
        available = WIDTH - LEAD - len(tag_prefix)
        num_name_padded = f"{num_name:<{available}}"
        header = f"{' ' * LEAD}{tag_prefix}{num_name_padded}"

    lines = [header]

    indent_body = 9  # align with text after "[XXXX] "

    issues: list[Issue] = getattr(result, "issues", []) or []
    message = _result_message(result)
    recommendation = _result_recommendation(result)

    if result.status == CheckStatus.MANUAL:
        if message:
            lines.append(_wrap(message, indent_body))
        if recommendation:
            lines.append(_wrap(f"Recommendation: {recommendation}", indent_body))
    elif result.status == CheckStatus.PASS:
        if message:
            lines.append(_wrap(message, indent_body))
    elif result.status == CheckStatus.NA:
        if message:
            lines.append(_wrap(message, indent_body))
    else:
        # FAIL
        if issues:
            n = len(issues)
            lines.append(_wrap(f"{n} issue(s) found:", indent_body))
            lines.append("")
            for issue in issues:
                lines.extend(_format_issue(issue, indent_body + 2))
                lines.append("")
        elif message:
            lines.append(_wrap(message, indent_body))

    return lines


def _format_issue(issue: Issue, indent: int) -> List[str]:
    """
    Format a single Issue as indented lines:

      SEVERITY  Summary text
               Location: <loc>
               Auto-fixable: Yes/No
    """
    severity = SEVERITY_LABEL.get(getattr(issue, "severity", None), "INFO")
    summary = getattr(issue, "message", "") or getattr(issue, "summary", "")
    location = getattr(issue, "location", "") or getattr(issue, "page", "")
    fixable = getattr(issue, "auto_fixable", None)

    pad = " " * indent
    # Severity label is up to 7 chars ("WARNING"); text follows after two spaces
    sev_width = 7
    first_indent = indent
    continuation_indent = indent + sev_width + 2

    lines: list[str] = []

    # First line: "  SEVERITY  summary…"
    first_line = f"{pad}{severity:<{sev_width}}  {summary}"
    if len(first_line) <= WIDTH:
        lines.append(first_line)
    else:
        # Wrap long summaries
        lines.append(f"{pad}{severity}")
        lines.append(_wrap(summary, continuation_indent))

    meta_pad = " " * continuation_indent
    if location:
        lines.append(f"{meta_pad}Location: {location}")
    if fixable is not None:
        lines.append(f"{meta_pad}Auto-fixable: {'Yes' if fixable else 'No'}")

    return lines


def _principal_number(result: CheckResult) -> int:
    """Extract the WCAG principle number (1–4) from the criterion id."""
    num = _criterion_number(result)
    if num:
        try:
            return int(num.split(".")[0])
        except (ValueError, IndexError):
            pass
    return 0


def _build_principles(results: List[CheckResult]) -> str:
    """Build all per-principle sections."""
    # Group by principle; unknown criteria go last under principle 0
    groups: dict[int, list[CheckResult]] = {}
    for r in results:
        p = _principal_number(r)
        groups.setdefault(p, []).append(r)

    sections: list[str] = []

    for p in sorted(groups.keys()):
        principle_results = groups[p]
        principle_name = PRINCIPLES.get(p, "OTHER")

        if p:
            heading = f"PRINCIPLE {p} — {principle_name}"
        else:
            heading = "OTHER CRITERIA"

        lines = [_section(heading), ""]

        for result in principle_results:
            check_lines = _format_check(result)
            lines.extend(check_lines)
            lines.append("")  # blank line between checks

        sections.append("\n".join(lines))

    return "\n".join(sections)


def _build_manual_review(results: List[CheckResult]) -> str:
    """Build the 'Issues Requiring Manual Review' section."""
    manual = [r for r in results if r.status == CheckStatus.MANUAL]

    lines = [_section("ISSUES REQUIRING MANUAL REVIEW"), ""]

    if not manual:
        lines.append("  None.")
    else:
        for result in manual:
            num = _criterion_number(result)
            name = _criterion_name(result)
            label = f"{num}  {name}" if num else name
            lines.append(f"  {label}")
            rec = _result_recommendation(result)
            msg = _result_message(result)
            detail = rec or msg
            if detail:
                lines.append(_wrap(detail, 6))
            lines.append("")

    return "\n".join(lines)


def _build_auto_fixed(results: List[CheckResult]) -> str:
    """Build the 'What Was Automatically Fixed' section."""
    lines = [_section("WHAT WAS AUTOMATICALLY FIXED"), ""]

    fixed_issues: list[tuple[CheckResult, Issue]] = []
    for result in results:
        for issue in (getattr(result, "issues", []) or []):
            if getattr(issue, "auto_fixable", False):
                fixed_issues.append((result, issue))

    if not fixed_issues:
        lines.append("  No automatic fixes were applied.")
    else:
        for result, issue in fixed_issues:
            num = _criterion_number(result)
            name = _criterion_name(result)
            label = f"{num}  {name}" if num else name
            summary = getattr(issue, "message", "") or getattr(issue, "summary", "")
            location = getattr(issue, "location", "") or getattr(issue, "page", "")

            lines.append(f"  [{label}]")
            if summary:
                lines.append(_wrap(summary, 6))
            if location:
                lines.append(f"      Location: {location}")
            lines.append("")

    return "\n".join(lines)


def _build_fixable_preview(results: List[CheckResult]) -> str:
    """Section shown when --fix has NOT yet been run: lists what it would fix."""
    fixable: dict = {}  # criterion -> (name, level, location)
    for r in results:
        for i in r.issues:
            if i.fixable and not i.fix_applied and r.wcag_criterion not in fixable:
                fixable[r.wcag_criterion] = (r.name, r.level, i.location or "")
    if not fixable:
        return ""

    lines = [_section("WHAT --fix CAN AUTOMATICALLY CORRECT"), ""]
    lines.append(f"  Running:  python check_pdf.py <your_pdf> --fix")
    lines.append(f"  ...will correct {len(fixable)} issue(s) automatically:")
    lines.append("")
    for crit, (name, level, loc) in fixable.items():
        header = f"  [{crit}] {name}"
        level_str = f"Level {level}"
        pad = max(0, 72 - len(header) - len(level_str))
        lines.append(f"{header}{' ' * pad}{level_str}")
        if loc:
            lines.append(f"         {loc}")
        lines.append("")
    lines.append(_rule("-"))
    return "\n".join(lines)


def _build_fixes_applied(results: List[CheckResult]) -> str:
    """Section shown after --fix was run: lists what was corrected."""
    fixed: dict = {}  # criterion -> name
    for r in results:
        for i in r.issues:
            if i.fix_applied and r.wcag_criterion not in fixed:
                fixed[r.wcag_criterion] = r.name
    if not fixed:
        return ""

    lines = [_section("AUTOMATICALLY FIXED BY --fix"), ""]
    lines.append("  The following issues were corrected automatically:")
    lines.append("")
    for crit, name in fixed.items():
        lines.append(f"  [FIXED]  [{crit}] {name}")
    lines.append("")
    lines.append(_rule())
    return "\n".join(lines)


def _build_what_to_do_next(
    results: List[CheckResult],
    already_fixed: bool = False,
    n_auto_fixed: int = 0,
) -> str:
    """Build the actionable 'What To Do Next' section."""
    failing = [r for r in results if r.status == CheckStatus.FAIL]
    manual_review = [r for r in results if r.status == CheckStatus.MANUAL]

    auto_fixable_pairs = [
        (r, i) for r in failing for i in r.issues if i.fixable
    ]
    manual_pairs = [
        (r, i) for r in failing for i in r.issues if not i.fixable
    ]

    if not auto_fixable_pairs and not manual_pairs and not manual_review and not (already_fixed and n_auto_fixed):
        return ""

    lines = [_section("WHAT TO DO NEXT"), ""]
    step = 1

    # ---- banner: --fix was run and corrected issues (now passing) ------------
    if already_fixed and n_auto_fixed > 0 and not auto_fixable_pairs:
        lines.append(
            f"  {step}. AUTO-FIXES APPLIED — {n_auto_fixed} structural fix(es) corrected"
        )
        lines.append(
            "     The issues listed below are what remains after --fix was run."
        )
        lines.append("")
        step += 1

    # ---- auto-fixable (still failing) ----------------------------------------
    if auto_fixable_pairs:
        n_checks = len({r.wcag_criterion for r, _ in auto_fixable_pairs})
        if already_fixed:
            lines.append(f"  {step}. CORRECTED BY --fix ({n_checks} issue(s) fixed automatically)")
        else:
            lines.append(f"  {step}. RUN --fix TO AUTO-CORRECT {n_checks} ISSUE(S)")
            lines.append("     python check_pdf.py <your_pdf> --fix")
        lines.append("")
        seen: set = set()
        for result, issue in auto_fixable_pairs:
            key = result.wcag_criterion
            if key not in seen:
                seen.add(key)
                marker = "[FIXED]" if already_fixed else "[AUTO] "
                lines.append(f"     {marker}  [{key}] {result.name}")
                if issue.location:
                    lines.append(_wrap(f"Location: {issue.location}", 20))
        lines.append("")
        step += 1

    # ---- manual fixes --------------------------------------------------------
    if manual_pairs:
        n_issues = len(manual_pairs)
        n_checks = len({r.wcag_criterion for r, _ in manual_pairs})
        lines.append(
            f"  {step}. MANUAL EDITS REQUIRED — {n_issues} issue(s) in {n_checks} check(s)"
        )
        lines.append("     Edit the source document (cannot be auto-fixed):")
        lines.append("")
        seen = set()
        for result, issue in manual_pairs:
            key = result.wcag_criterion
            if key not in seen:
                seen.add(key)
                lines.append(f"     [{key}] {result.name}")
                guidance = _MANUAL_FIX_GUIDANCE.get(
                    key, "Review this criterion and update the source document."
                )
                lines.append(_wrap(guidance, 11))
        lines.append("")
        step += 1

    # ---- manual review -------------------------------------------------------
    if manual_review:
        n = len(manual_review)
        lines.append(
            f"  {step}. MANUAL VISUAL REVIEW — {n} criterion/criteria"
        )
        lines.append("     Cannot be verified automatically — human review required:")
        lines.append("")
        for result in manual_review:
            lines.append(f"     [{result.wcag_criterion}] {result.name}")
            if result.issues:
                msg = result.issues[0].message
                if len(msg) > 100:
                    msg = msg[:97] + "..."
                lines.append(_wrap(msg, 11))
        lines.append("")

    return "\n".join(lines)


def _build_footer() -> str:
    url = "https://www.w3.org/TR/WCAG21/"
    content = f"WCAG 2.1 REFERENCE: {url}"
    lines = [
        _rule(),
        content,
        _rule(),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(
    results: List[CheckResult],
    pdf_path: str,
    output_path: str,
    already_fixed: bool = False,
    n_auto_fixed: int = 0,
) -> None:
    """
    Write a plain-text accessibility report to *output_path*.

    Parameters
    ----------
    results:
        List of CheckResult objects produced by the check modules.
    pdf_path:
        Path to the source PDF file (used for display only).
    output_path:
        Destination path for the ``.txt`` report.
    already_fixed:
        True when --fix was applied before this report was generated.
    n_auto_fixed:
        Number of fixers that actually changed the PDF.
    """
    sections = [
        _build_header(pdf_path, results),
        "",
        _build_summary(results),
        "",
        _build_what_to_do_next(results, already_fixed, n_auto_fixed),
        "",
        _build_fixable_preview(results),
        _build_fixes_applied(results),
        _build_principles(results),
        _build_manual_review(results),
        "",
        _build_auto_fixed(results),
        "",
        _build_footer(),
    ]

    report = "\n".join(sections) + "\n"

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(report)
