# Generated Test Format

Derived from `rw144_project_1.6.pdf` (v1.6, 18 Aug 2026) plus the official public
expected outputs in `tests/`. Nothing under `src/` was read. Where the spec and a
public example disagree, the public example wins and the conflict is recorded in
`AMBIGUITIES.md`.

## 1. Layout

```
tests_generated/<SH>/public/ins/<name>.txt   -> piped to the program's stdin
tests_generated/<SH>/public/outs/<name>.txt   -> compared byte-exact against stdout
```

Both files share a stem. `<SH>` is one of the staged hand-in directories. Files
are UTF-8 with LF line endings, and every file ends with exactly one trailing
newline.

## 2. What the marking script does with a test

From `scripts/marking_script.py`:

- **Discovery is hardcoded** to
  `Path.cwd()/"tests"/<SH>/<visibility>/{ins,outs}`. Nothing outside `tests/` is
  ever read, so generated files must be *copied* in before marking.
- **Category** = `test_name[:4]`. A file whose first four characters are not a
  category of the hand-in being marked is silently skipped.
- **Expected output** must be `outs/<same filename>`; a missing one raises
  `RuntimeError` and aborts the whole run.
- **Arguments** come from `sparg_check(test_name)`, else `SH_ARGS[SH]`.
- **Comparison** is `result.stdout == out_file.read_text()` — exact, including the
  trailing newline — under a 40 s timeout.
- **A non-zero exit is recorded as a CRASH, never a pass.** Every error-message
  test therefore assumes the message goes to **stdout and the program exits 0**.
  This is not a guess: all 23 public `SH2` cases expect exactly the message and
  nothing else.
- `compute_final_mark` raises if a weighted category has zero tests, so adding
  tests must never leave a hand-in with an empty category.

| SH | default args | meaning |
|----|----|----|
| SH2 / SH3 | `0 0` | vanilla, no AI |
| SH4 / SH5 | `1 0` | agentic, no AI |
| SH6 | `0 1` | vanilla, cipher guess strategy |
| SH7 | `0 2` | vanilla, lockcode guess strategy |
| SH8 | `1 3` | agentic, agentic guess strategy |

## 3. Filenames

Base shape is `<category>_gen<NNNN>.txt`. `sparg_check` scans the **entire**
filename for these keywords, in this order:

| keyword | chars consumed | effect |
|---|---|---|
| `sparg` | next 2 | one argument per character |
| `noargs` | 0 | no arguments |
| `onearg` | next 1 | one argument |
| `thrarg` | next 3 | three arguments |

If no keyword matches, the SH default applies. Because a keyword is required in
order to express argument-count and non-numeric argument cases, generated names
either **append** the keyword or **insert** it before the `_genNNNN` block —
never at the front, which would break the `[:4]` category prefix:

```
arge_gen0001_noargs.txt          -> args []
arge_gen0002_sparg030.txt        -> args ['0','3']
arge_gen0003_oneargx.txt         -> args ['x']
arge_gen0004_thrarg0000.txt      -> args ['0','0','0']
agsh_sparg11_gen0001.txt         -> args ['1','1']
```

No category prefix contains any keyword as a substring, so `[:4]` stays intact.
Each argument is exactly **one character**, so `-0` yields a non-numeric game
type, but an *empty* argument is not expressible through a filename and is
skipped (see `AMBIGUITIES.md`).

## 4. Categories and hand-in tags

| SH | category | generated | notes |
|----|---|---|---|
| SH2 | `arge` | yes | argument count / value errors |
| SH2 | `argc` | yes | valid combinations -> **completely empty** output |
| SH3 | `rsgn` | yes | first-guess resignation and game-setup errors |
| SH3 | `game` | yes | vanilla wins, losses, resignations, loop errors |
| SH4 | `deck` | yes | agent count and deck/hand setup errors |
| SH5 | `crck` | yes | none / unordered / ordered cracks |
| SH5 | `revl` | yes | full / hidden reveals |
| SH5 | `toss` | yes | discard and redraw order |
| SH5 | `extd` | yes | extend and the remaining-guess title bar |
| SH5 | `prmt` | yes | promote, rewrites of earlier rows |
| SH5 | `hdst` | yes | hindsight, rewrites of earlier rows |
| SH5 | `mapp` | yes | map |
| SH5 | `cont` | yes | count |
| SH5 | `alll` | yes | all effects, replay chains, combinations |
| SH6 | `cigs` | yes | cipher guess strategy |
| SH7 | `lkgs` | yes | lockcode guess strategy |
| SH8 | `agsh` | yes | agentic AI, hindsight / promote |
| SH8 | `agsm` | yes | agentic AI, map / count |
| SH8 | `agsr` | yes | agentic AI, no agent digits |
| SH8 | `agsa` | yes | agentic AI, everything |

