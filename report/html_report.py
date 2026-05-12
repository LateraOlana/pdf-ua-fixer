"""Generate a self-contained HTML accessibility report from check results."""

from checks.base import CheckResult, CheckStatus, Severity, Issue
from typing import List
from datetime import datetime
import os


# ---------------------------------------------------------------------------
# WCAG principle mapping
# ---------------------------------------------------------------------------

_PRINCIPLES = {
    "1": ("Perceivable", "#6366f1"),
    "2": ("Operable", "#0ea5e9"),
    "3": ("Understandable", "#8b5cf6"),
    "4": ("Robust", "#10b9a5"),
}


# ---------------------------------------------------------------------------
# Small HTML helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _status_badge(status: CheckStatus) -> str:
    colours = {
        CheckStatus.PASS:   ("#22c55e", "#ffffff"),
        CheckStatus.FAIL:   ("#ef4444", "#ffffff"),
        CheckStatus.MANUAL: ("#f59e0b", "#ffffff"),
        CheckStatus.NA:     ("#94a3b8", "#ffffff"),
    }
    labels = {
        CheckStatus.PASS:   "PASS",
        CheckStatus.FAIL:   "FAIL",
        CheckStatus.MANUAL: "MANUAL",
        CheckStatus.NA:     "N/A",
    }
    bg, fg = colours.get(status, ("#94a3b8", "#ffffff"))
    label = labels.get(status, status.value)
    return (
        f'<span class="badge" style="background:{bg};color:{fg};">'
        f"{label}</span>"
    )


def _level_badge(level: str) -> str:
    colour = "#3b82f6" if level == "AA" else "#64748b"
    return (
        f'<span class="badge level-badge" style="background:{colour};color:#fff;">'
        f"{_esc(level)}</span>"
    )


def _severity_icon(severity: Severity) -> str:
    icons = {
        Severity.ERROR:   ("&#9888;", "#ef4444"),   # ⚠
        Severity.WARNING: ("&#9888;", "#f59e0b"),
        Severity.INFO:    ("&#8505;", "#3b82f6"),    # ℹ
    }
    symbol, colour = icons.get(severity, ("&#8505;", "#64748b"))
    return f'<span style="color:{colour};font-size:1rem;" aria-hidden="true">{symbol}</span>'


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont,
                 'Segoe UI', Roboto, sans-serif;
    font-size: 0.9375rem;
    line-height: 1.6;
    background: #f8fafc;
    color: #1e293b;
    min-height: 100vh;
}

a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ---- page layout ---- */
.page-wrap {
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
}

/* ---- header ---- */
.site-header {
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    color: #f8fafc;
    padding: 2rem 1.5rem 1.75rem;
    border-bottom: 3px solid #3b82f6;
}
.site-header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}
.site-header .meta {
    margin-top: 0.4rem;
    font-size: 0.875rem;
    color: #94a3b8;
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
}
.site-header .meta span { display: flex; align-items: center; gap: 0.35rem; }

/* ---- section titles ---- */
.section-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
    margin: 2.5rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

