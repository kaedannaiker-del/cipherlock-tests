# Generated Cipherlock regression suite

A standalone, specification-only regression suite for Cipherlock: 1200 unique
input/output pairs, an independent oracle, a deterministic generator and two
verifiers.

Nothing in this directory reads, imports, copies or executes anything under
`src/`. Every rule comes from `rw144_project_1.6.pdf`, and wherever the prose
and the official expected outputs under `tests/` disagree, the official outputs
win (`AMBIGUITIES.md`).

## Layout

| path | purpose |
|---|---|
| `FORMAT.md` | exact output format: prompts, tables, borders, hand box, AI line, errors |
| `AMBIGUITIES.md` | every spec/output conflict, how it was resolved, what was skipped |
| `oracle.py` | the oracle: replay of the whole game, both AIs, all eight stages |
| `generate.py` | deterministic generator that writes `tests_generated/` and `MANIFEST.csv` |
| `verify_public.py` | replays all 102 official `tests/` pairs through the oracle |
| `verify_generated.py` | independently re-reads and re-checks all 1200 generated pairs |
| `show_test.py` | inspect one generated case, list cases, or replay a stage |
| `MANIFEST.csv` | one row per generated pair: stage, category, test, args, confidence, hashes |

## Running

```sh
python3 tools/testgen/generate.py           # writes tests_generated/ + MANIFEST.csv
python3 scripts/test_script.py FH2          # marks the generated suite
python3 scripts/marking_script.py FH2       # marks the official suite
```

`scripts/test_script.py` is the generated-suite counterpart of
`scripts/marking_script.py`: it is a verbatim copy of that script with only the
test root changed, so discovery, the subprocess invocation of `src/cipherlock.py`,
the exact stdout comparison, the category weights, the hand-in tags and the
summary tables are identical. It reads `tests_generated/`; add
`--include-original` to merge in the official `tests/` cases too. It never writes
to `tests/`.

Requires Python 3.10+, standard library only.

Other verifier entry points:

```sh
python3 tools/testgen/verify_public.py      # 102 passed, 0 failed
python3 tools/testgen/verify_generated.py   # 1200 verified, 0 problems
```

`generate.py` prints its seed (`SEED = 20261003`) and is a pure function of it:
re-running reproduces every file byte for byte. It takes about 55 s.

## Inspecting a single case

```sh
python3 tools/testgen/show_test.py SH5 mapp_gen0001   # stage + name
python3 tools/testgen/show_test.py mapp_gen0001      # stage auto-detected
python3 tools/testgen/show_test.py --list --stage SH8 --category agsh
python3 tools/testgen/show_test.py --all --stage SH4 # replay a stage
python3 tools/testgen/show_test.py --all             # replay all 1200
```

With one test name it prints the stored input and expected stdout, recomputes
the transcript with the oracle, and exits non-zero if the two disagree. This is
the quickest way to read one case without touching ``src/``.

`--all` prints one line per test, plus the reason and the first differing line
for any failure:

```
mapp_gen0001 : passed
prmt_gen0012 : FAILED
    reason: output mismatch
    line 14:
      expected: '1 │ 1122 │ 123456 │ Willow   │ UFM │ 1  │'
      got:      '1 │ 1122 │ 123456 │ Willow   │ UFM │ 2  │'
17 passed, 3 failed, 20 total
```

The reported line number uses the same convention as `verify_public.py`, so it
means the same thing in all three tools. The failure reasons are: output
mismatch, missing expected-output file, unreadable input, and oracle raised
`<Error>: <message>`. Exit status is 1 if anything failed.

## Output layout

```
tests_generated/<SH>/public/ins/<test>.txt
tests_generated/<SH>/public/outs/<test>.txt
```

Filenames follow the conventions `scripts/marking_script.py` understands: the
category is the first four characters, and `spargXY` / `noargs` / `oneargX` /
`thrargXYZ` override the stage's default arguments. Defaults are `0 0` for
SH2/SH3, `1 0` for SH4/SH5, `0 1` for SH6, `0 2` for SH7 and `1 3` for SH8.

To mark with these tests, run `python3 scripts/test_script.py <tag>` — it points
directly at `tests_generated/`, so nothing has to be copied into `tests/`. The
official `scripts/marking_script.py` still reads `<stage>/public/{ins,outs}`
under `tests/` and is unchanged.

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

Total 1200. Every input is **complete**: each transcript ends in a win, a loss or
a resignation, so no generated test depends on what happens at end of input.

`MANIFEST.csv` marks 360 pairs `confidence=low`: the AI strategy categories
(`cigs`, `lkgs`) and the agentic AI categories (`agsh`, `agsm`, `agsr`, `agsa`,
including the `sparg11`/`sparg12` overrides). Their expected output depends on
the AI's card and digit choice, which is the least firmly specified part of the
project; everything else is `high`.

## Deviations from the requested distribution

Two categories cannot meet their requested counts. Both are recorded in
`AMBIGUITIES.md` entries 10 and 11.

- **`argc` is 0, not 10.** The seven official `argc` pairs are argument
  validation only: one-byte stdin, zero-byte expected output. Only seven
  `(game_type, ai_type)` combinations are valid, and all seven already exist in
  the official files, so any generated `argc` pair would be a duplicate. The 10
  slots were moved to `game` (320 -> 327).
- **`agsh` is 65, not 45.** The additional 20 pairs are the requested
  `sparg11`/`sparg12` argument overrides, which share the `agsh` category tag.

## How a pair is built

Each constructor proposes a candidate, then the generator gates it:

1. `oracle.run_args` must run it without raising.
2. The transcript must satisfy the category's own acceptance check — a category
   like `prmt` is only kept if it really produced `Crack on round N is now
   ordered.`, and `hdst` only if it produced a Hindsight exposure.
3. Neither `(args, stdin)` nor `(args, stdin, stdout)` may collide with an
   earlier case or with any official public test.

Crack kinds, Count/Map digits, Promote and Hindsight targets are constructed
deliberately rather than left to chance: `guess_of_kind` searches for a guess
whose lock produces a required none/unordered/ordered crack against the true
lock, and Promote and Hindsight plans are laid out so the targeted round really
is eligible.
## Coverage

Every `MSG_*` constant in the oracle is exercised by at least one generated
pair, with one deliberate exception: `MSG_AI3_VANILLA` (game type 0 with AI type
3). The official test `tests/SH2/public/arge_sparg030.txt` already covers it with
identical arguments and identical empty stdin, so a generated pair would be a
byte-for-byte duplicate and is skipped by the de-duplication gate. Together the
official and generated suites cover every message.

Every generated input is complete, and the transcript outcomes are spread
across wins, losses and resignations rather than concentrating on one.

## Notes for future changes

- `deck` cases must place the invalid card **inside** the declared card count.
  Appending it after the count silently produces a test that never reads it.
- `Toss` empties the hand, so only the round that tosses can play a card; later
  rounds must not name a card.
- The default card is `UFN`, so a guess with no card played has a **full**
  reveal. Hindsight therefore needs round 1 to play an `H`-reveal card before a
  later round can expose it.
- An extend is cancelled by that round's own guess, so the 20-guess ceiling is
  only reached on round 11. The official `extra_tests/extd/outs/extd_cap.txt`
  confirms this; `c_extend_full` plays eleven extends to reach it.
- Replay delegates digit validation to the effect it repeats, so a Replay of
  Extend or Toss must not carry an agent digit.
