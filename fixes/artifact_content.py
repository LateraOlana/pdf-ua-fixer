"""
Fix 3 — "Tagged content present inside an artifact".

tcolorbox (and similar environments) emit a single /Artifact BMC…EMC wrapper
that encloses both the box background/border paths AND the tagged text inside
the box.  PDF/UA-1 forbids tagged content nested inside an artifact.

Fix: find every /Artifact BMC…EMC block that contains inner BDC/BMC markers,
remove the outer artifact wrapper, then re-wrap only the pure path-drawing
sequences as individual /Artifact blocks (reuses the same logic as Fix 1).
"""
import pikepdf
from pikepdf import Name, Operator
from .utils import MC_OPEN, MC_CLOSE, PATH_BUILDERS, PATH_PAINTERS, instructions_to_bytes


def _is_artifact_open(operands, operator):
    op = bytes(operator)
    return op in MC_OPEN and bool(operands) and str(operands[0]) == '/Artifact'


def _unwrap(instructions):
    """
    Remove outer /Artifact wrappers that contain inner BDC/BMC.
    Recurses to handle nested cases.
    Returns (new_instructions, count_removed).
    """
    result   = []
    removed  = 0
    i = 0

    while i < len(instructions):
        operands, operator = instructions[i]

        if _is_artifact_open(operands, operator):
            block = []
            depth = 1
            j = i + 1
            while j < len(instructions):
                ops2, op2 = instructions[j]
                op2b = bytes(op2)
                if op2b in MC_OPEN:
                    depth += 1
                elif op2b in MC_CLOSE:
                    depth -= 1
                    if depth == 0:
                        break
                block.append((ops2, op2))
                j += 1

            has_inner_mc = any(bytes(op2) in MC_OPEN for _, op2 in block)

            if has_inner_mc:
                inner, n = _unwrap(block)
                result.extend(inner)
                removed += 1 + n
            else:
                result.append((operands, operator))
                result.extend(block)
                result.append(([], Operator('EMC')))

            i = j + 1
        else:
            result.append((operands, operator))
            i += 1

    return result, removed


def _rewrap_paths(instructions):
    """Wrap untagged path sequences in /Artifact BMC…EMC (same as Fix 1)."""
    out      = []
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


def fix_artifact_content(pdf):
    """
    Process all pages of an open pikepdf.Pdf.
    Returns {'pages': int, 'unwrapped': int, 'rewrapped': int}.
    """
    pages_fixed     = 0
    total_unwrapped = 0
    total_rewrapped = 0

    for page in pdf.pages:
        try:
            instructions = list(pikepdf.parse_content_stream(page))

            cleaned, n_unwrapped = _unwrap(instructions)
            if n_unwrapped == 0:
                continue

            final, n_rewrapped = _rewrap_paths(cleaned)

            page['/Contents'] = pdf.make_stream(instructions_to_bytes(final))
            pages_fixed     += 1
            total_unwrapped += n_unwrapped
            total_rewrapped += n_rewrapped
        except Exception:
            pass

    return {'pages': pages_fixed, 'unwrapped': total_unwrapped, 'rewrapped': total_rewrapped}
