#!/usr/bin/env python3
"""
check_pdf.py — WCAG 2.1 Level AA accessibility checker for PDF files.

Usage:
    python check_pdf.py input.pdf
    python check_pdf.py input.pdf --fix
    python check_pdf.py input.pdf --fix --output fixed.pdf
    python check_pdf.py input.pdf --report-only
"""
import argparse
import io
import sys
import os
from datetime import date
from pathlib import Path

# Ensure UTF-8 output on all platforms (especially Windows).
# Only rewrap when running as a script so that importing the module doesn't
# close the caller's stdout prematurely (e.g. during testing).
if __name__ == "__main__" or hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # already a TextIOWrapper without .buffer (e.g. StringIO in tests)

# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

try:
    _USE_COLOUR = sys.stdout.isatty()
except Exception:
    _USE_COLOUR = False

_ANSI = {
    "green":  "\033[32m",
    "red":    "\033[31m",
    "yellow": "\033[33m",
    "gray":   "\033[90m",
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "cyan":   "\033[36m",
}


def _c(text: str, colour: str) -> str:
    """Wrap *text* in an ANSI colour escape if the terminal supports it."""
    if not _USE_COLOUR:
        return text
    return f"{_ANSI.get(colour, '')}{text}{_ANSI['reset']}"


def _badge(status_value: str) -> str:
    """Return a colourised [STATUS] badge string."""
    colour_map = {
        "PASS":   "green",
        "FAIL":   "red",
        "MANUAL": "yellow",
        "NA":     "gray",
    }
    label_map = {
        "PASS":   "PASS",
        "FAIL":   "FAIL",
        "MANUAL": "MNUL",
        "NA":     "N/A ",
    }
    label = label_map.get(status_value, status_value[:4].ljust(4))
    colour = colour_map.get(status_value, "reset")
    return _c(f"[{label}]", colour)


# ---------------------------------------------------------------------------
# Fixer application
# ---------------------------------------------------------------------------

def apply_fixes(pdf, pdf_path: str, lang: str, title: str):
    """Apply all automatic fixes.  Returns a list of dicts:
      {"desc": str, "status": "changed"|"already_ok"|"error", "detail": str}
    Every fixer always produces an entry so the caller can show what was
    attempted vs. what actually changed.
    """
    results = []

    def _record(desc, changed, detail=""):
        results.append({
            "desc": desc,
            "status": "changed" if changed else "already_ok",
            "detail": detail,
        })

    def _error(desc, exc):
        results.append({"desc": desc, "status": "error", "detail": str(exc)})

    # --- PDF/UA metadata ---------------------------------------------------
    try:
        from fixes.pdfua_metadata import fix_pdfua_metadata
        r = fix_pdfua_metadata(pdf)
        _record("PDF/UA metadata (pdfuaid:part = 1)", r.get("added", False))
    except Exception as exc:
        _error("PDF/UA metadata", exc)

    # --- Document title ----------------------------------------------------
    try:
        from fixes import document_title
        n = document_title.fix(pdf, title)
        _record("Document title", n > 0, f'set to "{title}"' if n else "already present")
    except Exception as exc:
        _error("Document title", exc)

    # --- Document language -------------------------------------------------
    try:
        from fixes import language
        n = language.fix(pdf, lang)
        _record("Document language (/Lang)", n > 0,
                f"set to {lang}" if n else f"already set to {lang}")
    except Exception as exc:
        _error("Document language", exc)

    # --- Untagged paths ----------------------------------------------------
    try:
        from fixes.untagged_paths import fix_untagged_paths
        r = fix_untagged_paths(pdf)
        wrapped = r.get("wrapped", 0)
        _record("Untagged path sequences → /Artifact", wrapped > 0,
                f"{wrapped} sequence(s) wrapped" if wrapped else "none found")
    except Exception as exc:
        _error("Untagged paths", exc)

    # --- Artifact/content nesting ------------------------------------------
    try:
        from fixes.artifact_content import fix_artifact_content
        r = fix_artifact_content(pdf)
        unwrapped = r.get("unwrapped", 0)
        _record("Artifact blocks containing tagged content", unwrapped > 0,
                f"{unwrapped} block(s) restructured" if unwrapped else "none found")
    except Exception as exc:
        _error("Artifact/content nesting", exc)

    # --- TH scope ----------------------------------------------------------
    try:
        from fixes.th_scope import fix_th_scope
        r = fix_th_scope(pdf)
        patched = r.get("patched", 0)
        _record("TH header cell /Scope attributes", patched > 0,
                f"{patched} cell(s) updated" if patched else "none needed / no tables")
    except Exception as exc:
        _error("TH scope", exc)

    # --- Alt text placeholders ---------------------------------------------
    try:
        from fixes import alt_text
        n = alt_text.fix(pdf, placeholder="Image — description needed")
        _record("Figure /Alt placeholder text", n > 0,
                f"{n} figure(s) updated" if n else "none needed / no untagged figures")
    except Exception as exc:
        _error("Figure alt text", exc)

    return results


