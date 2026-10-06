# Cipherlock Test Suite

1200 generated input / expected-output pairs for the CS144 Cipherlock project,
plus an independent oracle, a deterministic generator and a marking script.

Everything here is built from the specification alone: no implementation is
read, imported or executed to produce an expected output. Where the prose and
the official expected outputs disagreed, the official outputs won
(`tools/testgen/AMBIGUITIES.md`).

## Getting it

```sh
git clone https://github.com/kaedannaiker-del/cipherlock-tests.git
```

No git? Use **Code → Download ZIP** on the repo page and unzip it.

## Requirements

- **Python 3.12.3** is the official marking runtime. The marking script runs on
  other versions too, but prints a warning that results may differ.
- `python3 -m pip install pycodestyle==2.14.0` — only needed for hand-ins that
  include a style mark (`FH2`); everything else skips it gracefully.
- Standard library only otherwise. No third-party packages, no network access.

## Running it against your implementation

Run from **this repo's root** (the suite is read from `./tests_generated`):

```sh
python3 scripts/test_script.py SH4 -i /path/to/your/project
```

`-i` points at your project root, which must contain:

```
src/cipherlock.py      # the implementation under test
src/  tests/  scripts/ # plus README.md and .gitignore at the root
```

Those last checks are the standard SH1 setup check, so a normal course project
layout satisfies them. Useful flags:

| flag | effect |
|---|---|
| `--quiet` | suppress per-test logging |
| `--include-original` | also merge in an official `tests/` directory (not shipped here) |
| `-v public private` | choose visibility directories |

Hand-in tags: `SH1`–`SH8`, `FH1` (SH2+SH3+SH5), `FH2` (SH6+SH7+SH8+style).

Example:

```
┌────────┬──────┬──────┬───────┬─────┐
│Category│Passed│Failed│Crashed│Total│
├────────┼──────┼──────┼───────┼─────┤
│deck    │20    │0     │0      │20   │
│TOTAL   │20    │0     │0      │20   │
└────────┴──────┴──────┴───────┴─────┘
```

## Merging into your own project instead

If you would rather mark with your course's own `scripts/marking_script.py`,
copy `tests_generated/` and `tools/` into your project root and run:

```sh
python3 tools/testgen/install_into_tests.py          # copy into tests/ (never clobbers)
python3 tools/testgen/install_into_tests.py --check  # preview only
python3 scripts/marking_script.py SH4                # your marking script
```

The generated names (`<category>_genNNNN.txt`) never collide with the shipped
official names, and the tool refuses to overwrite a file it did not create.

## Inspecting and verifying individual cases

```sh
python3 tools/testgen/verify_generated.py      # 1200 verified, 0 problems
python3 tools/testgen/show_test.py mapp_gen0001  # one case: input, output, oracle replay
python3 tools/testgen/show_test.py --list --stage SH5
python3 tools/testgen/show_test.py --all         # replay all 1200
```

`show_test.py` recomputes the expected output with the oracle and exits
non-zero if it disagrees with the stored file, so a single case can be checked
in a second without touching your implementation.

## Regenerating from scratch

```sh
python3 tools/testgen/generate.py     # ~55 s, prints its seed, writes tests_generated/ + MANIFEST.csv
```

Pure function of `SEED = 20261003`: re-running reproduces every file byte for
byte. Python 3.10+, standard library only.

## Layout

```
tests_generated/<SH>/public/ins/<test>.txt    # stdin for the run
tests_generated/<SH>/public/outs/<test>.txt   # exact expected stdout
```

The category is the first four characters of the filename. The suffixes
`spargXY`, `noargs`, `oneargX` and `thrargXYZ` override the stage's default
arguments; defaults are `0 0` for SH2/SH3, `1 0` for SH4/SH5, `0 1` for SH6,
`0 2` for SH7 and `1 3` for SH8.

## Distribution

| stage | categories |
|---|---|
| SH2 | `arge` 93 |
| SH3 | `game` 327, `rsgn` 60 |
| SH4 | `deck` 20 |
| SH5 | `crck` 45, `revl` 35, `toss` 35, `extd` 35, `prmt` 40, `hdst` 40, `mapp` 40, `cont` 40, `alll` 30 |
| SH6 | `cigs` 70 |
| SH7 | `lkgs` 90 |
| SH8 | `agsh` 65, `agsm` 45, `agsr` 45, `agsa` 45 |

Total 1200. Every input is **complete**: each transcript ends in a win, a loss
or a resignation, so no generated test depends on what happens at end of input.

`tools/testgen/MANIFEST.csv` marks 360 pairs `confidence=low`: the AI strategy
categories (`cigs`, `lkgs`) and the agentic AI categories (`agsh`, `agsm`,
`agsr`, `agsa`). Their expected output depends on the AI's card and digit
choice, which is the least firmly specified part of the project. Everything
else is `high`.

Two requested categories could not be met; see `tools/testgen/AMBIGUITIES.md`
entries 10 and 11 for why (`argc` is 0, not 10 — the seven valid argument
combinations already exist officially; `agsh` is 65, not 45 — the extra 20 are
`sparg11`/`sparg12` overrides).

## Not included

- The reference implementation and the 102 official test pairs — private.
- `tools/testgen/verify_public.py`, which only replays that official suite.
- The course specification PDF.

## Documentation

| file | contents |
|---|---|
| `tools/testgen/FORMAT.md` | exact output format: prompts, tables, borders, hand box, AI line, errors |
| `tools/testgen/AMBIGUITIES.md` | every spec/output conflict, how it was resolved, what was skipped |
| `tools/testgen/README.md` | how the suite was built, generator internals, notes for future changes |
