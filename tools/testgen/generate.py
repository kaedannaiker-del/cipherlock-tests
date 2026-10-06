#!/usr/bin/env python3
"""Generate the Cipherlock regression suite under tests_generated/.

Every expected output is produced by ``tools/testgen/oracle.py``, which
reproduces all 102 official public pairs and all 200 ``extra_tests`` pairs
exactly. Nothing under ``src/`` is read or imported.

Run from the repository root::

    python3 tools/testgen/generate.py

The seed is fixed and printed on every run and the suite is a pure function of
that seed, so re-running reproduces it byte for byte.

Each candidate is validated before acceptance: the oracle must run it without
raising, the transcript must satisfy the category's acceptance check, and
neither ``(args, stdin)`` nor ``(args, stdin, stdout)`` may duplicate an
earlier case or an official public test.
"""

from __future__ import annotations

import csv
import hashlib
import os
import random
import shutil
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle  # noqa: E402

SEED = 20261003

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
OUT_ROOT = os.path.join(ROOT, "tests_generated")
TESTS_ROOT = os.path.join(ROOT, "tests")

SH_ARGS = {
    "SH2": ["0", "0"],
    "SH3": ["0", "0"],
    "SH4": ["1", "0"],
    "SH5": ["1", "0"],
    "SH6": ["0", "1"],
    "SH7": ["0", "2"],
    "SH8": ["1", "3"],
}

CRACK_CODES = "UON"
REVEAL_CODES = "FH"
BONUS_CODES = "ECMRTHPN"

MIN_DECK, MAX_DECK = 8, 28

# Cards played across a plan; the front of the deck in play order keeps the
# hand check correct for any number of them.
MAX_PLAYS = 12

NAME_POOL = [
    "Alpha", "Bravo", "Cedar", "Delta", "Echo", "Foxtrot", "Golf", "Hotel",
    "India", "Juliett", "Kilo", "Lima", "Mike", "Nova", "Oscar", "Papa",
    "Quebec", "Romeo", "Sierra", "Tango", "Umber", "Victor", "Willow",
    "Xray", "Yankee", "Zulu", "Basil", "Maple", "Aspen", "Hazel", "Birch",
    "Laurel", "Rowan", "Sorrel", "Tulip", "Vetch", "Yarrow", "Aster",
    "Bramble", "Clover", "Dahlia", "Elm",
]

TERMINATORS = {oracle.MSG_WIN, oracle.MSG_LOSS, oracle.MSG_RESIGN}

VALID_ARGC = [(g, a) for g in "01" for a in "0123"
              if not (g == "0" and a == "3")]

ARGCHARS = "0123456789x-"

SETUP_ERRORS = (
    oracle.MSG_WHITESPACE, oracle.MSG_CODE_LEN, oracle.MSG_CODE_DIGITS,
    oracle.MSG_CIPHER_LEN, oracle.MSG_CIPHER_DIGITS, oracle.MSG_CIPHER_REPEAT,
    oracle.expected_tokens_message((2,)), oracle.expected_tokens_message((1, 2)),
    oracle.expected_tokens_message((3,)),
)

GUESS_ERRORS = SETUP_ERRORS + (
    oracle.MSG_DIGIT_RANGE, oracle.MSG_ROUND_NUMBER, oracle.MSG_NOT_IN_HAND,
    oracle.MSG_RESIGN_ONLY,
)


# --- construction helpers ----------------------------------------------------

def rand_cipher(rng: random.Random) -> str:
    digits = list("123456")
    rng.shuffle(digits)
    return "".join(digits)


def rand_passcode(rng: random.Random) -> str:
    return "".join(rng.choice("123456") for _ in range(4))


def code(crack: str = "U", reveal: str = "F", bonus: str = "N") -> str:
    return f"{crack}{reveal}{bonus}"


def deck_block(cards: list[tuple[str, str] | str]) -> str:
    """Render a deck. A raw string is emitted verbatim, for invalid cards."""
    lines = [f"{card[0]} {card[1]}" if isinstance(card, tuple) else str(card)
             for card in cards]
    return "\n".join([str(len(cards))] + lines) + "\n"


def names_for(rng: random.Random, n: int, used: set[str]) -> list[str]:
    pool = [nm for nm in NAME_POOL if nm.lower() not in used]
    if len(pool) < n:
        raise RuntimeError("name pool exhausted")
    rng.shuffle(pool)
    chosen = pool[:n]
    used.update(nm.lower() for nm in chosen)
    return chosen