def _print_fix_summary(fix_results, output_path: str):
    """Print each fixer's outcome with a clear changed / no-change / error badge."""
    n_changed    = sum(1 for r in fix_results if r["status"] == "changed")
    n_already_ok = sum(1 for r in fix_results if r["status"] == "already_ok")
    n_errors     = sum(1 for r in fix_results if r["status"] == "error")

    print("  Applying fixes...")
    print()
    for r in fix_results:
        if r["status"] == "changed":
            badge  = _c("✓  CHANGED   ", "green")
        elif r["status"] == "already_ok":
            badge  = _c("─  NO CHANGE ", "gray")
        else:
            badge  = _c("✗  ERROR     ", "red")
        detail = f"  ({r['detail']})" if r.get("detail") else ""
        print(f"    {badge}  {r['desc']}{detail}")

    print()
    print(f"    {_c(str(n_changed), 'green')} change(s) applied  •  "
          f"{_c(str(n_already_ok), 'gray')} already correct  •  "
          f"{_c(str(n_errors), 'red')} error(s)")
    print(f"    →  Saved: {_c(str(output_path), 'cyan')}")
    print()


# ---------------------------------------------------------------------------
# Console output helpers
# ---------------------------------------------------------------------------

_LINE_WIDTH = 70


def _banner():
    border = "═" * _LINE_WIDTH
    title  = "PDF ACCESSIBILITY CHECKER — WCAG 2.1 Level AA (ADA Title II)"
    pad    = (_LINE_WIDTH - len(title)) // 2
    print(f"╔{border}╗")
    print(f"║{' ' * pad}{title}{' ' * (_LINE_WIDTH - pad - len(title))}║")
    print(f"╚{border}╝")
    print()


def _print_check_line(result):
    """Print one check result line in the console summary."""
    from checks.base import CheckStatus

    badge = _badge(result.status.value)

    crit  = result.wcag_criterion.ljust(6)
    name  = result.name
    level = f"({result.level})"

    # right-align level within a fixed column layout
    detail = ""
    n_issues = len(result.issues)
    if result.status == CheckStatus.FAIL and n_issues:
        plural = "issue" if n_issues == 1 else "issues"
        detail = f"  {_c(str(n_issues) + ' ' + plural, 'red')}"
    elif result.status == CheckStatus.MANUAL:
        detail = f"  {_c('review required', 'yellow')}"

    # Fixed-width: badge=6, crit=7, name fills to col 54, level=5
    name_field = f"{name:<38}"
    level_field = f"{level:>4}"
    print(f"    {badge} {crit}  {name_field} {level_field}{detail}")


def _print_issue_details(all_results):
    """Print the expanded issue details section, marking fixability per issue."""
    from checks.base import CheckStatus, Severity

    failing = [r for r in all_results if r.status == CheckStatus.FAIL and r.issues]
    if not failing:
        return

    print(f"  {_c('── Issue Details ──────────────────────────────────────', 'bold')}")
    for result in failing:
        print(f"  [{result.wcag_criterion}] {result.name}:")
        for issue in result.issues:
            sev_str = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)
            colour = "red" if sev_str == "ERROR" else "yellow"
            msg = issue.message
            loc = f" ({issue.location})" if issue.location else ""
            fix_tag = f"  {_c('[auto-fixable: run --fix]', 'green')}" if issue.fixable else ""
            print(f"    • {_c(sev_str, colour)}  {msg}{loc}{fix_tag}")
        print()