/* ---- summary cards ---- */
.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin-top: 1.5rem;
}
.card {
    background: #ffffff;
    border-radius: 0.75rem;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.05);
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}
.card-count {
    font-size: 2rem;
    font-weight: 800;
    line-height: 1;
}
.card-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
}
.card.pass  .card-count { color: #22c55e; }
.card.fail  .card-count { color: #ef4444; }
.card.manual .card-count { color: #f59e0b; }
.card.na    .card-count { color: #94a3b8; }
.card.total .card-count { color: #3b82f6; }

/* ---- compliance bar ---- */
.compliance-wrap {
    background: #ffffff;
    border-radius: 0.75rem;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    margin-top: 1rem;
}
.compliance-label {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.6rem;
}
.compliance-label span:first-child {
    font-weight: 600;
    font-size: 0.9rem;
    color: #475569;
}
.compliance-label span:last-child {
    font-size: 1.25rem;
    font-weight: 800;
    color: #1e293b;
}
.bar-track {
    background: #e2e8f0;
    border-radius: 9999px;
    height: 14px;
    overflow: hidden;
}
.bar-fill {
    height: 100%;
    border-radius: 9999px;
    background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
    transition: width 0.8s cubic-bezier(.4,0,.2,1);
}

/* ---- principle group ---- */
.principle-group { margin-top: 1.5rem; }
.principle-heading {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    padding: 0.35rem 0.75rem;
    border-radius: 0.375rem;
    color: #ffffff;
    display: inline-block;
    margin-bottom: 0.6rem;
}

/* ---- results table ---- */
.results-table {
    width: 100%;
    border-collapse: collapse;
    background: #ffffff;
    border-radius: 0.75rem;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
.results-table thead tr {
    background: #f1f5f9;
    border-bottom: 2px solid #e2e8f0;
}
.results-table th {
    text-align: left;
    padding: 0.65rem 1rem;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
    white-space: nowrap;
}
.results-table td {
    padding: 0.7rem 1rem;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: middle;
}
.results-table tr.data-row:last-child td { border-bottom: none; }
.results-table tr.data-row {
    cursor: pointer;
    transition: background 0.15s;
}
.results-table tr.data-row:hover { background: #f8fafc; }
.results-table tr.data-row.has-issues { cursor: pointer; }
.results-table tr.data-row.no-issues { cursor: default; }

/* ---- expand chevron ---- */
.chevron {
    display: inline-block;
    width: 1rem;
    text-align: center;
    transition: transform 0.25s ease;
    color: #94a3b8;
    font-size: 0.75rem;
    user-select: none;
}
.chevron.open { transform: rotate(90deg); }

/* ---- issue detail row ---- */
tr.detail-row td {
    padding: 0;
    border-bottom: 1px solid #e2e8f0;
}
tr.detail-row.hidden { display: none; }
.detail-inner {
    overflow: hidden;
    max-height: 0;
    transition: max-height 0.35s cubic-bezier(.4,0,.2,1);
    background: #f8fafc;
}
.detail-inner.open { max-height: 2000px; }
.issue-list {
    list-style: none;
    padding: 0.75rem 1.25rem 0.75rem 2.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
.issue-item {
    display: grid;
    grid-template-columns: 1.25rem 1fr;
    gap: 0.4rem 0.5rem;
    align-items: start;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
}
.issue-msg { font-size: 0.875rem; color: #334155; }
.issue-loc {
    grid-column: 2;
    font-size: 0.8rem;
    color: #64748b;
    font-style: italic;
}
.fix-tag {
    grid-column: 2;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: #16a34a;
    font-weight: 600;
    margin-top: 0.1rem;
}

/* ---- manual review section ---- */
.manual-list, .fixed-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 0.5rem;
}
.manual-item, .fixed-item {
    background: #ffffff;
    border-left: 4px solid;
    border-radius: 0 0.5rem 0.5rem 0;
    padding: 0.85rem 1rem;
    box-shadow: 0 1px 2px rgba(0,0,0,.05);
}
.manual-item { border-color: #f59e0b; }
.fixed-item  { border-color: #22c55e; }
.item-header {
    font-weight: 600;
    font-size: 0.875rem;
    color: #1e293b;
    margin-bottom: 0.2rem;
}
.item-body {
    font-size: 0.85rem;
    color: #475569;
}
.item-loc {
    font-size: 0.8rem;
    color: #94a3b8;
    margin-top: 0.25rem;
    font-style: italic;
}
.empty-state {
    background: #f1f5f9;
    border-radius: 0.5rem;
    padding: 1rem 1.25rem;
    font-size: 0.875rem;
    color: #64748b;
    margin-top: 0.5rem;
}

/* ---- badge base ---- */
.badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.2em 0.55em;
    border-radius: 0.375rem;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    white-space: nowrap;
}
.level-badge { font-size: 0.7rem; }

/* ---- footer ---- */
.site-footer {
    text-align: center;
    padding: 1.5rem 1rem;
    font-size: 0.8rem;
    color: #94a3b8;
    border-top: 1px solid #e2e8f0;
    margin-top: 3rem;
}

.auto-fix-preview { background:#f0fdf4; border-left:4px solid #22c55e; padding:20px 24px; border-radius:8px; margin:24px 0; }
.auto-fixed { background:#f0fdf4; border-left:4px solid #22c55e; padding:20px 24px; border-radius:8px; margin:24px 0; }
.fix-title, .fixed-title { color:#15803d; margin:0 0 12px; font-size:1.1rem; }
.fix-list, .fixed-list { list-style:none; padding:0; margin:12px 0; }
.fix-list li, .fixed-list li { padding:10px 0; border-bottom:1px solid #bbf7d0; display:flex; align-items:flex-start; gap:10px; flex-wrap:wrap; }
.fix-detail { width:100%; color:#166534; font-size:0.85rem; margin-top:4px; }
.fix-command { background:#dcfce7; border-radius:6px; padding:12px 16px; margin-top:16px; font-family:monospace; font-size:0.9rem; color:#14532d; }
"""

# ---------------------------------------------------------------------------
# JS
# ---------------------------------------------------------------------------

_JS = """
(function () {
    'use strict';

    document.querySelectorAll('tr.data-row.has-issues').forEach(function (row) {
        row.addEventListener('click', function () {
            var targetId = row.getAttribute('data-detail');
            var detailRow = document.getElementById(targetId);
            if (!detailRow) return;
            var inner = detailRow.querySelector('.detail-inner');
            var chevron = row.querySelector('.chevron');
            var isOpen = inner.classList.contains('open');
            if (isOpen) {
                inner.classList.remove('open');
                detailRow.classList.add('hidden');
                if (chevron) chevron.classList.remove('open');
            } else {
                detailRow.classList.remove('hidden');
                // Force reflow so transition fires
                void inner.offsetHeight;
                inner.classList.add('open');
                if (chevron) chevron.classList.add('open');
            }
        });
        row.setAttribute('tabindex', '0');
        row.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                row.click();
            }
        });
    });
})();
"""


# ---------------------------------------------------------------------------
# Issue detail HTML
# ---------------------------------------------------------------------------

def _render_issues(issues: List[Issue]) -> str:
    if not issues:
        return ""
    items = []
    for issue in issues:
        icon = _severity_icon(issue.severity)
        msg = _esc(issue.message)
        loc_html = (
            f'<span class="issue-loc">&#128205; {_esc(issue.location)}</span>'
            if issue.location else ""
        )
        fix_html = (
            '<span class="fix-tag">&#10003; Auto-fixed</span>'
            if issue.fix_applied else ""
        )
        items.append(
            f'<li class="issue-item">'
            f'<span>{icon}</span>'
            f'<span class="issue-msg">{msg}</span>'
            f'{loc_html}'
            f'{fix_html}'
            f'</li>'
        )
    return '<ul class="issue-list">' + "\n".join(items) + "</ul>"


# ---------------------------------------------------------------------------
# Results table (grouped by principle)
# ---------------------------------------------------------------------------

def _render_results_tables(results: List[CheckResult]) -> str:
    # Group by first digit of criterion
    groups: dict = {"1": [], "2": [], "3": [], "4": [], "other": []}
    for r in results:
        key = r.wcag_criterion[0] if r.wcag_criterion else "other"
        if key not in groups:
            key = "other"
        groups[key].append(r)

    html_parts = []
    row_id = 0

    for key, principle_label, _ in [
        ("1", "1 – Perceivable", "#6366f1"),
        ("2", "2 – Operable", "#0ea5e9"),
        ("3", "3 – Understandable", "#8b5cf6"),
        ("4", "4 – Robust", "#10b9a5"),
        ("other", "Other", "#64748b"),
    ]:
        bucket = groups.get(key, [])
        if not bucket:
            continue

        _, colour = _PRINCIPLES.get(key, ("Other", "#64748b"))

        rows_html = []
        for result in bucket:
            row_id += 1
            detail_id = f"detail-{row_id}"
            has_issues = bool(result.issues)
            row_class = "data-row has-issues" if has_issues else "data-row no-issues"
            chevron_html = (
                '<span class="chevron" aria-hidden="true">&#9654;</span>'
                if has_issues else '<span style="display:inline-block;width:1rem;"></span>'
            )
            issue_count = len(result.issues) if result.issues else 0
            issue_count_cell = (
                f'<span style="color:#ef4444;font-weight:600;">{issue_count}</span>'
                if issue_count > 0 else
                '<span style="color:#94a3b8;">—</span>'
            )

            data_attr = f'data-detail="{detail_id}"' if has_issues else ""
            aria = 'role="button" aria-expanded="false"' if has_issues else ""

            rows_html.append(
                f'<tr class="{row_class}" {data_attr} {aria}>'
                f'<td>{chevron_html}</td>'
                f'<td>{_status_badge(result.status)}</td>'
                f'<td style="font-variant-numeric:tabular-nums;white-space:nowrap;">'
                f'<code style="font-size:0.85rem;">{_esc(result.wcag_criterion)}</code></td>'
                f'<td>{_esc(result.name)}</td>'
                f'<td>{_level_badge(result.level)}</td>'
                f'<td style="text-align:center;">{issue_count_cell}</td>'
                f'</tr>'
            )

            # Detail row (always rendered, toggled via JS/CSS)
            issues_html = _render_issues(result.issues)
            hidden_class = " hidden" if True else ""  # starts hidden
            rows_html.append(
                f'<tr class="detail-row hidden" id="{detail_id}">'
                f'<td colspan="6">'
                f'<div class="detail-inner">{issues_html}</div>'
                f'</td>'
                f'</tr>'
            )

        heading_style = (
            f'background:{_PRINCIPLES.get(key, ("Other", "#64748b"))[1] if key in _PRINCIPLES else "#64748b"};'
        )
        principle_name = _PRINCIPLES.get(key, ("Other", "#64748b"))[0] if key in _PRINCIPLES else "Other"
        group_html = (
            f'<div class="principle-group">'
            f'<span class="principle-heading" style="{heading_style}">'
            f'Principle {_esc(principle_name)}</span>'
            f'<table class="results-table" role="table">'
            f'<thead><tr>'
            f'<th style="width:1.5rem;"></th>'
            f'<th>Status</th>'
            f'<th>Criterion</th>'
            f'<th>Name</th>'
            f'<th>Level</th>'
            f'<th style="text-align:center;">Issues</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody>'
            f'</table>'
            f'</div>'
        )
        html_parts.append(group_html)

    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# Manual review section
# ---------------------------------------------------------------------------

def _render_manual_section(results: List[CheckResult]) -> str:
    manual_results = [r for r in results if r.status == CheckStatus.MANUAL]
    if not manual_results:
        return '<p class="empty-state">No items require manual review.</p>'

    items = []
    for r in manual_results:
        crit = _esc(r.wcag_criterion)
        name = _esc(r.name)
        desc = _esc(r.description) if r.description else ""
        url = r.wcag_url or f"https://www.w3.org/TR/WCAG21/#{r.wcag_criterion.replace('.', '')}"
        issue_lines = ""
        for issue in r.issues:
            issue_lines += f"<p class='item-body'>{_esc(issue.message)}</p>"
            if issue.location:
                issue_lines += f"<p class='item-loc'>&#128205; {_esc(issue.location)}</p>"
        items.append(
            f'<li class="manual-item">'
            f'<div class="item-header">'
            f'<code>{crit}</code> {name} {_level_badge(r.level)}'
            f'</div>'
            f'{issue_lines}'
            f'{"<p class=item-body>" + desc + "</p>" if desc and not r.issues else ""}'
            f'<p class="item-loc">'
            f'<a href="{_esc(url)}" target="_blank" rel="noopener">WCAG reference &#8599;</a>'
            f'</p>'
            f'</li>'
        )
    return '<ul class="manual-list">' + "\n".join(items) + "</ul>"


# ---------------------------------------------------------------------------
# Fixed items section
# ---------------------------------------------------------------------------

def _render_fixed_section(results: List[CheckResult]) -> str:
    fixed_issues: List[tuple] = []
    for r in results:
        for issue in r.issues:
            if issue.fix_applied:
                fixed_issues.append((r, issue))

    if not fixed_issues:
        return '<p class="empty-state">No automatic fixes were applied.</p>'

    items = []
    for result, issue in fixed_issues:
        crit = _esc(result.wcag_criterion)
        name = _esc(result.name)
        msg = _esc(issue.message)
        loc_html = (
            f'<p class="item-loc">&#128205; {_esc(issue.location)}</p>'
            if issue.location else ""
        )
        items.append(
            f'<li class="fixed-item">'
            f'<div class="item-header">&#10003; <code>{crit}</code> {name}</div>'
            f'<p class="item-body">{msg}</p>'
            f'{loc_html}'
            f'</li>'
        )
    return '<ul class="fixed-list">' + "\n".join(items) + "</ul>"


# ---------------------------------------------------------------------------
# Auto-fix preview section
# ---------------------------------------------------------------------------

def _render_auto_fix_preview(results: List[CheckResult]) -> str:
    """Return HTML for 'What --fix Can Automatically Correct' or empty string."""
    seen: set = set()
    fixable_items: list = []  # (criterion, name, level, location)
    for r in results:
        for i in r.issues:
            if i.fixable and not i.fix_applied and r.wcag_criterion not in seen:
                seen.add(r.wcag_criterion)
                fixable_items.append((r.wcag_criterion, r.name, r.level, i.location or ""))

    if not fixable_items:
        return ""

    n = len(fixable_items)
    li_html = []
    for crit, name, level, loc in fixable_items:
        level_cls = "level-a" if level == "A" else ("level-aa" if level == "AA" else "")
        loc_html = (
            f'<div class="fix-detail">&#128205; {_esc(loc)}</div>'
            if loc else ""
        )
        li_html.append(
            f'<li>'
            f'<span class="crit-badge badge" style="background:#166534;color:#fff;">{_esc(crit)}</span>'
            f'<strong>{_esc(name)}</strong>'
            f'<span class="level-badge badge" style="background:#3b82f6;color:#fff;">{_esc(level)}</span>'
            f'{loc_html}'
            f'</li>'
        )

    return (
        f'<section class="auto-fix-preview">'
        f'<h2 class="section-title fix-title">&#128295; What <code>--fix</code> Can Automatically Correct</h2>'
        f'<p>Running <code>python check_pdf.py your_file.pdf --fix</code> will automatically correct '
        f'<strong>{n} issue(s)</strong> in this document without any manual editing:</p>'
        f'<ul class="fix-list">{"".join(li_html)}</ul>'
        f'<div class="fix-command">'
        f'<code>python check_pdf.py &lt;your_pdf&gt; --fix</code>'
        f'</div>'
        f'</section>'
    )


# ---------------------------------------------------------------------------
# Auto-fixed summary section
# ---------------------------------------------------------------------------

def _render_auto_fixed_summary(results: List[CheckResult]) -> str:
    """Return HTML for 'Issues Corrected by --fix' or empty string."""
    seen: set = set()
    fixed_items: list = []  # (criterion, name)
    for r in results:
        for i in r.issues:
            if i.fix_applied and r.wcag_criterion not in seen:
                seen.add(r.wcag_criterion)
                fixed_items.append((r.wcag_criterion, r.name))

    if not fixed_items:
        return ""

    li_html = []
    for crit, name in fixed_items:
        li_html.append(
            f'<li>'
            f'<span class="crit-badge badge" style="background:#166534;color:#fff;">{_esc(crit)}</span>'
            f'<strong>{_esc(name)}</strong>'
            f' — corrected automatically'
            f'</li>'
        )

    return (
        f'<section class="auto-fixed">'
        f'<h2 class="section-title fixed-title">&#10003; Issues Corrected by <code>--fix</code></h2>'
        f'<ul class="fixed-list">{"".join(li_html)}</ul>'
        f'</section>'
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate(results: List[CheckResult], pdf_path: str, output_path: str) -> None:
    """Write a self-contained HTML accessibility report to *output_path*.

    Args:
        results:     List of CheckResult objects from the checker modules.
        pdf_path:    Path to the original PDF that was checked.
        output_path: Destination path for the HTML report file.
    """
    pdf_filename = _esc(os.path.basename(pdf_path))
    date_str = _esc(datetime.now().strftime("%B %d, %Y at %H:%M"))

    # --- counts ---
    n_pass   = sum(1 for r in results if r.status == CheckStatus.PASS)
    n_fail   = sum(1 for r in results if r.status == CheckStatus.FAIL)
    n_manual = sum(1 for r in results if r.status == CheckStatus.MANUAL)
    n_na     = sum(1 for r in results if r.status == CheckStatus.NA)
    n_total  = len(results)

    pct_pass = round(n_pass / n_total * 100) if n_total else 0

    # Compliance bar colour: green above 80%, amber 50-80, red below 50
    bar_colour = "#22c55e" if pct_pass >= 80 else ("#f59e0b" if pct_pass >= 50 else "#ef4444")
    bar_gradient = f"background: linear-gradient(90deg, {bar_colour} 0%, {bar_colour}cc 100%);"

    results_tables      = _render_results_tables(results)
    manual_section      = _render_manual_section(results)
    fixed_section       = _render_fixed_section(results)
    auto_fix_preview    = _render_auto_fix_preview(results)
    auto_fixed_summary  = _render_auto_fixed_summary(results)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>PDF Accessibility Report – {pdf_filename}</title>
<style>
{_CSS}
</style>
</head>
<body>

<!-- ===================== HEADER ===================== -->
<header class="site-header">
  <div style="max-width:1100px;margin:0 auto;">
    <h1>PDF Accessibility Checker &ndash; WCAG&nbsp;2.1 Level&nbsp;AA</h1>
    <div class="meta">
      <span>&#128196; <strong>{pdf_filename}</strong></span>
      <span>&#128197; Generated: {date_str}</span>
    </div>
  </div>
</header>

<!-- ===================== MAIN ===================== -->
<main class="page-wrap">

  <!-- ---- Summary dashboard ---- -->
  <h2 class="section-title">Summary</h2>
  <div class="card-grid">
    <div class="card pass">
      <span class="card-count">{n_pass}</span>
      <span class="card-label">Passed</span>
    </div>
    <div class="card fail">
      <span class="card-count">{n_fail}</span>
      <span class="card-label">Failed</span>
    </div>
    <div class="card manual">
      <span class="card-count">{n_manual}</span>
      <span class="card-label">Needs Review</span>
    </div>
    <div class="card na">
      <span class="card-count">{n_na}</span>
      <span class="card-label">Not Applicable</span>
    </div>
    <div class="card total">
      <span class="card-count">{n_total}</span>
      <span class="card-label">Total Checks</span>
    </div>
  </div>

  <!-- ---- Compliance bar ---- -->
  <div class="compliance-wrap">
    <div class="compliance-label">
      <span>Overall Compliance (passed checks)</span>
      <span>{pct_pass}%</span>
    </div>
    <div class="bar-track" role="progressbar"
         aria-valuenow="{pct_pass}" aria-valuemin="0" aria-valuemax="100"
         aria-label="Compliance: {pct_pass}%">
      <div class="bar-fill" style="width:{pct_pass}%;{bar_gradient}"></div>
    </div>
  </div>

  <!-- ---- Auto-fix preview (shown when --fix has NOT yet been run) ---- -->
  {auto_fix_preview}

  <!-- ---- Auto-fixed summary (shown when --fix was run) ---- -->
  {auto_fixed_summary}

  <!-- ---- Results by WCAG principle ---- -->
  <h2 class="section-title">Results by WCAG Criterion</h2>
  <p style="font-size:0.85rem;color:#64748b;margin-bottom:0.5rem;">
    Click any row with issues to expand details.
  </p>
  {results_tables}

  <!-- ---- Manual review ---- -->
  <h2 class="section-title">Items Requiring Manual Review</h2>
  {manual_section}

  <!-- ---- What was fixed ---- -->
  <h2 class="section-title">What Was Fixed Automatically</h2>
  {fixed_section}

</main>

<!-- ===================== FOOTER ===================== -->
<footer class="site-footer">
  Generated by pdf-ua-fixer &nbsp;|&nbsp;
  WCAG 2.1 reference:
  <a href="https://www.w3.org/TR/WCAG21/" target="_blank" rel="noopener">
    https://www.w3.org/TR/WCAG21/
  </a>
</footer>

<script>
{_JS}
</script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)