def random_deck(rng: random.Random, n: int, used: set[str]) -> list[tuple[str, str]]:
    picks = names_for(rng, n, used)
    return [(nm, code(rng.choice(CRACK_CODES), rng.choice(REVEAL_CODES),
                      rng.choice(BONUS_CODES))) for nm in picks]


def filler_guesses(rng: random.Random, n: int, avoid: tuple[str, str]) -> list[str]:
    """``n`` valid guess lines that cannot accidentally win the game."""
    out = []
    while len(out) < n:
        line = f"{rand_passcode(rng)} {rand_cipher(rng)}"
        if (line.split()[0], line.split()[1]) != avoid:
            out.append(line)
    return out


def ends_with_terminator(out: str) -> bool:
    lines = out.rstrip("\n").split("\n")
    return bool(lines) and lines[-1] in TERMINATORS


def contains(*needles: str) -> Callable[[str], bool]:
    def check(out: str) -> bool:
        return ends_with_terminator(out) and all(n in out for n in needles)
    return check


def exact_last(*needles: str) -> Callable[[str], bool]:
    def check(out: str) -> bool:
        lines = out.rstrip("\n").split("\n")
        return bool(lines) and lines[-1] in needles
    return check


def crack_kind(lock: str, true_lock: str) -> str:
    unordered = oracle.crack_unordered(lock, true_lock)
    if unordered == "----":
        return "none"
    if unordered == oracle.crack_ordered(lock, true_lock):
        return "ordered"
    return "unordered"


def expand_effect(rng: random.Random, spec: str) -> str:
    """Expand a shorthand effect into a valid 3-character code.

    Plans name only the interesting slot: ``"P"`` means "some card whose bonus
    is Promote", ``"H"`` means "some card whose reveal is Hindsight".
    """
    if len(spec) == 3:
        return spec
    if spec in BONUS_CODES:
        return code(rng.choice(CRACK_CODES), rng.choice(REVEAL_CODES), spec)
    if spec in REVEAL_CODES:
        return code(rng.choice(CRACK_CODES), spec, rng.choice(BONUS_CODES))
    raise ValueError(f"bad effect shorthand {spec!r}")


def guess_of_kind(rng: random.Random, tp: str, tc: str, kind: str,
                  tries: int = 900) -> str | None:
    """A guess line whose crack is exactly ``kind`` against the true lock.

    Repeated passcodes are tried often because a lock with few distinct digits
    is what makes "none" and "unordered" cracks reachable at all.
    """
    true_lock = oracle.lock_of(tc, tp)
    for _ in range(tries):
        gp = rng.choice("123456") * 4 if rng.random() < 0.45 else rand_passcode(rng)
        gc = rand_cipher(rng)
        if crack_kind(oracle.lock_of(gc, gp), true_lock) == kind:
            return f"{gp} {gc}"
    return None


# --- agentic manual cases ----------------------------------------------------

# --- SH2 argument cases ------------------------------------------------------

ARGE_FORCED = [["0", "3"], ["1", "0"]]


def c_arge(rng: random.Random) -> dict | None:
    if rng.random() < 0.12:
        return {"args": list(rng.choice(ARGE_FORCED)), "ins": "",
                "check": exact_last(oracle.MSG_AI3_VANILLA)}
    n = rng.choice([0, 0, 1, 1, 1, 2, 2, 2, 3])
    if n == 0:
        args: list[str] = []
    elif n == 1:
        args = [rng.choice(ARGCHARS)]
    elif n == 2:
        args = [rng.choice(ARGCHARS), rng.choice(ARGCHARS)]
    else:
        args = [rng.choice(ARGCHARS) for _ in range(3)]
    if args == SH_ARGS["SH2"]:
        return None
    try:
        oracle.validate_args(args)
    except oracle.Terminate:
        pass
    else:
        return None
    return {"args": args, "ins": "", "check": exact_last(
        oracle.MSG_FEW_ARGS, oracle.MSG_MANY_ARGS, oracle.MSG_GAME_TYPE,
        oracle.MSG_AI_TYPE, oracle.MSG_AI3_VANILLA)}


