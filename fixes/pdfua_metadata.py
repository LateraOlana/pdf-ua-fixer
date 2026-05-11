"""
Fix 4 — "PDF/UA identifier missing".

PAC requires the XMP metadata to declare:
  xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/"
  pdfuaid:part = 1
"""

PDFUAID_NS  = 'http://www.aiim.org/pdfua/ns/id/'
PDFUAID_KEY = f'{{{PDFUAID_NS}}}part'


def fix_pdfua_metadata(pdf):
    """
    Set pdfuaid:part = '1' in the XMP metadata of an open pikepdf.Pdf.
    Returns {'value': str, 'added': bool}.
    """
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        current = meta.get(PDFUAID_KEY)
        already_present = current == '1'
        meta[PDFUAID_KEY] = '1'

    return {'value': '1', 'added': not already_present}
