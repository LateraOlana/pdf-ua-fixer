"""
Fix 1 — "Second path object not tagged" / untagged path sequences.

Scans every page content stream for path-drawing sequences (m/l/c/re/…/S/f/…)
that sit outside any marked-content block (MC depth == 0) and wraps each one
in  /Artifact BMC … EMC  so PDF readers treat it as decorative.

Typical source: booktabs toprule / midrule / bottomrule / cmidrule.
"""
import pikepdf
from pikepdf import Name, Operator
from .utils import MC_OPEN, MC_CLOSE, PATH_BUILDERS, PATH_PAINTERS, instructions_to_bytes


def _wrap_paths(instructions):
    """Return (new_instructions, count_wrapped)."""
    out = []
    mc_depth = 0
    path_buf = []
    in_path  = False
    wrapped  = 0

    def flush(wrap):
        nonlocal wrapped
        if not path_buf:
            return
        if wrap:
            out.append(([Name('/Artifact')], Operator('BMC')))
            out.extend(path_buf)
            out.append(([], Operator('EMC')))
            wrapped += 1
        else:
            out.extend(path_buf)
        path_buf.clear()

    for operands, operator in instructions:
        op = bytes(operator)

        if op in MC_OPEN:
            flush(mc_depth == 0)
            mc_depth += 1
            out.append((operands, operator))
            continue

        if op in MC_CLOSE:
            flush(mc_depth == 0)
            mc_depth = max(0, mc_depth - 1)
            out.append((operands, operator))
            continue

        if mc_depth == 0:
            if op in PATH_BUILDERS:
                in_path = True
                path_buf.append((operands, operator))
                continue
            if op in PATH_PAINTERS and in_path:
                path_buf.append((operands, operator))
                flush(True)
                in_path = False
                continue
            if in_path:
                flush(True)
                in_path = False

        out.append((operands, operator))

    if in_path:
        flush(mc_depth == 0)

    return out, wrapped


def fix_untagged_paths(pdf):
    """
    Process all pages in an open pikepdf.Pdf.
    Returns {'pages': int, 'wrapped': int}.
    """
    pages_modified = 0
    total_wrapped  = 0

    for page in pdf.pages:
        try:
            instructions = list(pikepdf.parse_content_stream(page))
            new_instr, n = _wrap_paths(instructions)
            if n > 0:
                page['/Contents'] = pdf.make_stream(instructions_to_bytes(new_instr))
                pages_modified += 1
                total_wrapped  += n
        except Exception as e:
            pass  # leave page unchanged on error

    return {'pages': pages_modified, 'wrapped': total_wrapped}