_MANUAL_FIX_GUIDANCE = {
    "1.1.1": "Add meaningful alt text to every image in your authoring tool (Word, InDesign, LaTeX \\includegraphics[alt={...}]).",
    "1.3.1": "Re-author the PDF with proper tagging: use a tagged PDF workflow (LaTeX tagpdf, Adobe Acrobat, or Word's Accessibility Checker).",
    "1.3.2": "Re-author the PDF ensuring the structure tree reading order matches the visual order.",
    "1.4.3": "Change text or background colours in the source document to achieve ≥ 4.5:1 contrast (use https://webaim.org/resources/contrastchecker/).",
    "1.4.5": "Replace images of text with real searchable text in the source document.",
    "1.4.11": "Ensure form field borders and graphical UI components have ≥ 3:1 contrast against adjacent colours.",
    "2.4.1": "Add PDF bookmarks (Outlines) via your authoring tool or with Adobe Acrobat's Bookmarks panel.",
    "2.4.4": "Replace vague link text ('click here', 'read more') with descriptive text in the source document.",
    "2.4.5": "Add a Table of Contents or bookmarks so users have multiple ways to navigate the document.",
    "2.4.6": "Ensure headings are tagged (H1–H6) in proper hierarchical order in the structure tree.",
    "3.1.2": "Tag passages in a different language with the correct /Lang attribute in your authoring tool.",
}


def _print_next_steps(all_results, already_fixed: bool):
    """Print a clear 'What to do next' section separating auto-fixable from manual work."""
    from checks.base import CheckStatus

    failing = [r for r in all_results if r.status == CheckStatus.FAIL]
    manual_review = [r for r in all_results if r.status == CheckStatus.MANUAL]

    if not failing and not manual_review:
        return

    sep = "─" * _LINE_WIDTH
    print(f"  {_c('── What To Do Next ────────────────────────────────────', 'bold')}")
    print()

    # --- Auto-fixable failures ------------------------------------------------
    auto_fixable_issues = [
        (r, i) for r in failing
        for i in r.issues if i.fixable
    ]
    manual_issues = [
        (r, i) for r in failing
        for i in r.issues if not i.fixable
    ]

    # --- What --fix can do (always shown; wording changes if already fixed) ---
    if auto_fixable_issues:
        n = len(auto_fixable_issues)
        checks = len({r.wcag_criterion for r, _ in auto_fixable_issues})
        if already_fixed:
            print(f"  {_c('✓  --fix was applied — auto-fixable issues corrected:', 'green')}")
        else:
            print(f"  {_c('1. --fix can automatically correct these issues:', 'green')}")
        seen = set()
        for result, issue in auto_fixable_issues:
            key = result.wcag_criterion
            if key not in seen:
                seen.add(key)
                tag = _c("✓ fixed", "green") if already_fixed else _c("→ fixable", "green")
                print(f"       {tag}  [{key}] {result.name}")
                if issue.location:
                    print(f"              Location: {issue.location}")
        print()
        if not already_fixed:
            print(f"     {_c('Run:', 'bold')} python check_pdf.py <your_pdf> {_c('--fix', 'bold')}")
            print()

    # --- Manual failures ------------------------------------------------------
    if manual_issues:
        n = len(manual_issues)
        checks = len({r.wcag_criterion for r, _ in manual_issues})
        label = "2." if (auto_fixable_issues and not already_fixed) else "1."
        print(f"  {_c(f'{label} Issues that require manual changes to the source document', 'red')}")
        print(f"     {n} issue{'s' if n != 1 else ''} across {checks} "
              f"criterion/criteria cannot be fixed automatically:")
        print()
        seen = set()
        for result, issue in manual_issues:
            key = result.wcag_criterion
            if key not in seen:
                seen.add(key)
                guidance = _MANUAL_FIX_GUIDANCE.get(key, "Review the criterion and update the source document.")
                print(f"       • [{key}] {result.name}")
                print(f"         {guidance}")
        print()

    # --- Manual review items --------------------------------------------------
    if manual_review:
        n = len(manual_review)
        label_n = sum([
            bool(auto_fixable_issues and not already_fixed),
            bool(manual_issues),
        ]) + 1
        print(f"  {_c(f'{label_n}. Items needing manual visual review', 'yellow')}")
        print(f"     These {n} criterion/criteria cannot be verified automatically:")
        for result in manual_review:
            print(f"       • [{result.wcag_criterion}] {result.name}")
            if result.issues:
                print(f"         {result.issues[0].message[:100]}")
        print()


