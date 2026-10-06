#!/usr/bin/env python3
"""Show a single generated test case, or replay a whole stage.

Examples::

    python3 tools/testgen/show_test.py SH5 mapp_gen0001
    python3 tools/testgen/show_test.py mapp_gen0001        # stage auto-detected
    python3 tools/testgen/show_test.py --list --stage SH8
    python3 tools/testgen/show_test.py --list --category crck
    python3 tools/testgen/show_test.py --all --stage SH4

``--all`` prints one ``<name> : passed`` line per test and, for a failure, an
indented reason plus the first differing line::

    mapp_gen0001 : passed
    prmt_gen0012 : FAILED
        reason: output mismatch
        line 14:
          expected: '1 │ 1122 │ 123456 │ Willow   │ UFM │ 1  │'
          got:      '1 │ 1122 │ 123456 │ Willow   │ UFM │ 2  │'

With no ``--all`` it prints the stored input, the expected stdout, and the
transcript recomputed by the oracle, then reports whether the two agree.

Nothing here touches ``src/``; the recomputed transcript comes from
``tools/testgen/oracle.py``.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle  # noqa: E402
from verify_generated import SH_ARGS, OUT_ROOT, sparg_check  # noqa: E402

MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "MANIFEST.csv")


def load_confidence() -> dict[tuple[str, str], str]:
    if not os.path.isfile(MANIFEST):
        return {}
    with open(MANIFEST, encoding="utf-8", newline="") as fh:
        return {(r["sh"], r["test"]): r["confidence"] for r in csv.DictReader(fh)}


def iter_tests(stage: str | None, category: str | None):
    stages = [stage] if stage else list(SH_ARGS)
    for sh in stages:
        pattern = os.path.join(OUT_ROOT, sh, "public", "ins", "*.txt")
        for path in sorted(glob.glob(pattern)):
            name = os.path.basename(path)[:-4]
            if category and not name.startswith(category):
                continue
            yield sh, name, path


def locate(name: str) -> list[tuple[str, str, str]]:
    return [(sh, n, p) for sh, n, p in iter_tests(None, None) if n == name]


def recompute(sh: str, name: str, ins: str) -> str:
    """Mirror verify_public: ``argc`` pairs are an SH2-stage check."""
    args = sparg_check(name, SH_ARGS[sh])
    if name.startswith("argc"):
        oracle.validate_args(args)
        return ""
    return oracle.run_args(args, ins)


def first_difference(expected: str, got: str) -> tuple[int, str, str] | None:
    """Return ``(line_no, expected_line, got_line)`` for the first difference.

    Same convention as the diff loop in ``verify_public.py``, so the reported
    line number means the same thing in all three tools. ``None`` means the
    two transcripts are identical.
    """
    exp_lines = expected.split("\n")
    got_lines = got.split("\n")
    for i in range(max(len(exp_lines), len(got_lines))):
        e = exp_lines[i] if i < len(exp_lines) else "<missing>"
        g = got_lines[i] if i < len(got_lines) else "<missing>"
        if e != g:
            return i + 1, e, g
    return None


def show(sh: str, name: str, path: str, confidence: dict) -> bool:
    with open(path, encoding="utf-8") as fh:
        ins = fh.read()
    out_path = os.path.join(OUT_ROOT, sh, "public", "outs", name + ".txt")
    with open(out_path, encoding="utf-8") as fh:
        stored = fh.read()
    try:
        got = recompute(sh, name, ins)
        ok = got == stored
        error = None
    except Exception as exc:  # noqa: BLE001 - report, do not hide
        got, ok, error = "", False, f"{type(exc).__name__}: {exc}"

    args = sparg_check(name, SH_ARGS[sh])
    args_text = " ".join(args) if args else "(no args)"
    print(f"{os.path.join('tests_generated', sh, 'public', 'ins', name + '.txt')}")
    print(f"  stage       {sh}")
    print(f"  category    {name[:4]}")
    print(f"  args        {args_text}"
          + (f"   confidence {confidence[(sh, name)]}"
             if (sh, name) in confidence else ""))
    print(f"  input       {len(ins)} bytes, "
          f"{len(ins.rstrip(chr(10)).split(chr(10)))} line(s)")
    print(f"  expected    {len(stored)} bytes")
    print("\n===== INPUT =====")
    print(ins, end="" if ins.endswith("\n") else "\n")
    print("\n===== EXPECTED STDOUT =====")
    print(stored, end="" if stored.endswith("\n") else "\n")
    if error:
        print(f"\n===== ORACLE RAISED =====\n{error}")
    print("\n===== RECOMPUTED =====")
    print("matches stored output" if ok else "MISMATCH", end="")
    print("\n" if ok else "\n")
    if not ok and not error and got != stored:
        print(got, end="" if got.endswith("\n") else "\n")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse
                                     .RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="*",
                        help="stage and/or test name, e.g. SH5 mapp_gen0001")
    parser.add_argument("--stage", help="restrict to one stage, e.g. SH5")
    parser.add_argument("--category", help="restrict to a 4-letter category")
    parser.add_argument("--list", action="store_true",
                        help="list matching test names instead of showing one")
    parser.add_argument("--all", action="store_true",
                        help="replay every matching test, printing one "
                             "'<name> : passed' line each, with reason and "
                             "first differing line on failure")
    args = parser.parse_args()

    confidence = load_confidence()

    if args.list:
        found = iter_tests(args.stage, args.category)
        for sh, name, _ in found:
            print(f"{sh} {name}")
        return 0

    stage, name = None, None
    if len(args.target) == 2:
        stage, name = args.target
        if stage not in SH_ARGS:
            print(f"unknown stage {stage!r}; expected one of "
                  f"{', '.join(SH_ARGS)}", file=sys.stderr)
            return 2
    elif len(args.target) == 1:
        name = args.target[0]
    elif args.all:
        pass
    else:
        parser.print_help()
        return 2

    if args.all:
        failures = 0
        total = 0
        for sh, n, path in iter_tests(args.stage, args.category):
            total += 1
            stored_path = os.path.join(OUT_ROOT, sh, "public", "outs",
                                       n + ".txt")
            try:
                with open(path, encoding="utf-8") as fh:
                    ins = fh.read()
            except OSError as exc:
                print(f"{n} : FAILED")
                print(f"    reason: cannot read input ({exc.strerror})")
                failures += 1
                continue
            try:
                with open(stored_path, encoding="utf-8") as fh:
                    stored = fh.read()
            except OSError:
                print(f"{n} : FAILED")
                print("    reason: missing expected-output file")
                failures += 1
                continue

            try:
                got = recompute(sh, n, ins)
            except Exception as exc:  # noqa: BLE001 - report, do not hide
                print(f"{n} : FAILED")
                print(f"    reason: oracle raised "
                      f"{type(exc).__name__}: {exc}")
                failures += 1
                continue

            if got == stored:
                print(f"{n} : passed")
                continue

            failures += 1
            print(f"{n} : FAILED")
            print("    reason: output mismatch")
            diff = first_difference(stored, got)
            if diff is None:
                print("    transcripts differ but no line differs; "
                      "check trailing whitespace")
                continue
            line_no, expected_line, got_line = diff
            print(f"    line {line_no}:")
            print(f"      expected: {expected_line!r}")
            print(f"      got:      {got_line!r}")
        print(f"{total - failures} passed, {failures} failed, {total} total")
        return 1 if failures else 0

    if name is None:
        parser.print_help()
        return 2

    matches = ([(stage, name, os.path.join(OUT_ROOT, stage, "public", "ins",
                                           name + ".txt"))]
               if stage else locate(name))
    if not matches:
        print(f"no generated test named {name!r}"
              + (f" in {stage}" if stage else ""), file=sys.stderr)
        return 2
    if len(matches) > 1:
        print(f"{name!r} exists in several stages: "
              + ", ".join(sh for sh, _, _ in matches), file=sys.stderr)
        return 2
    sh, n, path = matches[0]
    return 0 if show(sh, n, path, confidence) else 1


if __name__ == "__main__":
    sys.exit(main())