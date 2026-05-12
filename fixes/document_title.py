"""
Fix — Document title missing (WCAG 2.4.2 Page Titled).

Sets the document title in both DocInfo (/Title) and XMP metadata (dc:title).
If no explicit title is supplied the filename stem is used as a fallback.
"""

from pathlib import Path

import pikepdf

DC_NS    = 'http://purl.org/dc/elements/1.1/'
DC_TITLE = f'{{{DC_NS}}}title'


def _infer_title(pdf: pikepdf.Pdf) -> str:
    """
    Try to derive a title from the PDF's filename.

    pikepdf exposes the path via ``pdf.filename`` when the file was opened
    from disk.  If that attribute is absent or empty, return an empty string
    so the caller can decide what to do.
    """
    filename = getattr(pdf, 'filename', None)
    if filename:
        return Path(filename).stem
    return ''


def fix(pdf: pikepdf.Pdf, title: str = None) -> int:
    """
    Ensure the PDF has a document title in both DocInfo and XMP metadata.

    Parameters
    ----------
    pdf:
        An open, writable pikepdf.Pdf instance.
    title:
        The title string to set.  When *None* the function first checks
        whether a title is already present; if one is found it returns 0
        (no change needed).  If no title exists it tries to infer one from
        ``pdf.filename``; if that is also unavailable it sets an empty string
        (which callers should treat as "still broken").

    Returns
    -------
    1 if the title was written (a change was made), 0 if the title was
    already present and *title* was not explicitly supplied.
    """
    # --- Read current values ------------------------------------------------
    current_docinfo: str = ''
    try:
        raw = pdf.docinfo.get('/Title')
        if raw is not None:
            current_docinfo = str(raw).strip()
    except Exception:
        pass

    current_xmp: str = ''
    try:
        with pdf.open_metadata() as meta:
            raw_xmp = meta.get(DC_TITLE)
            if raw_xmp is not None:
                current_xmp = str(raw_xmp).strip()
    except Exception:
        pass

    already_present = bool(current_docinfo) or bool(current_xmp)

    # --- If caller did not supply a title and one already exists, do nothing -
    if title is None and already_present:
        return 0

    # --- Resolve the title to write -----------------------------------------
    if title is None:
        title = _infer_title(pdf)
        # If we still have nothing, use whatever is already there (even empty)
        if not title:
            title = current_docinfo or current_xmp

    # --- Write DocInfo /Title ------------------------------------------------
    try:
        pdf.docinfo['/Title'] = title
    except Exception:
        # DocInfo may not exist; create a minimal one.
        pdf.docinfo = pikepdf.Dictionary(Title=pikepdf.String(title))

    # --- Write XMP dc:title --------------------------------------------------
    try:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta[DC_TITLE] = title
    except Exception:
        pass

    return 1