def _print_summary(all_results, report_html, report_txt, output_pdf=None):
    """Print the complete console summary section."""
    from checks.base import CheckStatus

    already_fixed = output_pdf is not None

    n_total  = len(all_results)
    n_pass   = sum(1 for r in all_results if r.status == CheckStatus.PASS)
    n_fail   = sum(1 for r in all_results if r.status == CheckStatus.FAIL)
    n_manual = sum(1 for r in all_results if r.status == CheckStatus.MANUAL)
    n_na     = sum(1 for r in all_results if r.status == CheckStatus.NA)

    pct_pass   = round(n_pass   / n_total * 100) if n_total else 0
    pct_fail   = round(n_fail   / n_total * 100) if n_total else 0
    pct_manual = round(n_manual / n_total * 100) if n_total else 0

    # Count auto-fixable vs manual-only failures
    n_auto_fixable = sum(
        1 for r in all_results if r.status == CheckStatus.FAIL
        for i in r.issues if i.fixable
    )
    n_manual_only = sum(
        1 for r in all_results if r.status == CheckStatus.FAIL
        for i in r.issues if not i.fixable
    )

    sep = "═" * _LINE_WIDTH
    print(f"  {sep}")
    print("  SUMMARY")
    print(f"  {sep}")
    print(f"    Passed:        {n_pass:3d} / {n_total}   ({pct_pass}%)")
    print(f"    Failed:        {n_fail:3d} / {n_total}   ({pct_fail}%)", end="")
    if n_fail > 0 and not already_fixed:
        auto_note = f"  ← {n_auto_fixable} auto-fixable, {n_manual_only} need manual changes"
        print(_c(auto_note, "yellow"), end="")
    print()
    print(f"    Needs Review:  {n_manual:3d} / {n_total}   ({pct_manual}%)  ← cannot be auto-verified")
    print(f"    Not Applicable:{n_na:3d} / {n_total}")
    print()

    _print_issue_details(all_results)
    _print_next_steps(all_results, already_fixed)

    # --- Report paths ------------------------------------------------------
    print("  Reports saved:")
    if report_html:
        print(f"    {_c(report_html, 'cyan')}")
    if report_txt:
        print(f"    {_c(report_txt, 'cyan')}")
    print()

    # --- Overall status line -----------------------------------------------
    sep2 = "─" * _LINE_WIDTH
    print(f"  {sep2}")

    if n_fail == 0 and n_manual == 0:
        print(f"  Overall status: {_c('✓ ALL CHECKS PASSED', 'green')}")
        print(f"  {_c('This document meets WCAG 2.1 Level AA requirements.', 'green')}")

    elif n_fail == 0:
        print(f"  Overall status: {_c('⚠  MANUAL REVIEW NEEDED', 'yellow')}")
        print(f"  All automated checks passed, but {n_manual} criterion/criteria "
              f"require human verification.")
        print(f"  See 'What To Do Next' above for details.")

    else:
        fail_word  = "check" if n_fail  == 1 else "checks"
        rev_word   = "criterion" if n_manual == 1 else "criteria"
        print(f"  Overall status: {_c('✗  ISSUES FOUND', 'red')}")
        print(f"  {_c(str(n_fail), 'red')} {fail_word} failed"
              + (f"  •  {_c(str(n_manual), 'yellow')} {rev_word} need manual review" if n_manual else ""))
        print()
        if already_fixed:
            if n_auto_fixable == 0:
                print(f"  {_c('✓', 'green')} Auto-fixable issues were corrected by --fix.")
            print(f"  {_c('✗', 'red')} {n_manual_only} issue(s) in {n_fail} check(s) require "
                  f"manual changes to the source document.")
        else:
            if n_auto_fixable:
                print(f"  {_c('→', 'green')} {n_auto_fixable} issue(s) are auto-fixable — "
                      f"run: python check_pdf.py <pdf> {_c('--fix', 'bold')}")
            if n_manual_only:
                print(f"  {_c('→', 'red')} {n_manual_only} issue(s) require manual changes "
                      f"to the source document")
        print(f"  See 'What To Do Next' above for step-by-step guidance.")

    print(f"  {sep2}")
    print()


