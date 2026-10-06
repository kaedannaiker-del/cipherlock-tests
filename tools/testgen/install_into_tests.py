"""
Copy the generated test suite into tests/ so scripts/marking_script.py finds it.

This is an installer, not a runner: it never executes cipherlock.py and never
compares outputs. It only copies files.

The marking script discovers cases by taking the first four characters of each
filename in tests/<SH>/public/ins as the category (marking_script.py:1027), so a
generated file must start with a real category prefix. Generated names are
<category>_gen<NNNN>.txt (optionally with a sparg/onearg/thrarg suffix), which
keeps them clear of the shipped *_caseNN.txt names and never overwrites them.

Usage:
    python3 tools/testgen/install_into_tests.py [--check]
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC_ROOT = ROOT / "tests_generated"
DST_ROOT = ROOT / "tests"
KINDS = ("ins", "outs")


def install(check_only: bool = False, replace: bool = False) -> int:
    """Copy every generated case into tests/. Returns a process exit code."""
    if not SRC_ROOT.is_dir():
        print(f"error: {SRC_ROOT} does not exist; run generate.py first",
              file=sys.stderr)
        return 2

    copied = 0
    replaced = 0
    already = 0
    identical = 0
    conflicts: list[tuple[Path, Path]] = []

    for stage in sorted(p.name for p in SRC_ROOT.iterdir() if p.is_dir()):
        for kind in KINDS:
            src_dir = SRC_ROOT / stage / "public" / kind
            dst_dir = DST_ROOT / stage / "public" / kind
            if not src_dir.is_dir():
                continue
            if not dst_dir.is_dir():
                print(f"error: missing destination {dst_dir}", file=sys.stderr)
                return 2

            for src in sorted(src_dir.iterdir()):
                if not src.is_file():
                    continue
                # Refuse to clobber a file we did not generate.
                if not src.name[:4].isalpha() or "_gen" not in src.name:
                    conflicts.append((src, dst_dir / src.name))
                    continue
                dst = dst_dir / src.name
                if dst.exists():
                    if filecmp.cmp(src, dst, shallow=False):
                        identical += 1
                    else:
                        # The destination has our generated name and a matching
                        # source exists, so it is ours from a previous install.
                        # Only --replace may overwrite it.
                        if not replace or check_only:
                            conflicts.append((src, dst))
                        else:
                            shutil.copy2(src, dst)
                            replaced += 1
                    already += 1
                    continue
                if not check_only:
                    shutil.copy2(src, dst)
                copied += 1

    if conflicts:
        print("REFUSING to overwrite these files:", file=sys.stderr)
        for src, dst in conflicts[:20]:
            print(f"  {src.name} -> {dst}", file=sys.stderr)
        if len(conflicts) > 20:
            print(f"  ... and {len(conflicts) - 20} more", file=sys.stderr)
        print("Pass --replace to overwrite your own generated cases after a "
              "regeneration. Shipped *_caseNN.txt files are never touched.",
              file=sys.stderr)
        return 1

    verb = "would copy" if check_only else "copied"
    print(f"{verb} {copied} new file(s) into tests/")
    if replaced:
        print(f"  replaced {replaced} regenerated file(s)")
    print(f"  already present and byte-identical: {identical}")
    print(f"  total generated cases now visible to the marking script: "
          f"{copied + identical + replaced}")
    return 0


def prune_orphans() -> int:
    """Remove installed *_gen* files that no longer exist in tests_generated/.

    Regeneration can rename a case, which would otherwise leave the old file
    behind in tests/ where the marking script would still discover it. Only
    files carrying our generated marker are ever considered.
    """
    removed = 0
    for stage_dir in sorted(p for p in DST_ROOT.iterdir() if p.is_dir()):
        src_stage = SRC_ROOT / stage_dir.name
        for kind in KINDS:
            dst_dir = stage_dir / "public" / kind
            src_dir = src_stage / "public" / kind
            if not dst_dir.is_dir():
                continue
            expected = {p.name for p in src_dir.iterdir()} if src_dir.is_dir() \
                else set()
            for dst in sorted(dst_dir.iterdir()):
                if not dst.is_file() or "_gen" not in dst.name:
                    continue
                if dst.name not in expected:
                    dst.unlink()
                    removed += 1
    if removed:
        print(f"pruned {removed} orphaned generated file(s) no longer produced")
    else:
        print("no orphaned generated files")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report what would be copied, change nothing")
    parser.add_argument("--replace", action="store_true",
                        help="overwrite generated files that differ from "
                             "tests_generated/ (use after regenerating)")
    parser.add_argument("--no-prune", action="store_true",
                        help="keep installed generated files that are no longer "
                             "produced by the generator")
    args = parser.parse_args()
    status = install(check_only=args.check, replace=args.replace)
    if status == 0 and not args.check and not args.no_prune:
        prune_orphans()
    return status


if __name__ == "__main__":
    sys.exit(main())