`FH1` marks SH2+SH3+SH5, `FH2` marks SH6+SH7+SH8. `deck` and `argc` are picked up
only by `marking_script.py SH4` and `SH2` respectively, and are invisible to
FH1/FH2.

## 5. Output grammar

### 5.1 Prompts

Setup, both game types — 3 lines:

```
Enter the true-passcode and true-cipher:
○○○○ 123456
↓↓↓↓ ↓↓↓↓↓↓
```

Agentic setup adds `How many agent cards will you add?` and then, once per card,
`Enter agent name and effects for agent N:` (unadorned 1-based index).

Vanilla guess — 3 lines:

```
Enter a guess-passcode and guess-cipher:
○○○○ 123456
↓↓↓↓ ↓↓↓↓↓↓
```

Agentic guess — one long line with **no** break after `(optional).`, then 2
lines:

```
Enter a guess-passcode and guess-cipher, and play an agent card (optional). Also enter the agent digit if required.
○○○○ 123456 Agent and digit
↓↓↓↓ ↓↓↓↓↓↓ ↓
```

### 5.2 Guess title bar

Total width **44**, interior 42, 11 spaces before the `G`, right border flush:

```
┌──────────────────────────────────────────┐
│           Guess 1 (10 remaining)         │
└──────────────────────────────────────────┘
```

Text is `Guess {n} ({r} remaining)`, left-aligned at column 11 and padded to 42.
So `Guess 10 (10 remaining)` gets 9 trailing spaces, not 10.

### 5.3 Vanilla feedback table

Total 44. `┌`@0, `┬`@19, `┐`@43 -> **Guess interior 18**, **Feedback interior
23**.

| section | column | interior | rendered cell |
|---|---|---|---|
| Guess | `##` | 2 | left-justified: `1 `, `10` |
| | `Code` | 6 | ` 1122 ` |
| | `Cipher` | 8 | ` 123456 ` |
| *divider* | | | |
| Feedback | `Lock` | 6 | ` 1122 ` |
| | `Crack` | 7 | ` ○--●  ` |
| | `Reveal` | 8 | ` 123456 ` |

`Crack` is 7 = one leading space, a 5-wide glyph region left-justified, then one
trailing space. A 4-glyph crack therefore shows **two** trailing spaces.

### 5.4 Agent hand box

Total **18**. Printed after the title bar, before the guess prompt:

```
┌────────────────┐
│  Your Agents   │
├──────────┬─────┤
│ Mappa    │ UFM │
└──────────┴─────┘
```

Name column interior 10, effects column interior 5, each with one leading and one
trailing pad space. Cards are listed **oldest first**, so the most recently
drawn card is the last row. The header is 16 interior characters beginning with
**two** spaces, which deliberately does not align to the 10/5 split beneath it.

### 5.5 Agentic feedback table

Total `67 + B`, i.e. 1 + 40 + 1 + (24 + B) + 1. `┌`@0, `┬`@41, `┐`@(66+B).
Verified over all 4465 agentic tables in `tests_generated/`.

| section | column | interior | rendered cell |
|---|---|---|---|
| Guess | `##` | 2 | left-justified |
| | `Code` | 6 | ` 1122 ` |
| | `Cipher` | 8 | ` 123456 ` |
| | `Agent` | 10 | ` One      ` (1 leading pad, name left-justified) |
| | `CRB` | 5 | ` OHN ` |
| | `D` | 4 | ` X  ` / ` 1  ` (1 leading pad, left-justified) |
| *divider* | | | |
| Feedback | `Lock` | 6 | ` 1122 ` |
| | `Crack` | 7 | ` ○--●  ` |
| | `Reveal` | 8 | ` ------ ` |
| | `Bonus` | **B** | ` No bonus applied. ` + pad |

`Agent` shows `DEFAULT` and `CRB` shows `UFN` when no card is played.

**Reveal has three distinct rendered forms:**

- ` 123456 ` — full reveal.
- ` ------ ` — the reveal was hidden *and has since been exposed* by Hindsight.
- ` XXXXXX ` — the reveal is hidden and **not yet exposed**.

The transition from `XXXXXX` to `------` happens on the table redraw that follows
the Hindsight play, alongside the "Reveal on round N has been exposed." bonus.