# ---------------------------------------------------------------------------
# Principle grouping
# ---------------------------------------------------------------------------

_PRINCIPLE_LABELS = {
    "1": "PERCEIVABLE (Principle 1)",
    "2": "OPERABLE (Principle 2)",
    "3": "UNDERSTANDABLE (Principle 3)",
    "4": "ROBUST (Principle 4)",
}


def _print_results_by_principle(all_results):
    """Print check results grouped by WCAG principle."""
    groups: dict = {}
    for r in all_results:
        key = r.wcag_criterion[0] if r.wcag_criterion else "0"
        groups.setdefault(key, []).append(r)

    for key in sorted(groups.keys()):
        label = _PRINCIPLE_LABELS.get(key, f"Principle {key}")
        print(f"  {_c(label, 'bold')}")
        print(f"  {'─' * _LINE_WIDTH}")
        for result in groups[key]:
            _print_check_line(result)
        print()


# ---------------------------------------------------------------------------
# Checker runner
# ---------------------------------------------------------------------------

_CHECKER_MODULES = [
    ("metadata",  "checks.metadata",  "metadata_run",  "Metadata"),
    ("structure", "checks.structure", "structure_run", "Structure"),
    ("images",    "checks.images",    "images_run",    "Images"),
    ("tables",    "checks.tables",    "tables_run",    "Tables"),
    ("links",     "checks.links",     "links_run",     "Links"),
    ("contrast",  "checks.contrast",  "contrast_run",  "Contrast"),
    ("fonts",     "checks.fonts",     "fonts_run",     "Fonts"),
    ("forms",     "checks.forms",     "forms_run",     "Forms"),
    ("bookmarks", "checks.bookmarks", "bookmarks_run", "Bookmarks"),
]


