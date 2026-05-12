"""
Fix — Language of page missing (WCAG 3.1.1 Language of Page).

Sets the /Lang entry in the PDF catalog (pdf.Root) to the supplied BCP-47
language tag.  Only writes when the value is absent or different from the
requested tag, making the fix idempotent.
"""

import pikepdf


def fix(pdf: pikepdf.Pdf, lang: str = 'en-US') -> int:
    """
    Ensure the PDF catalog has a /Lang entry set to *lang*.

    Parameters
    ----------
    pdf:
        An open, writable pikepdf.Pdf instance.
    lang:
        BCP-47 language tag to set (default ``"en-US"``).

    Returns
    -------
    1 if /Lang was written (a change was made), 0 if it was already set to
    the requested value.
    """
    current = None
    try:
        raw = pdf.Root.get('/Lang')
        if raw is not None:
            current = str(raw).strip()
    except Exception:
        pass

    if current == lang:
        return 0

    pdf.Root['/Lang'] = pikepdf.String(lang)
    return 1