def c_argc(rng: random.Random) -> dict | None:
    """SH2-stage valid argument combinations: validate, exit, print nothing.

    The seven official ``argc`` pairs all have a one-byte stdin and a
    zero-byte expected output, so they are argument-validation-only checks
    rather than full games. ``verify_public.py`` special-cases them the same
    way.
    """
    g, a = rng.choice(VALID_ARGC)
    try:
        oracle.validate_args([g, a])
    except oracle.Terminate:
        return None
    return {"args": [g, a], "ins": "\n", "check": lambda out: out == "",
            "stage": "sh2"}


# --- SH3 vanilla -------------------------------------------------------------

def c_rsgn(rng: random.Random) -> dict | None:
    pick = rng.randrange(10)
    if pick < 3:
        word = rng.choice(["Resign", "resign", "RESIGN", "rEsIgN", "ReSiGn"])
        return {"args": SH_ARGS["SH3"],
                "ins": f"{rand_passcode(rng)} {rand_cipher(rng)}\n{word}\n",
                "check": exact_last(oracle.MSG_RESIGN)}
    if pick == 4:
        return c_cipher_digits(rng)
    if pick < 5:
        bad = rng.choice(["1234", "hello", "123456789", "1", "resign "])
        return {"args": SH_ARGS["SH3"],
                "ins": f"{rand_passcode(rng)} {rand_cipher(rng)}\n{bad}\n",
                "check": exact_last(oracle.MSG_RESIGN_ONLY,
                                    oracle.expected_tokens_message((1, 2)))}
    if pick == 5:
        bad = rng.choice([" 1234 123456", "1234 123456 ", "1234  123456",
                          "1234\t123456", "1234 1 23456", "1234  123456  ",
                          "1 2 3"])
        return {"args": SH_ARGS["SH3"], "ins": bad + "\n",
                "check": exact_last(oracle.MSG_WHITESPACE,
                                    oracle.expected_tokens_message((2,)),
                                    oracle.expected_tokens_message((3,)))}
    if pick == 6:
        bad = rng.choice(["123", "12345", "1234567", "1"])
        return {"args": SH_ARGS["SH3"],
                "ins": f"{bad} {rand_cipher(rng)}\n",
                "check": exact_last(oracle.MSG_CODE_LEN,
                                    oracle.expected_tokens_message((1, 2)))}
    if pick == 7:
        bad = rng.choice(["1230", "1237", "abcd", "12 4", "12a4"])
        return {"args": SH_ARGS["SH3"], "ins": f"{bad} {rand_cipher(rng)}\n",
                "check": exact_last(oracle.MSG_CODE_DIGITS,
                                    oracle.MSG_WHITESPACE,
                                    oracle.expected_tokens_message((2,)))}
    bad = rng.choice(["12345", "1234567", "12345a", "12345678"])
    return {"args": SH_ARGS["SH3"], "ins": f"{rand_passcode(rng)} {bad}\n",
            "check": exact_last(oracle.MSG_CIPHER_LEN,
                                oracle.MSG_CODE_DIGITS,
                                oracle.expected_tokens_message((2,)))}


def c_cipher_digits(rng: random.Random) -> dict | None:
    bad = rng.choice(["123450", "123457", "12345a", "023456"])
    return {"args": SH_ARGS["SH3"], "ins": f"{rand_passcode(rng)} {bad}\n",
            "check": exact_last(oracle.MSG_CIPHER_DIGITS,
                                oracle.MSG_CODE_DIGITS)}


def c_game(rng: random.Random) -> dict | None:
    tp, tc = rand_passcode(rng), rand_cipher(rng)
    head = f"{tp} {tc}\n"
    pick = rng.randrange(10)
    if pick < 4:
        win_at = rng.randrange(1, 11)
        lines = filler_guesses(rng, win_at - 1, (tp, tc)) + [f"{tp} {tc}"]
        return {"args": SH_ARGS["SH3"], "ins": head + "\n".join(lines) + "\n",
                "check": exact_last(oracle.MSG_WIN)}
    if pick < 7:
        lines = filler_guesses(rng, 10, (tp, tc))
        return {"args": SH_ARGS["SH3"], "ins": head + "\n".join(lines) + "\n",
                "check": exact_last(oracle.MSG_LOSS)}
    if pick < 9:
        at = rng.randrange(2, 11)
        lines = (filler_guesses(rng, at - 1, (tp, tc))
                 + [rng.choice(["Resign", "resign", "RESIGN"])])
        return {"args": SH_ARGS["SH3"], "ins": head + "\n".join(lines) + "\n",
                "check": exact_last(oracle.MSG_RESIGN)}
    bad = rng.choice(["1 2", "1 2 3", "12345 123456", "1234 12345",
                      "1234 1234567", "1234 112345", "abcd 123456",
                      "1234 123456 extra", " 1234 123456"])
    filler = filler_guesses(rng, rng.randrange(1, 5), (tp, tc))
    return {"args": SH_ARGS["SH3"],
            "ins": head + "\n".join(filler + [bad]) + "\n",
            "check": exact_last(*GUESS_ERRORS)}


