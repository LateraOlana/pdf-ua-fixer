"""Shared helpers for PDF content-stream parsing and serialization."""
import pikepdf

MC_OPEN       = frozenset({b'BMC', b'BDC'})
MC_CLOSE      = frozenset({b'EMC'})
PATH_BUILDERS = frozenset({b'm', b'l', b'c', b'v', b'y', b'h', b're'})
PATH_PAINTERS = frozenset({b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*', b'n'})


def try_resolve(obj):
    """Dereference a PDF indirect reference.

    Dictionary-key access in pikepdf auto-resolves; array items may still be
    indirect references.  Calling .get_object() on a concrete type raises
    ValueError (pikepdf __getattr__ intercepts it as a key lookup), so we
    catch both ValueError and AttributeError.
    """
    try:
        return obj.get_object()
    except (AttributeError, ValueError):
        return obj


def operand_bytes(obj):
    """Serialize a pikepdf operand to its PDF content-stream token bytes."""
    if isinstance(obj, pikepdf.Name):
        return str(obj).encode()
    if isinstance(obj, pikepdf.String):
        return b'<' + bytes(obj).hex().encode() + b'>'
    if isinstance(obj, pikepdf.Array):
        inner = b' '.join(operand_bytes(x) for x in obj)
        return b'[' + inner + b']'
    if isinstance(obj, pikepdf.Dictionary):
        parts = [b'<<']
        for k, v in obj.items():
            parts.append(str(k).encode())
            parts.append(operand_bytes(v))
        parts.append(b'>>')
        return b' '.join(parts)
    try:
        return str(obj).encode()
    except Exception:
        return b'0'


def instructions_to_bytes(instructions):
    """Serialize a list of (operands, operator) tuples to content-stream bytes."""
    parts = []
    for operands, operator in instructions:
        tokens = [operand_bytes(op) for op in operands]
        tokens.append(bytes(operator))
        parts.append(b' '.join(tokens))
    return b'\n'.join(parts)
