"""
Fix — Missing /Alt text on Figure elements (WCAG 1.1.1 Non-text Content).

Provides two entry points:

fix(pdf, placeholder)
    Adds a placeholder /Alt string to every Figure structure element that has
    no /Alt attribute at all.  Returns the number of elements patched.

fix_artifacts(pdf)
    Stub for marking decorative Figure elements with an empty /Alt string.
    Reliable automated detection of "decorative" images requires visual
    analysis or human judgment, so this function always returns 0.  A human
    reviewer should identify decorative figures and set their /Alt to "" (an
    empty string) manually, or with a targeted script once the set is known.
"""

import pikepdf

from checks.base import get_struct_tree_elements, try_resolve


def fix(pdf: pikepdf.Pdf, placeholder: str = "Image") -> int:
    """
    Add a placeholder /Alt attribute to every Figure element that lacks one.

    Parameters
    ----------
    pdf:
        An open, writable pikepdf.Pdf instance.
    placeholder:
        The string to use as the alternative-text placeholder.  Defaults to
        ``"Image"``.  Replace placeholder values with meaningful descriptions
        before publishing the document.

    Returns
    -------
    Number of Figure elements that received a new /Alt attribute.
    """
    figures = get_struct_tree_elements(pdf, "/Figure")
    patched = 0

    for figure in figures:
        alt = figure.get("/Alt")
        if alt is None:
            figure["/Alt"] = pikepdf.String(placeholder)
            patched += 1

    return patched


def fix_artifacts(pdf: pikepdf.Pdf) -> int:
    """
    Mark decorative Figure elements with an empty /Alt string.

    Detecting whether a Figure is purely decorative (i.e., contains only path
    drawing operations with no image XObjects and conveys no meaningful content)
    cannot be done reliably through automated content-stream analysis alone.
    Factors such as vector art that represents real content, invisible clipping
    paths, and Form XObjects that embed images at arbitrary nesting depths all
    make a purely programmatic determination error-prone.

    This function is a stub that always returns 0.  To mark decorative figures:
    1. Identify them through manual review or an accessibility audit tool.
    2. Set their /Alt attribute to an empty pikepdf.String (``pikepdf.String("")``).
       An empty /Alt signals to assistive technology that the figure is
       decorative and should be skipped.

    Parameters
    ----------
    pdf:
        An open, writable pikepdf.Pdf instance (not modified by this stub).

    Returns
    -------
    Always 0 — no elements are modified.
    """
    # Manual review required; see docstring above.
    return 0