# --- SH4 deck ----------------------------------------------------------------

def c_deck(rng: random.Random) -> dict | None:
    used: set[str] = set()
    tp, tc = rand_passcode(rng), rand_cipher(rng)
    head = f"{tp} {tc}\n"
    pick = rng.randrange(12)

    def bad_card(line: str) -> str:
        """Declare N cards, supply N-1 valid ones, then the invalid line.

        The invalid card has to sit *inside* the declared count, otherwise the
        oracle never reads it.
        """
        good = random_deck(rng, rng.randrange(MIN_DECK, MAX_DECK), used)
        cards = good[:-1] + [line.rstrip("\n")]
        return head + deck_block(cards)

    def with_tail(tail: str) -> str:
        cards = random_deck(rng, rng.randrange(MIN_DECK, MAX_DECK + 1), used)
        return head + deck_block(cards) + tail

    if pick == 0:
        bad = rng.choice(["a", "b", "Z", "-", "3.5", "-1", "eight"])
        return {"args": SH_ARGS["SH4"], "ins": head + bad + "\n",
                "check": exact_last(oracle.MSG_CARD_COUNT_NUM)}
    if pick == 1:
        # Numeric but out of range. "27" is deliberately absent: it is a legal
        # count, so the oracle would go on to read 27 cards.
        bad = rng.choice(["0", "1", "7", "99", "100", "29"])
        return {"args": SH_ARGS["SH4"], "ins": head + bad + "\n",
                "check": exact_last(oracle.MSG_CARD_COUNT_RANGE)}
    if pick == 2:
        bad = rng.choice(["Abcdefghi", "Verylongname", "Abcdefghij", "NameLong"])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"{bad} UFN\n"),
                "check": exact_last(oracle.MSG_NAME_LEN)}
    if pick == 3:
        bad = rng.choice(["Ab1", "A-b", "A_B", "123", "Na me"])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"{bad} UFN\n"),
                "check": exact_last(oracle.MSG_NAME_CHARS)}
    if pick == 4:
        names = names_for(rng, MIN_DECK + 1, used)
        clash = rng.choice([names[0], names[-1]])
        cards = [(n, code()) for n in names[:-1]] + [f"{clash} UFN"]
        return {"args": SH_ARGS["SH4"], "ins": head + deck_block(cards),
                "check": exact_last(oracle.MSG_NAME_UNIQUE)}
    if pick == 5:
        bad = rng.choice(["UF", "UFNN", "U", "UFNNN", ""])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"Zed {bad}\n"),
                "check": exact_last(oracle.MSG_EFFECT_LEN)}
    if pick == 6:
        bad = rng.choice(["XFN", "ZFN", "0FN"])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"Zed {bad}\n"),
                "check": exact_last(oracle.MSG_CRACK_CODE)}
    if pick == 7:
        bad = rng.choice(["UXN", "UZN", "UXN"])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"Zed {bad}\n"),
                "check": exact_last(oracle.MSG_REVEAL_CODE)}
    if pick == 8:
        bad = rng.choice(["UFZ", "UFQ", "UFI"])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"Zed {bad}\n"),
                "check": exact_last(oracle.MSG_BONUS_CODE)}
    if pick == 9:
        bad = rng.choice(["ufn", "Ufn", "uFN", "ufN", "Ufn"])
        return {"args": SH_ARGS["SH4"], "ins": bad_card(f"Zed {bad}\n"),
                "check": exact_last(oracle.MSG_CRACK_CODE, oracle.MSG_REVEAL_CODE,
                                    oracle.MSG_BONUS_CODE)}
    if pick == 10:
        # with_tail builds the deck itself; drawing twice would exhaust the
        # shared name pool.
        guesses = "\n".join(filler_guesses(rng, 10, (tp, tc))) + "\n"
        return {"args": SH_ARGS["SH4"], "ins": with_tail(guesses),
                "check": ends_with_terminator}
    bad = rng.choice(["8 extra", "8", " ", ""])
    guesses = "\n".join(filler_guesses(rng, 3, (tp, tc))) + "\n"
    return {"args": SH_ARGS["SH4"], "ins": head + bad + "\n" + guesses,
            "check": exact_last(oracle.MSG_WHITESPACE,
                                oracle.expected_tokens_message((1,)),
                                oracle.expected_tokens_message((2,)))}


