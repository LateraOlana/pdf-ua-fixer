# pdf-ua-fixer

Post-process a PDF to fix PDF/UA-1 accessibility errors reported by PAC (PDF Accessibility Checker).

## What it fixes

| # | PAC error | Cause | Fix |
|---|-----------|-------|-----|
| 1 | Second path object not tagged | booktabs `\toprule`/`\midrule`/`\bottomrule` emit raw path ops outside any marked-content block | Wrap each untagged path sequence in `/Artifact BMC … EMC` |
| 2 | Table header cells has no associated subcells | tagpdf stores TH scope via ClassMap only (`/C /TH-col`); PAC cannot resolve ClassMap refs | Add direct `/A << /O /Table /Scope /Column >>` to every TH structure element |
| 3 | Tagged content present inside an artifact | tcolorbox wraps the entire coloured box (frame + text) in a single `/Artifact BMC … EMC` | Remove the outer artifact wrapper; re-wrap only the path drawing ops individually |
| 4 | PDF/UA identifier missing | XMP metadata lacks `pdfuaid:part = 1` | Write `pdfuaid:part = 1` under `xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/"` |

## Requirements

```
pip install -r requirements.txt
```

Requires Python 3.9+, `pikepdf >= 10.0`, `pypdf >= 4.0`.

## Usage

```bash
# Fix a PDF — saves to dissertation_fixed.pdf by default
python fix_pdf.py dissertation.pdf

# Specify output file
python fix_pdf.py dissertation.pdf --output dissertation_ua.pdf

# Modify in place
python fix_pdf.py dissertation.pdf --inplace

# Verify fixes
python verify_pdf.py dissertation_fixed.pdf
```

## Project layout

```
pdf-ua-fixer/
├── fix_pdf.py          ← main entry point
├── verify_pdf.py       ← verification checks
├── requirements.txt
└── fixes/
    ├── utils.py            shared helpers (parse/serialize, try_resolve)
    ├── untagged_paths.py   Fix 1 — wrap untagged path ops as Artifacts
    ├── th_scope.py         Fix 2 — add /Scope to TH structure elements
    ├── artifact_content.py Fix 3 — tagged content inside Artifact blocks
    └── pdfua_metadata.py   Fix 4 — PDF/UA XMP identifier
```

## Notes

- The fixes are non-destructive: they only add/adjust PDF markup without changing visible content or fonts.
- Run `fix_pdf.py` once per PDF build. If you rebuild the PDF from LaTeX, run it again.
- Tested on PDFs produced by pdflatex + tagpdf (TeX Live 2025).