**B** is recomputed for **every** printed table from the rows shown in it:
`B = len(longest bonus string in this table) + 2`. Verified against all 113
agentic tables in `tests/SH5` and `tests/SH8` with zero mismatches. Because the
longest string can change between rounds, the table grows and shrinks.

### 5.6 Border rows

The section divider falls immediately before `Lock`, which means it *coincides
with a column junction*. That junction therefore renders `┼`, not `┬`. All four
border rows, with the section boundary marked:

```
┌───────┬────────────────┐   top:        ┌ at 0, ┬ at section, ┐ at end
├──┬──┬─┼──┬────────────┤   under header: ┬ at plain junctions, ┼ at section
├──┼──┼─┼──┼────────────┤   under titles: ┼ at every junction
└──┴──┴─┴──┴────────────┘   bottom:      ┴ at every junction
```

`├`/`┤` terminate rows 2 and 3; `└`/`┘` close the bottom row.

### 5.7 Feedback semantics

- **Crack is Mastermind with repeats**, and the **ordered** variant is
  two-pass: resolve *all* exact positional matches first, consuming those true
  digits, then assign `○` to the remaining positions against the leftover pool,
  then `-`. A single-pass implementation is wrong; e.g. `1122` vs `4612` is
  `○-○●` single-pass but `○--●` two-pass, and only `○--●` matches the official
  output. It also reproduces the spec's `1313`/`1133` -> `●○○●`.
- **Reveal** compares the guessed mapping to the true mapping positionally over
  the 6 cipher positions: `413651` vs `213461` -> `-13--1`. This reading matches
  every official agentic reveal cell. An earlier apparent contradiction came
  from misreading the official cipher `435261` as unsorted; it is `4,3,5,2,6,1`.
- **Deck**: the Guard's cards enter the deck in submission order, drawing takes
  from the top, a played card goes to the **bottom** unshuffled, then the hand is
  refilled to three. The deck cycles indefinitely. Toss discards the played card
  first, then the rest of the hand **least-recently-drawn first**, then draws
  three.
- `DEFAULT`/`UFN` applies when no card is played: unordered crack, full reveal,
  bonus `No bonus applied.`

### 5.8 AI decision line

For `ai_type` 1, 2 and 3 the AI prints its own decision, on its own line where
the Hacker would have typed. The input file then contains **only** the Guard's
setup (plus the deck when agentic).

```
{guess-passcode} {guess-cipher}                    -> no card played
{guess-passcode} {guess-cipher} {Agent}            -> card, no digit
{guess-passcode} {guess-cipher} {Agent} {digit}    -> card with digit
Resign                                             -> the AI resigns
```

The agent name is the normalized name exactly as it appears in the `Agent`
column. A digit is printed whenever the played card's bonus takes one, including
the no-op cases (for example `1122 123456 One 0` on the very first guess when
Hindsight has nothing to expose).

## 6. Errors: output, exit status, priority

All error messages go to **stdout**, the program then **exits 0**, and nothing
further is printed. Messages always end with a single newline.

| stage | tokens accepted | token-count error |
|---|---|---|
| Guard setup | 2 | `Expected 2 input tokens.` |
| Agent count | 1 | `Expected 1 input token.` |
| Agent name + effects | 2 | `Expected 2 input tokens.` |
| Vanilla guess | 1 or 2 | `Expected 1 or 2 input tokens.` |
| Agentic guess | 1-4 | `Expected 1, 2, 3 or 4 input tokens.` |

Priority, highest first:

1. **Whitespace** — any leading space, any trailing space, more than one space
   between tokens, or any tab -> `Too many whitespaces detected.`
2. **Token count**, before every other input error.
3. Everything else for that stage.

For a vanilla guess a single token must be `Resign`, in any case, giving
`The Hacker resigned.`; a single token that is not a resignation gives
`Expected resignation.`

The full message inventory is maintained in the generator so typos cannot drift.

## 7. Determinism

The generator uses a fixed seed, printed to stdout on every run, with no wall
clock or environment input. Each generated pair is verified by re-running the
oracle on its own `ins` and diffing against the stored `outs`; the run aborts on
any mismatch. Duplicate detection is by SHA-256 of the `(ins, outs)` pair.

## 8. Running

`marking_script.py` has no option to point at an external directory, so the only
supported route is a copy:

```
cp -R tests_generated/* tests/
python3 scripts/marking_script.py FH1
python3 scripts/marking_script.py FH2
python3 scripts/marking_script.py SH8   # for the sparg11 / sparg12 cases
```

`.gitignore` already excludes `*.txt`, so copied cases are never committed.