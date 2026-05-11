#!/usr/bin/env python3
"""
Verify PDF/UA accessibility fixes in a PDF.

Usage: python verify_pdf.py dissertation.pdf
"""
import sys
from pathlib import Path

import pikepdf
from pypdf import PdfReader

from fixes.utils import try_resolve

PDFUAID_NS  = 'http://www.aiim.org/pdfua/ns/id/'
PDFUAID_KEY = f'{{{PDFUAID_NS}}}part'


def check_pdfua_id(pdf_path):
    with pikepdf.open(pdf_path) as pdf:
        with pdf.open_metadata() as meta:
            val = meta.get(PDFUAID_KEY)
    ok = val == '1'
    print(f"PDF/UA identifier  pdfuaid:part = {val!r}  {'[PASS]' if ok else '[FAIL]'}")
    return ok


def check_th_scope(pdf_path):
    reader = PdfReader(str(pdf_path))
    root   = reader.trailer['/Root'].get_object()
    struct = root['/StructTreeRoot'].get_object()

    with_scope = [0]
    no_scope   = [0]
    tables     = [0]

    def get_scope(a):
        if not a:
            return None
        try:
            a = a.get_object()
        except Exception:
            pass
        if hasattr(a, 'keys'):
            return a.get('/Scope')
        if hasattr(a, '__iter__'):
            for item in a:
                try:
                    item = item.get_object()
                    s = item.get('/Scope')
                    if s:
                        return s
                except Exception:
                    pass
        return None

    def walk(node):
        if hasattr(node, 'get_object'):
            node = node.get_object()
        if not hasattr(node, 'keys'):
            return
        tag = str(node.get('/S', ''))
        if tag == '/Table':
            tables[0] += 1
        elif tag == '/TH':
            if get_scope(node.get('/A')):
                with_scope[0] += 1
            else:
                no_scope[0] += 1
        kids = node.get('/K')
        if not kids:
            return
        if not isinstance(kids, list):
            kids = [kids]
        for k in kids:
            walk(k)

    walk(struct)

    ok = no_scope[0] == 0 and with_scope[0] > 0
    print(f"TH /Scope          {with_scope[0]} with scope, {no_scope[0]} missing"
          f"  (tables: {tables[0]})  {'[PASS]' if ok else '[FAIL]'}")
    return ok


def check_artifact_content(pdf_path):
    """Count /Artifact BMC blocks that still contain inner BDC/BMC."""
    bad_pages = []

    with pikepdf.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                instructions = list(pikepdf.parse_content_stream(page))
            except Exception:
                continue

            depth       = 0
            in_artifact = False
            artifact_depth = 0

            for operands, operator in instructions:
                op = bytes(operator)
                is_artifact = (op in {b'BMC', b'BDC'} and
                               bool(operands) and
                               str(operands[0]) == '/Artifact')

                if op in {b'BMC', b'BDC'}:
                    if is_artifact and depth == 0:
                        in_artifact    = True
                        artifact_depth = depth
                    elif in_artifact and depth > artifact_depth:
                        bad_pages.append(i + 1)
                        in_artifact = False
                    depth += 1
                elif op == b'EMC':
                    depth = max(0, depth - 1)
                    if in_artifact and depth == artifact_depth:
                        in_artifact = False

    ok = len(bad_pages) == 0
    if ok:
        print(f"Artifact content   no tagged content inside artifacts  [PASS]")
    else:
        print(f"Artifact content   tagged content found on pages: {bad_pages}  [FAIL]")
    return ok


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <pdf>")
        return 1

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: not found: {pdf_path}", file=sys.stderr)
        return 1

    print(f"Verifying: {pdf_path}\n{'─' * 50}")

    results = [
        check_pdfua_id(pdf_path),
        check_th_scope(pdf_path),
        check_artifact_content(pdf_path),
    ]

    print(f"{'─' * 50}")
    if all(results):
        print("All checks PASSED")
    else:
        print(f"{results.count(False)} check(s) FAILED")
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