# --- SH5 agentic manual ------------------------------------------------------

def _manual(rng: random.Random, plan_fn, check) -> dict | None:
    """Resolve names, then delegate to a plan function that cannot fail late."""
    plan = plan_fn(rng)
    if plan is None:
        return None
    used: set[str] = set()
    plays = [s for s in plan if s.get("effect")]
    if len(plays) > MAX_PLAYS:
        return None
    play_names = names_for(rng, len(plays), used)
    planned = list(zip(play_names,
                       [expand_effect(rng, s["effect"]) for s in plays]))
    target = MIN_DECK + rng.randrange(0, MAX_DECK - MIN_DECK - len(planned) + 1)
    deck = planned + random_deck(rng, target - len(planned), used)
    tp, tc = rand_passcode(rng), rand_cipher(rng)
    queue = list(deck)
    hand = [queue.pop(0) for _ in range(3)]

    lines: list[str] = []
    name_iter = iter(play_names)
    eff_iter = iter(effect for _n, effect in planned)
    for step in plan:
        base = (guess_of_kind(rng, tp, tc, step["crack"])
                if step.get("crack") else f"{rand_passcode(rng)} {rand_cipher(rng)}")
        if base is None:
            return None
        if step.get("effect"):
            name = next(name_iter)
            card = (name, next(eff_iter))
            if card not in hand:
                return None
            hand.remove(card)
            queue.append(card)
            hand.append(queue.pop(0))
            base += f" {name}"
        if step.get("digit"):
            base += f" {step['digit']}"
        lines.append(base)

    ins = (f"{tp} {tc}\n" + deck_block(deck) + "\n".join(lines) + "\n"
           + "\n".join(filler_guesses(rng, 20, (tp, tc))) + "\n")
    return {"args": SH_ARGS["SH5"], "ins": ins, "check": check}


def c_digit_range(rng: random.Random) -> dict | None:
    """Count/Map with a digit outside 1-6."""
    plan = [{"crack": None, "effect": rng.choice("CM"),
             "digit": rng.choice("7890x")}]
    return _manual(rng, lambda _rng: plan, exact_last(oracle.MSG_DIGIT_RANGE))


def c_round_range(rng: random.Random) -> dict | None:
    """Promote/Hindsight naming a round that does not exist yet."""
    play = rng.choice("PH")
    plan = [{"crack": "none", "effect": None},
            {"crack": "unordered", "effect": play, "digit": rng.choice(["7", "9"])}]
    return _manual(rng, lambda _rng: plan, exact_last(oracle.MSG_ROUND_NUMBER))


def c_not_in_hand(rng: random.Random) -> dict | None:
    """Play a card that exists in the deck but is not in the three-card hand."""
    used: set[str] = set()
    cards = random_deck(rng, rng.randrange(MIN_DECK + 3, MAX_DECK + 1), used)
    outsider = cards[-1]
    tp, tc = rand_passcode(rng), rand_cipher(rng)
    ins = (f"{tp} {tc}\n" + deck_block(cards)
           + f"{rand_passcode(rng)} {rand_cipher(rng)} {outsider[0]}\n")
    return {"args": SH_ARGS["SH5"], "ins": ins,
            "check": exact_last(oracle.MSG_NOT_IN_HAND)}


def c_extend_full(rng: random.Random) -> dict | None:
    """Extend on every round until the 20-guess ceiling refuses another.

    Each extend is cancelled by that round's own guess, so the ceiling is only
    reached on round 11 -- matching the official ``extd_cap`` transcript.
    """
    plan = [{"crack": None, "effect": "E"} for _ in range(11)]
    return _manual(rng, lambda _rng: plan,
                   contains(oracle.MSG_EXTEND_FULL, oracle.MSG_EXTEND))


