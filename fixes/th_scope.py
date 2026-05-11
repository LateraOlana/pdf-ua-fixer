"""
Fix 2 — "Table header cells has no associated subcells".

PAC does not resolve ClassMap references when checking TH scope.
tagpdf stores TH scope as  /C /TH-col  (ClassMap only), which is invisible
to PAC.  This fix adds a direct  /A << /O /Table /Scope /Column >>  attribute
to every TH structure element alongside the existing ClassMap entry.
"""
import pikepdf
from pikepdf import Name, Array, Dictionary
from .utils import try_resolve


def _patch_node(node):
    """Recursively patch TH elements. Returns (patched, skipped)."""
    node = try_resolve(node)
    if not isinstance(node, pikepdf.Dictionary):
        return 0, 0

    patched = 0
    skipped = 0

    tag = node.get('/S')
    if tag is not None and str(tag) == '/TH':
        scope_dict = Dictionary(O=Name('/Table'), Scope=Name('/Column'))
        existing_a = node.get('/A')

        if existing_a is None:
            node['/A'] = scope_dict
            patched += 1
        else:
            has_scope = False
            if isinstance(existing_a, pikepdf.Dictionary):
                has_scope = existing_a.get('/Scope') is not None
            elif isinstance(existing_a, pikepdf.Array):
                for item in existing_a:
                    d = try_resolve(item)
                    if isinstance(d, pikepdf.Dictionary) and d.get('/Scope') is not None:
                        has_scope = True
                        break
            if has_scope:
                skipped += 1
            else:
                if isinstance(existing_a, pikepdf.Array):
                    existing_a.append(scope_dict)
                else:
                    node['/A'] = Array([existing_a, scope_dict])
                patched += 1

    kids = node.get('/K')
    if kids is not None:
        if isinstance(kids, pikepdf.Array):
            for kid in kids:
                p, s = _patch_node(try_resolve(kid))
                patched += p
                skipped += s
        elif isinstance(kids, pikepdf.Dictionary):
            p, s = _patch_node(kids)
            patched += p
            skipped += s

    return patched, skipped


def fix_th_scope(pdf):
    """
    Walk the structure tree of an open pikepdf.Pdf and patch all TH elements.
    Returns {'patched': int, 'skipped': int}.
    """
    try:
        struct_root = pdf.Root['/StructTreeRoot']
        patched, skipped = _patch_node(struct_root)
    except Exception:
        patched, skipped = 0, 0

    return {'patched': patched, 'skipped': skipped}
