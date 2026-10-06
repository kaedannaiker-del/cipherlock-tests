#!/usr/bin/env python3
"""Independently verify the generated suite under tests_generated/.

Run from the repository root::

    python3 tools/testgen/verify_generated.py

Nothing here trusts the generator: every pair is re-read from disk, the
arguments are re-parsed from the filename with the same rules as
``scripts/marking_script.py``, and the expected output is recomputed with
``oracle.run_args``. It also checks the per-category counts, the
``test_name[:4]`` category tag, SHA-256 uniqueness of ``(args, stdin)`` and
``(args, stdin, stdout)``, and that nothing duplicates an official public test.

Exits non-zero if anything fails.
"""

from __future__ import annotations

import collections
import csv
import glob
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
TESTS_ROOT = os.path.join(ROOT, "tests")
OUT_ROOT = os.path.join(ROOT, "tests_generated")
MANIFEST = os.path.join(ROOT, "tools", "testgen", "MANIFEST.csv")

SH_ARGS = {
    "SH2": ["0", "0"],
    "SH3": ["0", "0"],
    "SH4": ["1", "0"],
    "SH5": ["1", "0"],
    "SH6": ["0", "1"],
    "SH7": ["0", "2"],
    "SH8": ["1", "3"],
}

SPECS = {"sparg": 2, "noargs": 0, "onearg": 1, "thrarg": 3}

# The distribution actually produced, after the argc reduction recorded in
# README.md: the seven valid (game_type, ai_type) combinations are all already
# covered by official SH2 tests, so argc contributes no new pairs.
EXPECTED = {
    "SH2": {"arge": 93},
    "SH3": {"rsgn": 60, "game": 327},
    "SH4": {"deck": 20},
    "SH5": {"crck": 45, "revl": 35, "toss": 35, "extd": 35, "prmt": 40,
            "hdst": 40, "mapp": 40, "cont": 40, "alll": 30},
    "SH6": {"cigs": 70},
    "SH7": {"lkgs": 90},
    "SH8": {"agsh": 65, "agsm": 45, "agsr": 45, "agsa": 45},
}

TOTAL = 1200


def sparg_check(filename: str, default: list[str]) -> list[str]:
    """Byte-for-byte reimplementation of marking_script.sparg_check."""
    for key, count in SPECS.items():
        idx = filename.find(key)
        if idx == -1:
            continue
        if count == 0:
            return []
        tail = filename[idx + len(key): idx + len(key) + count]
        if len(tail) == count:
            return list(tail)
    return list(default)


def digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def public_input_fingerprints() -> set[str]:
    seen: set[str] = set()
    for sh, args in SH_ARGS.items():
        indir = os.path.join(TESTS_ROOT, sh, "public", "ins")
        for path in sorted(glob.glob(os.path.join(indir, "*.txt"))):
            name = os.path.basename(path)[:-4]
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            seen.add(digest(repr(sparg_check(name, args)), text))
    return seen


def main() -> int:
    problems: list[str] = []
    counts: dict[tuple[str, str], int] = collections.Counter()
    inputs: dict[str, str] = {}
    triples: dict[str, str] = {}
    public = public_input_fingerprints()
    checked = 0

    for sh, args in SH_ARGS.items():
        indir = os.path.join(OUT_ROOT, sh, "public", "ins")
        outdir = os.path.join(OUT_ROOT, sh, "public", "outs")
        paths = sorted(glob.glob(os.path.join(indir, "*.txt")))
        for path in paths:
            name = os.path.basename(path)[:-4]
            category = name[:4]
            counts[(sh, category)] += 1
            with open(path, encoding="utf-8") as fh:
                ins = fh.read()
            out_path = os.path.join(outdir, name + ".txt")
            if not os.path.isfile(out_path):
                problems.append(f"{sh}/{name}: missing outs file")
                continue
            with open(out_path, encoding="utf-8") as fh:
                outs = fh.read()

            args_used = sparg_check(name, args)
            try:
                expected = oracle.run_args(args_used, ins)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{sh}/{name}: oracle raised "
                                f"{type(exc).__name__}: {exc}")
                continue
            if expected != outs:
                problems.append(f"{sh}/{name}: output mismatch")
                continue

            input_fp = digest(repr(args_used), ins)
            triple_fp = digest(repr(args_used), ins, outs)
            if input_fp in inputs:
                problems.append(f"{sh}/{name}: duplicate stdin with "
                                f"{inputs[input_fp]}")
                continue
            if triple_fp in triples:
                problems.append(f"{sh}/{name}: duplicate output with "
                                f"{triples[triple_fp]}")
                continue
            if input_fp in public:
                problems.append(f"{sh}/{name}: duplicates a public test")
                continue
            inputs[input_fp] = f"{sh}/{name}"
            triples[triple_fp] = f"{sh}/{name}"
            checked += 1

    for sh, cats in EXPECTED.items():
        for cat, want in cats.items():
            got = counts.get((sh, cat), 0)
            if got != want:
                problems.append(f"{sh}/{cat}: expected {want} pairs, found {got}")
    for (sh, cat) in counts:
        if cat not in EXPECTED.get(sh, {}):
            problems.append(f"{sh}/{cat}: unexpected category")
    if checked != TOTAL:
        problems.append(f"expected {TOTAL} verified pairs, found {checked}")

    # The manifest must describe exactly the same set of tests.
    if os.path.isfile(MANIFEST):
        with open(MANIFEST, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        listed = {f"{r['sh']}/{r['test']}" for r in rows}
        on_disk = set(inputs.values())
        if listed != on_disk:
            problems.append(
                f"manifest lists {len(listed)} tests, disk has {len(on_disk)}"
                + (f"; only in manifest: {sorted(listed - on_disk)[:3]}"
                   if listed - on_disk else "")
                + (f"; only on disk: {sorted(on_disk - listed)[:3]}"
                   if on_disk - listed else ""))
        for row in rows:
            key = f"{row['sh']}/{row['test']}"
            ins_path = os.path.join(OUT_ROOT, row["sh"], "public", "ins",
                                    row["test"] + ".txt")
            with open(ins_path, encoding="utf-8") as fh:
                ins = fh.read()
            if hashlib.sha256(ins.encode()).hexdigest() != row["ins_sha256"]:
                problems.append(f"{key}: manifest ins_sha256 is wrong")
    else:
        problems.append("MANIFEST.csv is missing")

    print(f"{checked} verified, {len(problems)} problems, {checked} total")
    print("category counts:")
    for sh in SH_ARGS:
        row = "  ".join(f"{cat}={counts[(sh, cat)]}"
                        for cat in sorted(EXPECTED.get(sh, {})))
        print(f"  {sh} {row}")
    for p in problems:
        print(f"  ! {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())