def c_prmt(rng: random.Random) -> dict | None:
    """Promote a none crack (becomes unordered) and an unordered crack.

    The default card reveals fully, so Promote is driven purely by the crack
    kinds engineered into rounds 1 and 2.
    """
    if rng.random() < 0.5:
        plan = [{"crack": "none", "effect": None},
                {"crack": "unordered", "effect": "P", "digit": "1"}]
        needles = ("is now unordered.",)
    else:
        plan = [{"crack": "unordered", "effect": None},
                {"crack": "unordered", "effect": "P", "digit": "1"},
                {"crack": "none", "effect": "P", "digit": "2"}]
        needles = ("is now ordered.",)
    if rng.random() < 0.18:
        return c_round_range(rng)
    return _manual(rng, lambda _rng: plan, contains(*needles))


def c_hdst(rng: random.Random) -> dict | None:
    """Hindsight needs a hidden reveal, so round 1 must play an H-reveal card."""
    if rng.random() < 0.18:
        return c_round_range(rng)
    if rng.random() < 0.12:
        return c_not_in_hand(rng)
    plan = [{"crack": "ordered", "effect": "H"},
            {"crack": None, "effect": "H", "digit": "1"},
            {"crack": None, "effect": "H", "digit": "2"}]
    return _manual(rng, lambda _rng: plan, contains("has been exposed."))


def c_mapp(rng: random.Random) -> dict | None:
    if rng.random() < 0.2:
        return c_digit_range(rng)
    plan = [{"crack": None, "effect": "M", "digit": str(rng.randrange(1, 7))}
            for _ in range(3)]
    return _manual(rng, lambda _rng: plan, contains("maps to"))


def c_cont(rng: random.Random) -> dict | None:
    if rng.random() < 0.2:
        return c_digit_range(rng)
    plan = [{"crack": None, "effect": "C", "digit": str(rng.randrange(1, 7))}
            for _ in range(3)]
    return _manual(rng, lambda _rng: plan, contains(" appears "))


def c_toss(rng: random.Random) -> dict | None:
    """Toss discards the whole hand, so only the first round can play."""
    plan = [{"crack": "ordered", "effect": "T"},
            {"crack": None, "effect": None},
            {"crack": None, "effect": None}]
    return _manual(rng, lambda _rng: plan, contains(oracle.MSG_TOSS))


def c_extd(rng: random.Random) -> dict | None:
    if rng.random() < 0.22:
        return c_extend_full(rng)
    plan = [{"crack": "ordered", "effect": "E"},
            {"crack": None, "effect": "E"},
            {"crack": None, "effect": "N"}]
    return _manual(rng, lambda _rng: plan,
                   contains(oracle.MSG_EXTEND, oracle.MSG_NO_BONUS))


def c_revlc(rng: random.Random) -> dict | None:
    plan = [{"crack": "unordered", "effect": code("U", "F", "N")},
            {"crack": None, "effect": code("U", "H", "N")},
            {"crack": "ordered", "effect": code("N", "F", "N")}]
    return _manual(rng, lambda _rng: plan, contains("XXXXXX"))


def c_crck(rng: random.Random) -> dict | None:
    kinds = rng.choice([["ordered", "unordered", "none"],
                        ["none", "ordered", "unordered"],
                        ["unordered", "none", "ordered"]])
    plan = [{"crack": k, "effect": code(k[0].upper() if k != "none" else "U",
                                        rng.choice(REVEAL_CODES), "N")}
            for k in kinds]
    return _manual(rng, lambda _rng: plan, contains("●", "○"))


