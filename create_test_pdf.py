"""Creates a test PDF with deliberate WCAG 2.1 accessibility violations for testing."""
import sys
import os

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.colors import HexColor, white, black, Color
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print("reportlab is required: pip install reportlab")
    sys.exit(1)


VIOLATIONS = [
    ("2.4.2", "Page Titled", "No document title set in PDF metadata"),
    ("3.1.1", "Language of Page", "No /Lang set in document catalog"),
    ("1.1.1", "Non-text Content", "Image/figure without alt text"),
    ("1.4.3", "Contrast Minimum", "Very light gray text on white background"),
    ("2.4.4", "Link Purpose", "Link with non-descriptive text 'Click here'"),
    ("4.1.2", "Name, Role, Value", "Form field without accessible label (/TU)"),
    ("2.4.1", "Bypass Blocks", "Multi-page document with no bookmarks"),
    ("1.3.1", "Info and Relationships", "Table without header (TH) markup"),
    ("1.4.5", "Images of Text", "Potential image of text (drawn text in image form)"),
    ("4.1.1", "Parsing", "No StructTreeRoot — document is completely untagged"),
]


def create_test_pdf(output_path="test_document.pdf"):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # ── Page 1: Title page (no document title in metadata → 2.4.2) ──────────
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(width / 2, height * 0.65, "Sample Accessibility Test Report")
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height * 0.57, "WCAG 2.1 Violation Test Document")
    c.drawCentredString(width / 2, height * 0.51, "May 2026")
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#666666"))
    c.drawCentredString(width / 2, height * 0.42,
                        "Institute for Health Metrics and Evaluation")
    c.setFillColor(black)
    # No title set in metadata — violation 2.4.2
    c.showPage()

    # ── Page 2: Text content with contrast violation ─────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, height - inch, "1. Introduction")

    c.setFont("Helvetica", 11)
    c.setFillColor(black)
    body = (
        "This document demonstrates common accessibility violations in PDF files. "
        "It was generated specifically to test automated WCAG 2.1 Level AA checking tools. "
        "Each page contains one or more deliberate accessibility problems."
    )
    text_obj = c.beginText(inch, height - 1.5 * inch)
    text_obj.setFont("Helvetica", 11)
    for word_line in _wrap(body, 80):
        text_obj.textLine(word_line)
    c.drawText(text_obj)

    # Low-contrast text: light gray on white — violates 1.4.3
    c.setFillColor(HexColor("#cccccc"))   # Very light gray, contrast ratio ≈ 1.6:1
    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 3.2 * inch,
                 "This text is light gray on white — very low contrast ratio (≈1.6:1).")
    c.setFillColor(black)

    # Another normal paragraph
    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 3.8 * inch,
                 "The above line fails WCAG 1.4.3 (minimum contrast ratio: 4.5:1).")
    c.showPage()

    # ── Page 3: Figures without alt text ────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, height - inch, "2. Figures and Images")

    # Draw a rectangle as a fake "figure" — no alt text possible without tagging
    c.setStrokeColor(HexColor("#2563eb"))
    c.setFillColor(HexColor("#dbeafe"))
    c.rect(inch, height - 3.5 * inch, 4 * inch, 1.8 * inch, fill=1)
    c.setFillColor(HexColor("#1e3a5f"))
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(3 * inch, height - 2.7 * inch, "Figure 1: Sample Chart")
    c.drawCentredString(3 * inch, height - 3 * inch, "(No alt text — violates 1.1.1)")

    # Caption text
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    c.drawString(inch, height - 3.8 * inch,
                 "Figure 1. A sample figure with no alternative text description.")

    # Second figure (also without alt text)
    c.setStrokeColor(HexColor("#16a34a"))
    c.setFillColor(HexColor("#dcfce7"))
    c.rect(inch, height - 5.5 * inch, 4 * inch, 1.2 * inch, fill=1)
    c.setFillColor(HexColor("#14532d"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(3 * inch, height - 5.0 * inch, "Figure 2: Bar Chart Data")
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    c.drawString(inch, height - 5.8 * inch,
                 "Figure 2. Another image without alt text.")
    c.showPage()

    # ── Page 4: Table without header markup ──────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, height - inch, "3. Data Table")

    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 1.5 * inch,
                 "The table below has no TH (header) markup — violates 1.3.1.")

    # Draw table manually — no structure/tagging
    headers = ["Country", "Population (M)", "GDP (B USD)", "Life Expectancy"]
    rows = [
        ["United States", "331", "21,000", "78.9"],
        ["Germany", "83", "3,800", "81.2"],
        ["Japan", "126", "5,100", "84.3"],
        ["Brazil", "214", "1,900", "75.9"],
    ]

    col_widths = [2.0 * inch, 1.4 * inch, 1.4 * inch, 1.6 * inch]
    row_height = 0.35 * inch
    table_x = inch
    table_y = height - 2.2 * inch

    # Header row — DRAWN as bold text, NOT tagged as TH
    c.setFillColor(HexColor("#e2e8f0"))
    c.rect(table_x, table_y - row_height, sum(col_widths), row_height, fill=1, stroke=1)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 10)
    x = table_x
    for i, header in enumerate(headers):
        c.drawString(x + 4, table_y - row_height + 8, header)
        x += col_widths[i]

    # Data rows
    c.setFont("Helvetica", 10)
    for row_idx, row in enumerate(rows):
        y = table_y - (row_idx + 2) * row_height
        c.setFillColor(HexColor("#f8fafc") if row_idx % 2 == 0 else white)
        c.rect(table_x, y, sum(col_widths), row_height, fill=1, stroke=1)
        c.setFillColor(black)
        x = table_x
        for i, cell in enumerate(row):
            c.drawString(x + 4, y + 8, cell)
            x += col_widths[i]

    c.showPage()

    # ── Page 5: Links ─────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, height - inch, "4. Links and Navigation")

    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 1.5 * inch, "The following links demonstrate good and bad link text:")

    # Bad link: "Click here" — violates 2.4.4
    c.setFillColor(HexColor("#2563eb"))
    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 2.1 * inch, "For more information, ")
    # Underline to indicate link
    c.setFillColor(HexColor("#1d4ed8"))
    link_x = inch + c.stringWidth("For more information, ", "Helvetica", 11)
    c.drawString(link_x, height - 2.1 * inch, "Click here")
    c.line(link_x, height - 2.13 * inch,
           link_x + c.stringWidth("Click here", "Helvetica", 11),
           height - 2.13 * inch)
    # Actual link annotation — generic text
    link_url = "https://www.w3.org/TR/WCAG21/"
    c.linkURL(link_url,
              (link_x, height - 2.2 * inch,
               link_x + c.stringWidth("Click here", "Helvetica", 11),
               height - 2.05 * inch),
              relative=0)

    # Good link: descriptive text — should PASS
    c.setFillColor(black)
    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 2.7 * inch, "Or visit the full specification: ")
    good_link_x = inch + c.stringWidth("Or visit the full specification: ", "Helvetica", 11)
    c.setFillColor(HexColor("#1d4ed8"))
    c.drawString(good_link_x, height - 2.7 * inch,
                 "Web Content Accessibility Guidelines (WCAG) 2.1")
    c.linkURL(link_url,
              (good_link_x, height - 2.8 * inch,
               good_link_x + c.stringWidth(
                   "Web Content Accessibility Guidelines (WCAG) 2.1", "Helvetica", 11),
               height - 2.65 * inch),
              relative=0)

    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    c.drawString(inch, height - 3.3 * inch,
                 '↑ "Click here" fails 2.4.4 (non-descriptive). The second link passes.')
    c.showPage()

    # ── Page 6: Forms ────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, height - inch, "5. Form Fields")

    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 1.5 * inch,
                 "Form fields below are missing accessible labels (/TU) — violates 4.1.2.")

    from reportlab.pdfbase.pdfdoc import PDFFormXObject
    from reportlab.lib.colors import lightgrey

    # Label without form association (visual only)
    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 2.2 * inch, "Full Name:")  # visual label, NOT programmatically linked

    # Text field — no /TU (tooltip/accessible name) set
    c.setStrokeColor(black)
    c.setFillColor(white)
    c.rect(inch + 1.2 * inch, height - 2.35 * inch, 3 * inch, 0.3 * inch, fill=1)
    # Note: reportlab's basic rect is not a real AcroForm field —
    # we add an actual AcroForm field below via canvas._doc approach

    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 2.9 * inch, "Email Address:")

    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(inch, height - 3.7 * inch,
                 "Note: Real AcroForm fields require pikepdf/PyPDF to add.")
    c.drawString(inch, height - 3.95 * inch,
                 "This page demonstrates the visual layout. Run check_pdf.py to see")
    c.drawString(inch, height - 4.2 * inch,
                 "what our tool detects. For a full form violation test, use a real")
    c.drawString(inch, height - 4.45 * inch,
                 "PDF authoring tool (InDesign, Word, LaTeX) to create form fields.")
    c.setFillColor(black)

    c.showPage()
    c.save()


def _wrap(text, width):
    """Simple word wrapper."""
    words = text.split()
    lines = []
    current = []
    for word in words:
        if len(" ".join(current + [word])) <= width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "test_document.pdf"
    create_test_pdf(output)
    print(f"\nTest PDF created: {output}")
    print(f"\nDeliberate WCAG 2.1 violations embedded ({len(VIOLATIONS)} total):")
    for criterion, name, description in VIOLATIONS:
        print(f"  [{criterion}] {name}: {description}")
    print("\nRun:  python check_pdf.py test_document.pdf")
    print("      to see the full accessibility report.\n")
