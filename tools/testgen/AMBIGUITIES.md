# Ambiguities and Skip Rules

Where `rw144_project_1.6.pdf` and the official public expected outputs in
`tests/` disagree, the public output wins and the conflict is recorded here.
Where neither settles a case, the construction is **skipped** rather than
guessed.

The oracle is gated at **102/102** on `tests/` and **200/200** on `extra_tests/`,
so nothing listed below is currently blocking generation.

---

## 1. Agent hand box: header span vs. column split

**Conflict.** §9.1 says the agent name column "should be 10 spaces wide, with one
space between the left border of the table and the first letter of the
normalized agent name", and the ASCII sketch in the same section draws
`│ Your Agents │` spanning both columns. The observed header is
`│  Your Agents   │` — 16 interior characters with **two** leading spaces, which
does not align to the 10/5 split beneath it.

**Resolution.** Match the observed 16-character interior with two leading spaces,
per the same paragraph's instruction that there be two spaces before the `Y`.

**Skipped.** None. The public examples settle this completely.

---

## 2. Promote / Hindsight: "no candidates" feedback vs. digit validation order

**Conflict.** §9.3 says agent digit validation errors occur "before any other
effect-related error", while §9.3.5 and §9.3.6 each give their "no previous
guesses" feedback *before* checking whether a digit was supplied or is valid.
The two orderings disagree when both conditions hold at once.

**Resolution.** The "no candidates" feedback wins, per the more specific
§9.3.5/§9.3.6 and the public `hdst`/`prmt` examples.

**Skipped.** The constructions whose output depends only on the disputed
ordering: a Hindsight play with no previous hidden reveal *combined with* a digit
of `0` or a round number beyond the previous round, and the Promote equivalent.

---

## 3. Replay digit validation

**Was previously listed as underspecified. Now resolved.**

The old note claimed it was unspecified whether Replay validates the *original*
digit or the *currently entered* one, and skipped the difference. §9.3 states
that "for the Replay bonus action, the digit validation behavior should match
that of the Bonus effect being replayed", and `extra_tests/alll` confirms it:
`Rpla` replaying Toss validates its digit exactly as Toss would.

**Resolution.** Replay validates the currently entered digit against the
replayed effect's rules, then applies that effect — including its *deck action*,
not merely its feedback string. Replay-of-Toss really does discard and redraw.

**Skipped.** None.

---

## 4. Replay value when the replayed effect needs no digit

**Conflict.** §10.3.4 says only "Replay: equal to the value of the bonus effect
that will be played." Read naively, a Replay of Extend or Toss — neither of
which takes a digit — looks like it has nothing to replay and is worth `-1`.

**Resolution.** `extra_tests` and `tests/SH8/agsa_case00` both show the AI
playing a Replay card that replays Extend, which requires treating the effect's
*value* as replayable independent of whether it takes a digit. Replay is worth
`-1` only when there is genuinely no prior non-Replay, non-None bonus effect to
replay.

**Skipped.** None.

---

## 5. Agentic AI: what the minimax scores against

**Not a spec ambiguity, but genuinely underdetermined from the prose alone, so
recorded here because it was the single largest source of wrong guesses.**

§10.2 step 5 defines `score(code, ordered)` but does not say what `ordered` is
once cards are in play. Three points had to be pinned down, each confirmed
against `tests/SH8`:

1. `ordered` is the crack effect of **the card being played this round**. Scoring
   an ordered-crack card as unordered picks the wrong guess-lockcode.
2. The lock pool must be rebuilt from **every crack currently visible in the
   table**, not accumulated one guess at a time. A Promote card upgrades a row
   that was already played — none to unordered, or unordered to ordered — which
   turns a row that carried no information into a real constraint on S.
3. Constraints that leave no crack in the table, such as **Count**, must survive
   that rebuild. Discarding them silently un-solves a lockcode the AI had
   already pinned down.

**Skipped.** None; all three are exercised by the public `SH8` examples.

---

## 6. Agent-digit column for multi-digit digits

**Gap.** §9.2 makes the `D` column four characters wide and Hindsight and Promote
accept round numbers above 9, so `D` could need three characters. No public
example plays a double-digit agent digit.

**Resolution.** Render left-justified in the 4-character interior, so `10` appears
as `10  `.

**Skipped.** Hindsight and Promote plays needing an agent digit of 10 or more.

---

## 7. Extend at exactly 10 remaining vs. the 20-guess ceiling

**Gap.** §9.3.1 adds no extra guess when "guesses already played plus guesses
remaining is 20", while the bonus list says "no effect if the Hacker has already
extended to 20 total guesses". These agree for one extension and differ in
wording on a second attempt.

**Resolution.** The §9.3.1 arithmetic rule; the ceiling is reached only after ten
extends from a ten-guess start.

**Skipped.** None — the alternative wording cannot be distinguished in one game.

---

## 8. Empty command-line arguments

**Gap.** `sparg_check` reads one character per argument from the test filename, so
an argument that is the empty string cannot be encoded.

**Resolution.** None available.

**Skipped.** Any case requiring an empty-string argument. Non-numeric and
negative values are still reachable (`oneargx`, `spargx0`, `sparg-0`) and are
generated.

---

## 9. Truncated input

**Note.** The reference transcripts in `extra_tests/` include cases whose input
runs out mid-game; the expected output is simply the transcript up to the last
prompt printed. The oracle reproduces this by ending the transcript when input is
exhausted rather than reading past the end.

**Skipped.** None. The generator only ever emits complete input, so generated
tests never depend on this.
---

## 10. `argc` pairs are an SH2-stage check, not a game

**Observation.** All seven official `argc` pairs (`tests/SH2/public/`) have a
one-byte stdin (`"\n"`) and a **zero-byte** expected output, yet every other
official transcript in the suite begins with
`Enter the true-passcode and true-cipher:` — including the official cases that
fail setup validation. A full game fed `"\n"` could not produce empty output.

**Resolution.** `argc` is argument validation only: the SH2 stage of the
project, where the program validates its two arguments and exits before any
prompt is printed. `tools/testgen/verify_public.py` special-cases these names
(`if name.startswith("argc")`) by calling `oracle.validate_args` and expecting
`""`, and `generate.py` mirrors that with a `"stage": "sh2"` marker.

**Consequence for the suite.** Only seven `(game_type, ai_type)` pairs are
valid — `(0,0)`, `(0,1)`, `(0,2)`, `(1,0)`, `(1,1)`, `(1,2)`, `(1,3)` — and all
seven already exist in the official `argc` files. A generated `argc` pair could
therefore only be a byte-for-byte duplicate of a public test, so the generator
emits **zero** `argc` pairs rather than padding the category with fake ones.
The 10 requested slots are redistributed to `game` (320 -> 327), keeping the
total at 1200. See `README.md`.

**Skipped.** None.

---

## 11. Requested category distribution

**Gap.** The agreed per-category counts are not all attainable. `argc` admits at
most 7 distinct cases and all 7 are already public (entry 10); `agsh` needed a
further 20 pairs with the `sparg11`/`sparg12` argument overrides, which are
folded into the `agsh` count (45 + 20 = 65).

**Resolution.** `argc` is dropped to 0 and its 10 slots go to `game`. Every
other category meets its target exactly. `verify_generated.py` asserts the
resulting distribution, so any drift fails the gate.

**Skipped.** None.