def c_alll(rng: random.Random) -> dict | None:
    """Replay chains and mixed bonus sequences.

    Replay delegates digit validation to the effect it repeats, so a Replay of
    Extend or Toss must not carry a digit at all.
    """
    pick = rng.randrange(5)
    if pick == 0:
        plan = [{"crack": None, "effect": "M", "digit": "1"},
                {"crack": None, "effect": "R", "digit": "1"},
                {"crack": None, "effect": "C", "digit": "3"}]
        return _manual(rng, lambda _rng: plan, contains("Replay: ", "appears"))
    if pick == 1:
        plan = [{"crack": "ordered", "effect": "E"},
                {"crack": None, "effect": "R"},
                {"crack": None, "effect": "N"}]
        return _manual(rng, lambda _rng: plan, contains("Replay: "))
    if pick == 2:
        plan = [{"crack": "ordered", "effect": "H"},
                {"crack": None, "effect": "H", "digit": "1"},
                {"crack": None, "effect": "R", "digit": "1"}]
        return _manual(rng, lambda _rng: plan, contains("Replay: ", "has been"))
    if pick == 3:
        plan = [{"crack": "none", "effect": None},
                {"crack": "unordered", "effect": "P", "digit": "1"},
                {"crack": None, "effect": "R", "digit": "1"}]
        return _manual(rng, lambda _rng: plan, contains("Replay: ", "is now"))
    plan = [{"crack": "ordered", "effect": "T"},
            {"crack": None, "effect": "R"},
            {"crack": None, "effect": "R"}]
    return _manual(rng, lambda _rng: plan, contains("Replay: ", oracle.MSG_TOSS))


# --- SH6/SH7/SH8 AI ----------------------------------------------------------

def c_ai(rng: random.Random, sh: str, agentic: bool) -> dict | None:
    used: set[str] = set()
    n = rng.randrange(MIN_DECK, MAX_DECK + 1)
    deck = random_deck(rng, n, used)
    tp, tc = rand_passcode(rng), rand_cipher(rng)
    ins = f"{tp} {tc}\n"
    if agentic:
        ins += deck_block(deck)
    return {"args": SH_ARGS[sh], "ins": ins, "check": ends_with_terminator}


# --- plan --------------------------------------------------------------------

PLAN: list[tuple[str, str, int, Callable[[random.Random], dict | None], str]] = [
    ("SH2", "arge", 93, c_arge, "high"),
    ("SH3", "rsgn", 60, c_rsgn, "high"),
    ("SH3", "game", 327, c_game, "high"),
    ("SH4", "deck", 20, c_deck, "high"),
    ("SH5", "crck", 45, c_crck, "high"),
    ("SH5", "revl", 35, c_revlc, "high"),
    ("SH5", "toss", 35, c_toss, "high"),
    ("SH5", "extd", 35, c_extd, "high"),
    ("SH5", "prmt", 40, c_prmt, "high"),
    ("SH5", "hdst", 40, c_hdst, "high"),
    ("SH5", "mapp", 40, c_mapp, "high"),
    ("SH5", "cont", 40, c_cont, "high"),
    ("SH5", "alll", 30, c_alll, "high"),
    ("SH6", "cigs", 70, lambda r: c_ai(r, "SH6", False), "low"),
    ("SH7", "lkgs", 90, lambda r: c_ai(r, "SH7", False), "low"),
    ("SH8", "agsh", 45, lambda r: c_ai(r, "SH8", True), "low"),
    ("SH8", "agsm", 45, lambda r: c_ai(r, "SH8", True), "low"),
    ("SH8", "agsr", 45, lambda r: c_ai(r, "SH8", True), "low"),
    ("SH8", "agsa", 45, lambda r: c_ai(r, "SH8", True), "low"),
]

AGSH_OVERRIDE = 20


def digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def parse_public_args(stem: str, default: list[str]) -> list[str]:
    for key, count in (("sparg", 2), ("noargs", 0), ("onearg", 1),
                       ("thrarg", 3)):
        i = stem.find(key)
        if i == -1:
            continue
        chunk = stem[i + len(key): i + len(key) + count]
        if len(chunk) == count:
            return list(chunk)
    return list(default)


def public_fingerprints() -> set[str]:
    """``(args, stdin)`` fingerprints of every official public test."""
    seen: set[str] = set()
    for sh, args in SH_ARGS.items():
        indir = os.path.join(TESTS_ROOT, sh, "public", "ins")
        if not os.path.isdir(indir):
            continue
        for name in sorted(os.listdir(indir)):
            if not name.endswith(".txt"):
                continue
            with open(os.path.join(indir, name), encoding="utf-8") as fh:
                text = fh.read()
            use = parse_public_args(name[:-4], args)
            seen.add(digest(repr(use), text))
    return seen


def make_name(category: str, seq: int, args: list[str], sh: str) -> str:
    if args == SH_ARGS[sh]:
        return f"{category}_gen{seq:04d}"
    if len(args) == 2:
        if category in ("arge", "argc"):
            return f"{category}_gen{seq:04d}_sparg{''.join(args)}"
        return f"{category}_sparg{''.join(args)}_gen{seq:04d}"
    if len(args) == 0:
        return f"{category}_gen{seq:04d}_noargs"
    if len(args) == 1:
        return f"{category}_gen{seq:04d}_onearg{args[0]}"
    return f"{category}_gen{seq:04d}_thrarg{''.join(args)}"


