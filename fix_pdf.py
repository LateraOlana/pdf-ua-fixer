#!/usr/bin/env python3
"""
Fix PDF/UA (PDF/UA-1) accessibility issues for PAC compliance.

Usage
-----
  # Fix in-place
  python fix_pdf.py dissertation.pdf

  # Save to a new file (default: <name>_fixed.pdf)
  python fix_pdf.py dissertation.pdf --output dissertation_ua.pdf

Fixes applied
-------------
  1. Untagged path sequences (booktabs rules, decorative lines) wrapped as Artifacts
  2. TH structure elements given a direct /A /Scope /Column attribute
  3. Tagged content nested inside Artifact blocks restructured
  4. PDF/UA-1 XMP identifier (pdfuaid:part = 1) added to metadata
"""
import sys
import shutil
import argparse
import traceback
from pathlib import Path

import pikepdf

from fixes.untagged_paths   import fix_untagged_paths
from fixes.th_scope         import fix_th_scope
from fixes.artifact_content import fix_artifact_content
from fixes.pdfua_metadata   import fix_pdfua_metadata


def main():
    parser = argparse.ArgumentParser(
        description='Fix PDF/UA accessibility issues (PAC-compatible)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('pdf', help='Path to the input PDF')
    parser.add_argument(
        '--output', '-o', metavar='OUT',
        help='Output path (default: <input>_fixed.pdf)',
    )
    parser.add_argument(
        '--inplace', action='store_true',
        help='Modify the PDF in place instead of creating a copy',
    )
    args = parser.parse_args()

    src = Path(args.pdf)
    if not src.exists():
        print(f"Error: file not found: {src}", file=sys.stderr)
        return 1

    if args.inplace:
        dst = src
    elif args.output:
        dst = Path(args.output)
    else:
        dst = src.with_name(src.stem + '_fixed' + src.suffix)

    if not args.inplace:
        shutil.copy2(src, dst)
        print(f"Copied  {src.name}  →  {dst.name}")

    print(f"\nProcessing: {dst}\n{'─' * 50}")

    try:
        with pikepdf.open(dst, allow_overwriting_input=True) as pdf:
            print(f"Pages: {len(pdf.pages)}\n")

            # ── Fix 1 ──────────────────────────────────────────────────────────
            print("[1/4] Marking untagged path sequences as Artifacts ...")
            r1 = fix_untagged_paths(pdf)
            print(f"      Pages modified : {r1['pages']}")
            print(f"      Artifact blocks: {r1['wrapped']}\n")

            # ── Fix 2 ──────────────────────────────────────────────────────────
            print("[2/4] Adding direct /Scope to TH structure elements ...")
            r2 = fix_th_scope(pdf)
            print(f"      TH cells patched        : {r2['patched']}")
            print(f"      TH cells already correct: {r2['skipped']}\n")

            # ── Fix 3 ──────────────────────────────────────────────────────────
            print("[3/4] Fixing tagged content inside Artifact blocks ...")
            r3 = fix_artifact_content(pdf)
            print(f"      Pages fixed              : {r3['pages']}")
            print(f"      Artifact wrappers removed: {r3['unwrapped']}")
            print(f"      Path sequences re-wrapped: {r3['rewrapped']}\n")

            # ── Fix 4 ──────────────────────────────────────────────────────────
            print("[4/4] Adding PDF/UA-1 XMP identifier ...")
            r4 = fix_pdfua_metadata(pdf)
            status = "added" if r4['added'] else "already present"
            print(f"      pdfuaid:part = {r4['value']}  ({status})\n")

            print("Saving ...")
            pdf.save(dst)

    except Exception:
        traceback.print_exc()
        return 1

    print(f"{'─' * 50}")
    print(f"Done.  Output: {dst}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