def run_all_checks(pdf, pdf_path: str) -> list:
    """Run every checker module and return a flat list of CheckResult objects."""
    import importlib

    all_results = []
    for _short, module_name, alias, label in _CHECKER_MODULES:
        print(f"    ▸ Checking {label}...", end="", flush=True)
        try:
            mod = importlib.import_module(module_name)
            run_fn = getattr(mod, "run")
            results = run_fn(pdf, pdf_path)
            all_results.extend(results)
            print(f"\r    {_c('✓', 'green')} {label:<12}  {len(results)} criterion/criteria")
        except ImportError:
            print(f"\r    {_c('⚠', 'yellow')} {label:<12}  module not found — skipped")
        except Exception as exc:
            print(f"\r    {_c('✗', 'red')} {label:<12}  error: {exc}")

    return all_results


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_pdf.py",
        description="WCAG 2.1 Level AA accessibility checker for PDF files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "pdf",
        metavar="PDF",
        help="Path to the PDF file to check.",
    )
    parser.add_argument(
        "--fix", "-f",
        action="store_true",
        help="Apply automatic fixes before checking.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="OUT",
        help="Output path for the fixed PDF (default: <name>_fixed.pdf).",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip the console summary; only generate report files.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML report generation.",
    )
    parser.add_argument(
        "--no-txt",
        action="store_true",
        help="Skip TXT report generation.",
    )
    parser.add_argument(
        "--lang",
        default="en-US",
        metavar="LANG",
        help="BCP-47 language code to set when using --fix (default: en-US).",
    )
    parser.add_argument(
        "--title",
        default=None,
        metavar="TITLE",
        help=(
            "Document title to set when using --fix. "
            "Defaults to the filename stem."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Exit code helpers
# ---------------------------------------------------------------------------

def _exit_code(all_results) -> int:
    """Return 0 (all pass), 1 (any fail), or 2 (any manual, no fail)."""
    from checks.base import CheckStatus
    statuses = {r.status for r in all_results}
    if CheckStatus.FAIL in statuses:
        return 1
    if CheckStatus.MANUAL in statuses:
        return 2
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    pdf_path = Path(args.pdf)

    # --- Validate input path -----------------------------------------------
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        return 1
    if not pdf_path.is_file():
        print(f"Error: not a file: {pdf_path}", file=sys.stderr)
        return 1

    # --- Resolve output path -----------------------------------------------
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = pdf_path.with_name(pdf_path.stem + "_fixed" + pdf_path.suffix)

    # --- Resolve title default ---------------------------------------------
    title = args.title if args.title else pdf_path.stem

    # --- Banner ------------------------------------------------------------
    _banner()

    # --- Open PDF ----------------------------------------------------------
    try:
        import pikepdf
    except ImportError:
        print("Error: pikepdf is required. Install it with: pip install pikepdf", file=sys.stderr)
        return 1

    try:
        pdf = pikepdf.open(str(pdf_path))
    except Exception as exc:
        print(f"Error: could not open PDF: {exc}", file=sys.stderr)
        return 1

    n_pages = len(pdf.pages)
    today   = date.today().isoformat()
    pdf_name = pdf_path.name

    print(f"  File : {_c(pdf_name, 'bold')}")
    print(f"  Pages: {n_pages}")
    print(f"  Date : {today}")
    print()

    # --- Apply fixes -------------------------------------------------------
    fixed_pdf_path = str(pdf_path)  # default: check original

    if args.fix:
        try:
            fix_results = apply_fixes(pdf, str(pdf_path), args.lang, title)

            # Save before printing so output_path exists when referenced
            try:
                pdf.save(str(output_path))
            except Exception as exc:
                print(f"  ERROR: could not save fixed PDF: {exc}", file=sys.stderr)
                pdf.close()
                return 1

            _print_fix_summary(fix_results, output_path)

            pdf.close()

            # Re-open the fixed PDF for checking
            fixed_pdf_path = str(output_path)
            try:
                pdf = pikepdf.open(fixed_pdf_path)
            except Exception as exc:
                print(f"Error: could not reopen fixed PDF for checking: {exc}", file=sys.stderr)
                return 1

        except Exception as exc:
            print(f"  ERROR during fix application: {exc}", file=sys.stderr)
            pdf.close()
            return 1

        print()

    # --- Run checkers -------------------------------------------------------
    print("  Checking WCAG 2.1 Level AA criteria...")
    print()

    all_results = run_all_checks(pdf, fixed_pdf_path)
    pdf.close()

    print()

    # --- Console summary ----------------------------------------------------
    if not args.report_only:
        _print_results_by_principle(all_results)

    # --- Generate reports ---------------------------------------------------
    stem = pdf_path.stem
    report_html_path = None
    report_txt_path  = None

    if not args.no_html:
        report_html_path = str(pdf_path.with_name(stem + "_accessibility_report.html"))
        try:
            from report.html_report import generate as html_generate
            html_generate(all_results, str(pdf_path), report_html_path)
        except ImportError:
            print("WARNING: report.html_report not available — HTML report skipped.", file=sys.stderr)
            report_html_path = None
        except Exception as exc:
            print(f"WARNING: HTML report generation failed: {exc}", file=sys.stderr)
            report_html_path = None

    if not args.no_txt:
        report_txt_path = str(pdf_path.with_name(stem + "_accessibility_report.txt"))
        try:
            from report.txt_report import generate as txt_generate
            txt_generate(all_results, str(pdf_path), report_txt_path)
        except ImportError:
            print("WARNING: report.txt_report not available — TXT report skipped.", file=sys.stderr)
            report_txt_path = None
        except Exception as exc:
            print(f"WARNING: TXT report generation failed: {exc}", file=sys.stderr)
            report_txt_path = None

    # --- Print summary (with report paths) ----------------------------------
    if not args.report_only:
        _print_summary(all_results, report_html_path, report_txt_path,
                       output_pdf=str(output_path) if args.fix else None)
    else:
        # Minimal output when --report-only: just print the file paths
        print("  Reports saved:")
        if report_html_path:
            print(f"    {_c(report_html_path, 'cyan')}")
        if report_txt_path:
            print(f"    {_c(report_txt_path, 'cyan')}")
        print()

    return _exit_code(all_results)


if __name__ == "__main__":
    sys.exit(main())