def write_pair(sh: str, name: str, ins: str, outs: str) -> None:
    base = os.path.join(OUT_ROOT, sh, "public")
    for sub, text in (("ins", ins), ("outs", outs)):
        path = os.path.join(base, sub)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(text)


def emit(rows: list[dict], public: set[str], seen: set[str], sh: str,
         name: str, args: list[str], ins: str, outs: str,
         category: str, confidence: str) -> bool:
    input_fp = digest(repr(args), ins)
    triple_fp = digest(repr(args), ins, outs)
    if input_fp in public or input_fp in seen or triple_fp in seen:
        return False
    seen.add(input_fp)
    seen.add(triple_fp)
    write_pair(sh, name, ins, outs)
    rows.append({
        "sh": sh, "category": category, "test": name,
        "args": " ".join(args) if args else "(none)",
        "confidence": confidence,
        "ins_sha256": hashlib.sha256(ins.encode()).hexdigest(),
        "outs_sha256": hashlib.sha256(outs.encode()).hexdigest(),
    })
    return True


def main() -> int:
    print(f"seed = {SEED}")
    if os.path.isdir(OUT_ROOT):
        shutil.rmtree(OUT_ROOT)
    os.makedirs(OUT_ROOT, exist_ok=True)

    public = public_fingerprints()
    seen: set[str] = set()
    rows: list[dict] = []
    short: list[str] = []

    for sh, category, count, builder, confidence in PLAN:
        rng = random.Random(f"{SEED}:{category}")
        made = 0
        attempts = 0
        limit = count * 800 + 4000
        while made < count and attempts < limit:
            attempts += 1
            cand = builder(rng)
            if cand is None:
                continue
            args, ins, check = cand["args"], cand["ins"], cand["check"]
            if cand.get("stage") == "sh2":
                # Argument-validation-only stage: no game is played.
                outs = ""
            else:
                try:
                    outs = oracle.run_args(args, ins)
                except Exception:  # noqa: BLE001 - reject what oracle dislikes
                    continue
            if not check(outs):
                continue
            name = make_name(category, made + 1, args, sh)
            if emit(rows, public, seen, sh, name, args, ins, outs,
                    category, confidence):
                made += 1
        if made < count:
            short.append(f"{category}: {made}/{count}")
        print(f"  {sh} {category:<5} {made:>4}/{count}")

    rng = random.Random(f"{SEED}:agsh-override")
    made = 0
    attempts = 0
    while made < AGSH_OVERRIDE and attempts < AGSH_OVERRIDE * 800:
        attempts += 1
        cand = c_ai(rng, "SH8", True)
        if cand is None:
            continue
        args = ["1", "1" if made % 2 == 0 else "2"]
        try:
            outs = oracle.run_args(args, cand["ins"])
        except Exception:  # noqa: BLE001
            continue
        if not ends_with_terminator(outs):
            continue
        keyword = "sparg11" if args[1] == "1" else "sparg12"
        name = f"agsh_{keyword}_gen{made + 1:04d}"
        if emit(rows, public, seen, "SH8", name, args, cand["ins"], outs,
                "agsh", "low"):
            made += 1
    print(f"  SH8 agsh    {made:>4}/{AGSH_OVERRIDE}  (sparg11 / sparg12)")

    manifest = os.path.join(_HERE, "MANIFEST.csv")
    with open(manifest, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\ntotal pairs: {len(rows)}")
    print("manifest:    tools/testgen/MANIFEST.csv")
    if short:
        print("\nshortfalls (fewer distinct cases exist than requested):")
        for s in short:
            print(f"  {s}")
    return 0


if __name__ == "__main__":
    # Python randomises string hashing per process, so any code path that
    # iterates a set of strings can emit its cases in a different order on every
    # run. The seed alone is therefore not enough to make this generator
    # reproducible. Re-exec once with a pinned hash seed so that a given seed
    # always produces byte-identical files.
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        # -u so that progress is visible when output is redirected; without it
        # the child's stdout is block-buffered and the run looks hung.
        os.execv(sys.executable,
                 [sys.executable, "-u", os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit(main())