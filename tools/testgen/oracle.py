"""Spec-only reference implementation of Cipherlock.

Written from rw144_project_1.6.pdf and the public examples in tests/.
Nothing under src/ was read or imported.

The public API is ``run(text, game_type, ai_type) -> str``: feed it the contents
of a test's input file and it returns the exact stdout that
scripts/marking_script.py compares against.

Verification: tools/testgen/verify_public.py replays all 102 public ins/outs
pairs through this module and requires byte-exact agreement.
"""

from __future__ import annotations

import re

# --- Unicode -----------------------------------------------------------------

FULL = "●"  # ●
EMPTY = "○"  # ○
HALF = "-"
NONE_CRACK = "XXXX"
HIDDEN_REVEAL = "XXXXXX"

# --- Messages ----------------------------------------------------------------

MSG_FEW_ARGS = "Too few arguments. Expected 2."
MSG_MANY_ARGS = "Too many arguments. Expected 2."
MSG_GAME_TYPE = 'The game type should be "0" for vanilla, or "1" for agentic.'
MSG_AI_TYPE = (
    'The AI type should be "0" for no AI, "1" for the cipher guess strategy, '
    '"2" for the Vanilla guess strategy, or "3" for the Agentic guess strategy.'
)
MSG_AI3_VANILLA = "AI type 3 can only be played for game type 1."
MSG_WHITESPACE = "Too many whitespaces detected."
MSG_CODE_LEN = "A code must be 4 digits."
MSG_CODE_DIGITS = "A code must contain only the digits 1-6."
MSG_CIPHER_LEN = "A cipher must be 6 digits."
MSG_CIPHER_DIGITS = "A cipher must contain only the digits 1-6."
MSG_CIPHER_REPEAT = "No digit may be repeated in a cipher."
MSG_RESIGN = "The Hacker resigned."
MSG_RESIGN_ONLY = "Expected resignation."
MSG_CARD_COUNT_NUM = "Agent card count must be a number."
MSG_CARD_COUNT_RANGE = "You must select a minimum of 8 and a maximum of 28 agent cards."
MSG_NAME_LEN = "An agent name must have at most 8 letters."
MSG_NAME_CHARS = "An agent name must only contain letters."
MSG_NAME_UNIQUE = "An agent name must be unique."
MSG_EFFECT_LEN = "Effects must be 3 characters long."
MSG_CRACK_CODE = "Crack effect code is invalid."
MSG_REVEAL_CODE = "Reveal effect code is invalid."
MSG_BONUS_CODE = "Bonus effect code is invalid."
MSG_NOT_IN_HAND = "You must play an agent that is in your hand."
MSG_WIN = "Congratulations! You solved the cipherlock."
MSG_LOSS = "You have run out of guesses. Better luck next time!"

MSG_NO_BONUS = "No bonus applied."
MSG_EXTEND = "Added extra guess."
MSG_EXTEND_FULL = "No extra guess was added."
MSG_TOSS = "Tossed all cards."
MSG_NO_HIDDEN = "No hidden reveals can be exposed."
MSG_NO_CRACKS = "No cracks can be promoted."
MSG_ROUND_NUMBER = "Agent digit must be a valid round number."
MSG_DIGIT_RANGE = "Agent digit must be a value from 1-6."

# Bonus effects that take no agent digit.
NO_DIGIT_EFFECTS = {"E": "Extend", "T": "Toss", "N": "None"}
# Bonus effects that require an agent digit.
DIGIT_EFFECTS = {"C": "Count", "M": "Map", "H": "Hindsight", "P": "Promote"}
CRACK_CODES = {"U", "O", "N"}
REVEAL_CODES = {"F", "H"}
BONUS_CODES = {"E", "C", "M", "R", "T", "H", "P", "N"}

DEFAULT_CARD = ("DEFAULT", "UFN")

PROMPT_SETUP = "Enter the true-passcode and true-cipher:\n○○○○ 123456\n↓↓↓↓ ↓↓↓↓↓↓\n"
PROMPT_CARD_COUNT = "How many agent cards will you add?\n"
PROMPT_VANILLA_GUESS = "Enter a guess-passcode and guess-cipher:\n○○○○ 123456\n↓↓↓↓ ↓↓↓↓↓↓\n"
PROMPT_AGENTIC_GUESS = (
    "Enter a guess-passcode and guess-cipher, and play an agent card "
    "(optional). Also enter the agent digit if required.\n"
    "○○○○ 123456 Agent and digit\n↓↓↓↓ ↓↓↓↓↓↓ ↓\n"
)


class Terminate(Exception):
    """Raised to end the program with a message and exit status 0."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Crash(Exception):
    """Raised when the spec leaves the outcome undefined; never generated."""


# --- Input validation --------------------------------------------------------


def check_whitespace(line: str) -> None:
    """Section 7.2.1 whitespace rules."""
    if "\t" in line:
        raise Terminate(MSG_WHITESPACE)
    if line != line.strip(" "):
        raise Terminate(MSG_WHITESPACE)
    if "  " in line:
        raise Terminate(MSG_WHITESPACE)


def tokenize(line: str, allowed: tuple[int, ...]) -> list[str]:
    """Validate one input line and return its tokens.

    ``allowed`` is the set of acceptable token counts; ``0`` means "any".
    """
    check_whitespace(line)
    tokens = line.split(" ") if line else []
    if not tokens or tokens == [""]:
        tokens = []
    count = len(tokens)
    if 0 not in allowed and count not in allowed:
        raise Terminate(expected_tokens_message(allowed))
    return tokens


def expected_tokens_message(allowed: tuple[int, ...]) -> str:
    if len(allowed) == 1:
        if allowed[0] == 1:
            return "Expected 1 input token."
        return f"Expected {allowed[0]} input tokens."
    if len(allowed) == 2:
        return f"Expected {allowed[0]} or {allowed[1]} input tokens."
    listing = [str(n) for n in allowed[:-1]]
    return f"Expected {', '.join(listing)} or {allowed[-1]} input tokens."


def validate_code(token: str) -> None:
    """Passcode validation, priority: length, then digits."""
    if len(token) != 4:
        raise Terminate(MSG_CODE_LEN)
    if any(ch not in "123456" for ch in token):
        raise Terminate(MSG_CODE_DIGITS)


def validate_cipher(token: str) -> None:
    """Cipher validation, priority: length, digits, repetition."""
    if len(token) != 6:
        raise Terminate(MSG_CIPHER_LEN)
    if any(ch not in "123456" for ch in token):
        raise Terminate(MSG_CIPHER_DIGITS)
    if len(set(token)) != 6:
        raise Terminate(MSG_CIPHER_REPEAT)


def normalize_name(name: str) -> str:
    """Standard capitalization: first letter upper, rest lower."""
    return name.capitalize()


def validate_agent_name(name: str, existing: set[str]) -> str:
    if len(name) > 8:
        raise Terminate(MSG_NAME_LEN)
    if not name.isalpha():
        raise Terminate(MSG_NAME_CHARS)
    normalized = normalize_name(name)
    if normalized in existing:
        raise Terminate(MSG_NAME_UNIQUE)
    return normalized


def validate_effects(code: str) -> None:
    """Priority: length, crack, reveal, bonus. Codes must be uppercase."""
    if len(code) != 3:
        raise Terminate(MSG_EFFECT_LEN)
    if code[0] not in CRACK_CODES:
        raise Terminate(MSG_CRACK_CODE)
    if code[1] not in REVEAL_CODES:
        raise Terminate(MSG_REVEAL_CODE)
    if code[2] not in BONUS_CODES:
        raise Terminate(MSG_BONUS_CODE)


# --- Feedback primitives -----------------------------------------------------


def lock_of(cipher: str, passcode: str) -> str:
    """Lockcode for a guess: lock[i] = cipher[passcode[i] - 1]."""
    return "".join(cipher[int(d) - 1] for d in passcode)


def crack_unordered(lock: str, true_lock: str) -> str:
    """Vanilla crack: positional full dots, then multiset half dots."""
    full = [lock[i] == true_lock[i] for i in range(4)]
    n_full = sum(full)
    rest = [i for i in range(4) if not full[i]]
    used = [False] * 4
    n_half = 0
    for i in rest:
        for j in rest:
            if not used[j] and true_lock[j] == lock[i]:
                used[j] = True
                n_half += 1
                break
    return FULL * n_full + EMPTY * n_half + HALF * (4 - n_full - n_half)


def crack_ordered(lock: str, true_lock: str) -> str:
    """Ordered crack: each symbol sits where its digit actually is.

    Exact positional matches are claimed first, in a separate pass. Doing it in
    one pass lets an early half-dot steal the true-lockcode slot that a later
    symbol belongs in: guessing 1122 against 5432 must read ``---●``, not
    ``--○●``. Two passes give that, and still give the spec's own example of
    ``●○○●`` for 1313 against 1133.
    """
    out = [HALF] * 4
    used = [False] * 4
    for i in range(4):
        if lock[i] == true_lock[i]:
            out[i] = FULL
            used[i] = True
    for i in range(4):
        if out[i] == FULL:
            continue
        for j in range(4):
            if not used[j] and true_lock[j] == lock[i]:
                out[i] = EMPTY
                used[j] = True
                break
    return "".join(out)


def crack_with(lock: str, true_lock: str, code: str) -> str:
    if code == "O":
        return crack_ordered(lock, true_lock)
    if code == "N":
        return NONE_CRACK
    return crack_unordered(lock, true_lock)


def reveal_with(cipher: str, true_cipher: str, code: str) -> str:
    if code == "H":
        return HIDDEN_REVEAL
    return "".join(
        true_cipher[i] if true_cipher[i] == cipher[i] else HALF for i in range(6)
    )


def crack_score(code: str, pool_size: int, solved: bool) -> int:
    """Value of a crack effect, section 10.3.2."""
    if code == "U":
        if solved:
            return 0
        if pool_size >= 800:
            return 4
        if pool_size >= 300:
            return 3
        if pool_size >= 80:
            return 2
        return 1
    if code == "O":
        if solved:
            return 0
        if pool_size >= 300:
            return 5
        if pool_size >= 100:
            return 4
        return 2
    return 0 if solved else -2


def reveal_value(code: str, unknown: int) -> int:
    """Value of a reveal effect, section 10.3.3."""
    if code == "F":
        if unknown > 2:
            return 2
        if unknown > 1:
            return 1
        return 0
    return 0 if unknown == 0 else -2

# --- Rendering ---------------------------------------------------------------

GUESS_WIDTHS = (2, 6, 8)
GUESS_TITLES = ("##", "Code", "Cipher")
FEEDBACK_WIDTHS = (6, 7, 8)
FEEDBACK_TITLES = ("Lock", "Crack", "Reveal")
AGENTIC_GUESS_WIDTHS = (2, 6, 8, 10, 5, 4)
AGENTIC_GUESS_TITLES = ("##", "Code", "Cipher", "Agent", "CRB", "D")
TL, TR, BL, BR = "┌", "┐", "└", "┘"
H, V = "─", "│"
H2, V2 = "┬", "┼"
BT_ = "┴"
LT, RT = "├", "┤"


def cell(text: str, width: int) -> str:
    """A table cell: one space either side of the value.

    The 2-wide guess-number column is the exception -- it carries no padding,
    so ``1`` renders as ``1 `` and ``10`` as ``10``.
    """
    if width == 2:
        return text.ljust(width)
    return " " + text.ljust(width - 2) + " "


def title_bar(guess_no: int, remaining: int) -> str:
    """Width 44, interior 42, 11 spaces before the G of Guess."""
    inner = 42
    body = (" " * 11 + f"Guess {guess_no} ({remaining} remaining)").ljust(inner)
    return (TL + H * inner + TR + "\n"
            + V + body + V + "\n"
            + BL + H * inner + BR + "\n")


def table(agentic: bool, rows: list[list[str]]) -> str:
    """Render a full feedback table from raw cell values.

    Border junctions differ per line: the top border is solid apart from the
    single ``┬`` splitting Guess from Feedback, the first separator row uses
    ``┬`` within each section and ``┼`` between them, the second separator row
    uses ``┼`` throughout, and the bottom border uses ``┴`` throughout.
    """
    if agentic:
        gw = list(AGENTIC_GUESS_WIDTHS)
        gt = list(AGENTIC_GUESS_TITLES)
        bonus = max(len(r[-1]) for r in rows) + 2
        fw = list(FEEDBACK_WIDTHS) + [bonus]
        ft = list(FEEDBACK_TITLES) + ["Bonus"]
    else:
        gw = list(GUESS_WIDTHS)
        gt = list(GUESS_TITLES)
        fw = list(FEEDBACK_WIDTHS)
        ft = list(FEEDBACK_TITLES)

    g_flat = H * (sum(gw) + len(gw) - 1)
    f_flat = H * (sum(fw) + len(fw) - 1)
    g_rule = H2.join(H * w for w in gw)
    f_rule = H2.join(H * w for w in fw)

    def body(cells: list[str]) -> str:
        n = len(gw)
        return V + V.join(cells[:n]) + V + V.join(cells[n:]) + V

    header = [cell(t, w) for t, w in zip(gt, gw)] + [cell(t, w) for t, w in zip(ft, fw)]

    out = [
        TL + g_flat + H2 + f_flat + TR,
        V + cell("Guess", sum(gw) + len(gw) - 1) + V
        + cell("Feedback", sum(fw) + len(fw) - 1) + V,
        LT + g_rule + V2 + f_rule + RT,
        body(header),
        LT + V2.join(H * w for w in gw) + V2 + V2.join(H * w for w in fw) + RT,
    ]
    for row in rows:
        n = len(gw)
        out.append(body([cell(v, w) for v, w in zip(row[:n], gw)]
                        + [cell(v, w) for v, w in zip(row[n:], fw)]))
    out.append(BL + BT_.join(H * w for w in gw) + BT_
               + BT_.join(H * w for w in fw) + BR)
    return "\n".join(out) + "\n"


def hand_box(hand: list["AgentCard"]) -> str:
    out = [TL + H * 16 + TR, V + "  Your Agents".ljust(16) + V,
           LT + H * 10 + H2 + H * 5 + RT]
    for card in hand:
        out.append(V + cell(card.name, 10) + V + cell(card.code, 5) + V)
    out.append(BL + H * 10 + BT_ + H * 5 + BR)
    return "\n".join(out) + "\n"


# --- Agent deck --------------------------------------------------------------


class AgentCard:
    __slots__ = ("name", "code")

    def __init__(self, name: str, code: str) -> None:
        self.name = name
        self.code = code

    @property
    def crack(self) -> str:
        return self.code[0]

    @property
    def reveal(self) -> str:
        return self.code[1]

    @property
    def bonus(self) -> str:
        return self.code[2]


class Deck:
    """Cards are drawn from the front and returned to the back, unshuffled."""

    def __init__(self, cards: list[AgentCard]) -> None:
        self.cards = list(cards)
        self.hand: list[AgentCard] = []

    def draw_to_three(self) -> None:
        while len(self.hand) < 3:
            self.hand.append(self.cards.pop(0))

    def play(self, card: AgentCard) -> None:
        """Remove from hand, push to the back of the deck, refill."""
        self.hand.remove(card)
        self.cards.append(card)
        self.draw_to_three()

    def toss(self, card: AgentCard) -> None:
        """Discard the card played, then the rest oldest-first, then draw 3."""
        self.hand.remove(card)
        self.cards.append(card)
        for held in list(self.hand):
            self.hand.remove(held)
            self.cards.append(held)
        self.hand = []
        self.draw_to_three()

    def find(self, name: str) -> AgentCard | None:
        for card in self.hand:
            if card.name.lower() == name.lower():
                return card
        return None


# --- Guess bookkeeping -------------------------------------------------------


class GuessRow:
    """One row of the feedback table, plus the state needed to rewrite it."""

    def __init__(self, passcode: str, cipher: str, card: AgentCard,
                 digit: str | None, lock: str, crack: str, reveal: str,
                 bonus: str, effect_code: str) -> None:
        self.passcode = passcode
        self.cipher = cipher
        self.card = card
        self.digit = digit
        self.lock = lock
        self.crack = crack
        self.reveal = reveal
        self.bonus = bonus
        self.effect_code = effect_code
        # Raw forms, before Promote / Hindsight rewrite any earlier row.
        self.raw_crack = crack
        self.raw_reveal = reveal
        # Current crack kind, which Promote advances N -> U -> O. The card's
        # own code is only the starting point.
        self.crack_kind = card.crack

    def display(self, agentic: bool, guess_no: int) -> list[str]:
        if agentic:
            name = self.card.name
            code = self.card.code
            digit = self.digit if self.digit is not None else "X"
            head = [str(guess_no), self.passcode, self.cipher, name, code, digit]
            return head + [self.lock, self.crack, self.reveal, self.bonus]
        return [str(guess_no), self.passcode, self.cipher,
                self.lock, self.crack, self.reveal]


# --- The game ----------------------------------------------------------------


class Game:
    def __init__(self, out: list[str], game_type: int, ai_type: int) -> None:
        self.out = out
        self.game_type = game_type
        self.ai_type = ai_type
        self.agentic = game_type == 1
        self.rows: list[GuessRow] = []
        self.deck: Deck | None = None
        self.true_passcode = ""
        self.true_cipher = ""
        self.true_lock = ""
        self.guesses_remaining = 10
        self.ai_resign_next = False
        self.ai: "VanillaAI | None" = None
        # Last non-Replay, non-None bonus effect, for Replay.
        self.last_bonus: tuple[str, str | None] | None = None

    def attach_ai(self) -> None:
        """Build the AI for this game type and ai_type."""
        if self.agentic:
            # Only ai_type 3 evaluates agent cards. Strategies 1 and 2 choose a
            # guess-lockcode only and never play a card, so in an agentic game
            # they still decline every card: the Hacker column reads DEFAULT and
            # the bonus column reads "No bonus applied.". Only ai_type 3 uses
            # the Knuth/minimax selector, and it is the only strategy that
            # records bonus outcomes back into its pools.
            if self.ai_type == 3:
                self.ai = AgenticAI(self)
            elif self.ai_type == 2:
                self.ai = VanillaAI(self.true_passcode, self.true_cipher,
                                    use_lock_strategy=True)
            else:
                self.ai = VanillaAI(self.true_passcode, self.true_cipher,
                                    use_lock_strategy=False)
        elif self.ai_type == 1:
            self.ai = VanillaAI(self.true_passcode, self.true_cipher,
                                use_lock_strategy=False)
        else:
            self.ai = VanillaAI(self.true_passcode, self.true_cipher)

    def ai_move(self, guess_no: int) -> str:
        if self.ai_resign_next:
            self.ai_resign_next = False
            self.emit("Resign\n")
            raise Terminate(MSG_RESIGN)
        return self.ai.next_move()

    def emit(self, text: str) -> None:
        self.out.append(text)

    # -- setup ---------------------------------------------------------------

    def setup(self, lines: list[str]) -> None:
        self.emit(PROMPT_SETUP)
        tokens = tokenize(lines.pop(0), (2,))
        validate_code(tokens[0])
        validate_cipher(tokens[1])
        self.true_passcode = tokens[0]
        self.true_cipher = tokens[1]
        self.true_lock = lock_of(self.true_cipher, self.true_passcode)

        if self.agentic:
            self.emit(PROMPT_CARD_COUNT)
            count_line = lines.pop(0)
            check_whitespace(count_line)
            raw = count_line.strip()
            if not raw.isdigit():
                raise Terminate(MSG_CARD_COUNT_NUM)
            count = int(raw)
            if count < 8 or count > 28:
                raise Terminate(MSG_CARD_COUNT_RANGE)
            cards: list[AgentCard] = []
            seen: set[str] = set()
            for index in range(1, count + 1):
                self.emit(f"Enter agent name and effects for agent {index}:\n")
                parts = tokenize(lines.pop(0), (2,))
                name = validate_agent_name(parts[0], seen)
                validate_effects(parts[1])
                seen.add(name)
                cards.append(AgentCard(name, parts[1]))
            self.deck = Deck(cards)
            self.deck.draw_to_three()

    # -- guess input parsing -------------------------------------------------

    def parse_guess(self, line: str) -> tuple[str, str, AgentCard, "AgentCard | None", str | None]:
        """Return (passcode, cipher, displayed card, played card, digit).

        ``displayed`` is DEFAULT when no card was played; ``played`` is None in
        that case, which is what drives deck handling and bonus selection.
        """
        default = AgentCard(DEFAULT_CARD[0], DEFAULT_CARD[1])
        if not self.agentic:
            tokens = tokenize(line, (1, 2))
            if len(tokens) == 1:
                if tokens[0].lower() != "resign":
                    raise Terminate(MSG_RESIGN_ONLY)
                raise Terminate(MSG_RESIGN)
            validate_code(tokens[0])
            validate_cipher(tokens[1])
            return tokens[0], tokens[1], default, None, None

        tokens = tokenize(line, (1, 2, 3, 4))
        if len(tokens) == 1:
            if tokens[0].lower() != "resign":
                raise Terminate(MSG_RESIGN_ONLY)
            raise Terminate(MSG_RESIGN)
        if len(tokens) <= 2:
            validate_code(tokens[0])
            validate_cipher(tokens[1])
            return tokens[0], tokens[1], default, None, None

        validate_code(tokens[0])
        validate_cipher(tokens[1])
        card = self.deck.find(tokens[2])
        if card is None:
            raise Terminate(MSG_NOT_IN_HAND)
        digit = tokens[3] if len(tokens) == 4 else None
        return tokens[0], tokens[1], card, card, digit

    # -- bonus effects -------------------------------------------------------

    def promotable_rounds(self) -> list[int]:
        """Guess numbers whose crack is currently none or unordered."""
        return [i + 1 for i, r in enumerate(self.rows)
                if r.crack_kind in ("N", "U")]

    def hidden_rounds(self) -> list[int]:
        """Guess numbers whose reveal is currently hidden."""
        return [i + 1 for i, r in enumerate(self.rows)
                if r.reveal == HIDDEN_REVEAL]

    def validate_digit(self, effect: str, digit: str | None,
                       previous_round: int) -> None:
        """Agent-digit validation for a single non-Replay effect.

        For Hindsight and Promote an empty candidate set makes validation
        skippable per section 9.3; see AMBIGUITIES.md entry 2 for why the
        "no candidates" feedback then wins over a bad digit.
        """
        if effect not in DIGIT_EFFECTS:
            if digit is not None:
                name = NO_DIGIT_EFFECTS[effect]
                raise Terminate(
                    f"{name} bonus effect should not have an agent digit."
                )
            return

        if effect == "H" and not self.hidden_rounds():
            return
        if effect == "P" and not self.promotable_rounds():
            return

        if digit is None:
            name = DIGIT_EFFECTS[effect]
            raise Terminate(f"{name} bonus effect should have an agent digit.")

        if effect in ("C", "M"):
            if digit not in "123456":
                raise Terminate(MSG_DIGIT_RANGE)
            return

        if not digit.isdigit() or not (1 <= int(digit) <= previous_round):
            raise Terminate(MSG_ROUND_NUMBER)
        if effect == "H" and int(digit) not in self.hidden_rounds():
            raise Terminate(f"The reveal on guess {digit} is not hidden.")
        if effect == "P" and int(digit) not in self.promotable_rounds():
            raise Terminate(f"The crack on guess {digit} is already ordered.")

    def round_of(self, digit: str | None) -> int | None:
        """The guess number a Promote/Hindsight digit names, if it names one."""
        if digit is None or not digit.isdigit() or int(digit) == 0:
            return None
        return int(digit)

    def apply_bonus(self, effect: str, digit: str | None, guess_no: int) -> tuple[str, str | None]:
        """Apply one bonus effect and return (feedback, digit used).

        Hindsight and Promote check for an empty candidate set before the digit
        is validated at all, per the more specific wording of 9.3.5 / 9.3.6.
        """
        if effect == "N":
            return MSG_NO_BONUS, None

        if effect == "E":
            if guess_no - 1 + self.guesses_remaining == 20:
                return MSG_EXTEND_FULL, None
            self.guesses_remaining += 1
            return MSG_EXTEND, None

        if effect == "T":
            return MSG_TOSS, None

        if effect == "C":
            assert digit is not None
            return f"{digit} appears {self.true_lock.count(digit)} times.", digit

        if effect == "M":
            assert digit is not None
            return f"{digit} maps to {self.true_cipher[int(digit) - 1]}.", digit

        if effect == "H":
            # Skipped validation means an absent *or* unusable digit both land
            # here, so membership in the candidate rounds is what matters.
            # A supplied digit is still displayed even when validation was
            # skipped and the effect had nothing to work on.
            if self.round_of(digit) not in self.hidden_rounds():
                return MSG_NO_HIDDEN, digit
            row = self.rows[int(digit) - 1]
            row.reveal = self.full_reveal(row)
            return f"Reveal on round {digit} has been exposed.", digit

        if effect == "P":
            if self.round_of(digit) not in self.promotable_rounds():
                return MSG_NO_CRACKS, digit
            row = self.rows[int(digit) - 1]
            if row.crack_kind == "N":
                row.crack_kind = "U"
                row.crack = crack_unordered(row.lock, self.true_lock)
                return f"Crack on round {digit} is now unordered.", digit
            row.crack_kind = "O"
            row.crack = crack_ordered(row.lock, self.true_lock)
            return f"Crack on round {digit} is now ordered.", digit

        raise Crash(f"unhandled bonus effect {effect}")

    def bonus_effect(self, effect: str, digit: str | None,
                     guess_no: int) -> tuple[str, str | None]:
        """Full bonus pipeline: validate, apply, then remember for Replay.

        Replay delegates both the digit validation and the effect itself to the
        most recently played non-Replay, non-None bonus effect.
        """
        if effect == "R":
            if self.last_bonus is None:
                self.validate_digit("N", digit, guess_no - 1)
                # Section 9.3.7: the feedback is always "Replay: <Effect>",
                # including when <Effect> is the none-bonus feedback.
                return f"Replay: {MSG_NO_BONUS}", None
            prior_effect, prior_digit = self.last_bonus
            self.validate_digit(prior_effect, digit, guess_no - 1)
            used = digit if digit is not None else prior_digit
            inner, _ = self.apply_bonus(prior_effect, used, guess_no)
            return f"Replay: {inner}", used

        self.validate_digit(effect, digit, guess_no - 1)
        if effect not in ("N", "R"):
            self.last_bonus = (effect, digit)
        return self.apply_bonus(effect, digit, guess_no)

    def full_reveal(self, row: GuessRow) -> str:
        return "".join(
            self.true_cipher[i] if self.true_cipher[i] == row.cipher[i] else HALF
            for i in range(6)
        )

    # -- main loop -----------------------------------------------------------

    def play(self, lines: list[str]) -> None:
        while True:
            if self.guesses_remaining <= 0:
                raise Terminate(MSG_LOSS)
            guess_no = len(self.rows) + 1
            self.emit(title_bar(guess_no, self.guesses_remaining))
            if self.agentic:
                self.emit(hand_box(self.deck.hand))
                self.emit(PROMPT_AGENTIC_GUESS)
            else:
                self.emit(PROMPT_VANILLA_GUESS)

            if self.ai_type != 0:
                line = self.ai_move(guess_no)
                self.emit(line + "\n")
            else:
                if not lines:
                    # Input exhausted mid-game. The reference transcripts simply
                    # stop after the prompt they had already printed, so end the
                    # transcript here rather than reading past the end.
                    return
                line = lines.pop(0)

            passcode, cipher, card, played, digit = self.parse_guess(line)
            lock = lock_of(cipher, passcode)
            effect_code = card.code
            crack = crack_with(lock, self.true_lock, card.crack)
            reveal = reveal_with(cipher, self.true_cipher, card.reveal)

            if self.agentic:
                if played is None:
                    bonus, used = self.bonus_effect("N", None, guess_no)
                else:
                    bonus, used = self.bonus_effect(played.bonus, digit, guess_no)
                    # A Replay card performs the deck action of the effect it
                    # replays, not just its feedback, so Replay-of-Toss has to
                    # discard and redraw exactly as Toss does.
                    effect = played.bonus
                    if effect == "R":
                        effect = self.last_bonus[0] if self.last_bonus else "N"
                    if effect == "T":
                        self.deck.toss(played)
                    else:
                        self.deck.play(played)
            else:
                bonus, used = MSG_NO_BONUS, None

            row = GuessRow(passcode, cipher, card, used, lock, crack, reveal,
                            bonus, effect_code)
            self.rows.append(row)

            won = passcode == self.true_passcode and cipher == self.true_cipher
            self.render_table()
            self.guesses_remaining -= 1

            if self.ai_type != 0:
                self.ai.observe(lock, crack, reveal, card, used, bonus)

            if won:
                raise Terminate(MSG_WIN)
            if self.ai_type == 1 and not won and reveal == self.true_cipher:
                # Only ai_type 1 resigns: section 10.1 states the rule
                # cumulatively, but the public cases take a full reveal on an
                # early guess and keep playing.
                self.ai_resign_next = True

    def render_table(self) -> None:
        rows = [r.display(self.agentic, i + 1) for i, r in enumerate(self.rows)]
        self.emit(table(self.agentic, rows))


# --- AI: shared machinery ----------------------------------------------------


def all_permutations(digits: str) -> list[str]:
    """Every ordering of ``digits``, lexicographically sorted."""
    from itertools import permutations

    return sorted("".join(p) for p in permutations(digits))


def all_lockcodes() -> list[str]:
    """Every 4-digit code over 1-6, repeats allowed: 6**4 = 1296.

    Section 10.2 step 1 is explicit that both S and G hold 1296 lockcodes, so
    these are digit strings, not permutations -- unlike ciphers.
    """
    from itertools import product

    return ["".join(p) for p in product("123456", repeat=4)]


class CipherPool:
    """The pool of guessable ciphers under the four constraints of 10.1."""

    def __init__(self, pool: list[str] | None = None) -> None:
        self.pool = list(pool) if pool is not None else all_permutations("123456")
        self.apply_constraints()

    def apply_constraints(self) -> None:
        """Iterate constraints 3 and 4 until the pool stops shrinking.

        Constraint 1 and 2 are applied by filtering on reveals; 3 and 4 are
        these forced-deductions. Each can break the others, so they run to a
        fixed point.

        The two deductions are collected into one ``forced`` map and applied
        together as equalities, then the pool is refiltered. Both passes read
        the *same* snapshot of the per-position possibilities, so a digit that
        becomes uniquely placed in one pass is not immediately removed from the
        other positions before the second pass looks for it.
        """
        while True:
            size_before = len(self.pool)
            possible = self.allowed_digits()

            forced: dict[int, str] = {}
            for i in range(6):
                if len(possible[i]) == 1:
                    forced[i] = next(iter(possible[i]))
            for digit in "123456":
                spots = [i for i in range(6) if digit in possible[i]]
                if len(spots) == 1:
                    forced[spots[0]] = digit

            self.pool = [
                c for c in self.pool
                if all(c[pos] == digit for pos, digit in forced.items())
            ]
            if len(self.pool) == size_before:
                return

    def allowed_digits(self) -> list[set[str]]:
        return [{c[i] for c in self.pool} for i in range(6)]

    def filter_reveal(self, guess_cipher: str, reveal: str) -> None:
        """Constraint 1 (revealed digits stay) and 2 (dashes exclude).

        A hidden reveal constrains nothing, so the pool is left untouched.
        """
        if reveal == HIDDEN_REVEAL:
            return
        self.pool = [
            c for c in self.pool
            if all((c[i] == r) if r != HALF else (c[i] != guess_cipher[i])
                   for i, r in enumerate(reveal))
        ]
        self.apply_constraints()

    def force_position(self, index: int, digit: str) -> None:
        """A Map bonus pins one position, then the four constraints re-run."""
        self.pool = [c for c in self.pool if c[index] == digit]
        self.apply_constraints()

    def smallest(self) -> str:
        return min(self.pool)

    def unknown_mappings(self) -> int:
        """Positions with more than one digit still possible."""
        return sum(1 for s in self.allowed_digits() if len(s) > 1)

    def map_score(self) -> int:
        """Largest candidate set; ties broken by smallest position."""
        counts = [len(s) for s in self.allowed_digits()]
        best = max(counts)
        return best, counts.index(best)


class LockPool:
    """Knuth's Minimax pools for the lockcode guess strategy (section 10.2)."""

    def __init__(self, ordered: bool = False) -> None:
        self.ordered = ordered
        self.S = all_lockcodes()
        self.G = list(self.S)
        self.last_bonus_count: dict[str, int] = {}
        self.solved = False

    def filter(self, guess: str, true_crack: str, code: str | None = None) -> None:
        """Step 4: keep candidates whose crack matches the true-crack."""
        kind = code if code is not None else self.code()
        self.S = [c for c in self.S if crack_with(guess, c, kind) == true_crack]
        self.G = [c for c in self.G if c != guess]

    def code(self) -> str:
        return "O" if self.ordered else "U"

    def score(self, code: str, ordered: bool) -> int:
        """The spec's recommended ``score(code, ordered)`` helper (10.2 step 5)."""
        return self.worst_bucket(code, "O" if ordered else "U")

    def worst_bucket(self, code: str, kind: str) -> int:
        buckets: dict[str, int] = {}
        for candidate in self.S:
            key = crack_with(code, candidate, kind)
            buckets[key] = buckets.get(key, 0) + 1
        return max(buckets.values())

    def best_guess(self) -> str:
        """Step 5: minimise the worst-case bucket size over G."""
        if len(self.S) == 1:
            return self.S[0]
        scored: list[tuple[int, str, bool]] = [
            (self.score(option, self.ordered), option, option in self.S)
            for option in self.G
        ]

        lowest = min(s[0] for s in scored)
        finalists = [s for s in scored if s[0] == lowest]
        in_s = [s for s in finalists if s[2]]
        if in_s:
            finalists = in_s
        return min(finalists, key=lambda s: s[1])[1]

    def apply_count(self, digit: str, count: int) -> None:
        """Section 10.2.1: Count narrows S to codes with that digit count."""
        self.S = [c for c in self.S if c.count(digit) == count]
        self.last_bonus_count[digit] = count

    @property
    def known(self) -> bool:
        """Whether the Hacker can name the true-lockcode.

        Either a 4-full-dot crack confirmed it outright, or the pool narrowed to
        a single candidate. The 4-full-dot case skips the S filter in 10.2 step 3,
        so the flag and the pool size are both needed.
        """
        return self.solved or len(self.S) <= 1

    def count_digit(self) -> tuple[str, int]:
        """Agent digit selection for Count, section 10.2.1."""
        best_digit = ""
        best_score = -1
        for digit in "123456":
            if digit in self.last_bonus_count:
                continue
            buckets = [0] * 5
            for candidate in self.S:
                buckets[candidate.count(digit)] += 1
            score = max(buckets)
            if best_digit == "" or score < best_score:
                best_digit, best_score = digit, score
        if best_digit == "":
            return "1", -1
        return best_digit, best_score


# --- AI: the two vanilla strategies -----------------------------------------


class VanillaAI:
    """Sections 10.1 and 10.2: cipher guess, then Knuth's minimax."""

    def __init__(self, true_passcode: str, true_cipher: str,
                 use_lock_strategy: bool = True) -> None:
        self.true_passcode = true_passcode
        self.true_cipher = true_cipher
        self.true_lock = lock_of(true_cipher, true_passcode)
        self.ciphers = CipherPool()
        self.locks = LockPool()
        # ai_type 1 plays 1111 every round and never consults the lock pool.
        self.use_lock_strategy = use_lock_strategy
        self.pending_lock = "1122" if use_lock_strategy else "1111"
        self.first = True
        self.last_cipher = ""

    def next_move(self) -> str:
        cipher = self.ciphers.smallest()
        self.last_cipher = cipher
        if not self.use_lock_strategy:
            # ai_type 1 always plays 1111, so the guess-lockcode is simply the
            # guess-cipher's digit-1 position repeated.
            self.first = False
            return f"1111 {cipher}"
        passcode = self.passcode_for(self.pending_lock, cipher)
        self.first = False
        return f"{passcode} {cipher}"

    def passcode_for(self, lock: str, cipher: str) -> str:
        """Decrypt a guess-lockcode back to a guess-passcode."""
        return "".join(str(cipher.index(d) + 1) for d in lock)

    def observe(self, guess_lock: str, true_crack: str, reveal: str,
                card: "AgentCard | None" = None, digit: str | None = None,
                bonus: str = "") -> None:
        self.ciphers.filter_reveal(self.last_cipher, reveal)
        if not self.use_lock_strategy:
            return
        if true_crack == NONE_CRACK:
            self.pending_lock = self.locks.best_guess()
            return
        if true_crack == FULL * 4:
            self.locks.solved = True
            self.pending_lock = guess_lock
            return
        self.locks.filter(guess_lock, true_crack)
        self.pending_lock = self.locks.best_guess()



def _floor_five(score: int, total: int) -> int:
    """floor(5 * (1 - score / total)) for section 10.3.4 bonus values.

    Evaluated as exact integer arithmetic so the result cannot drift with
    floating-point rounding.
    """
    return 5 * (total - score) // total


# --- Game entry point --------------------------------------------------------


def validate_args(args: list[str]) -> tuple[int, int]:
    """Section 7.1. Returns (game_type, ai_type) or raises Terminate.

    Priority: argument count, then game_type, then ai_type, then the
    game_type 0 / ai_type 3 incompatibility.
    """
    if len(args) < 2:
        raise Terminate(MSG_FEW_ARGS)
    if len(args) > 2:
        raise Terminate(MSG_MANY_ARGS)
    if args[0] not in ("0", "1"):
        raise Terminate(MSG_GAME_TYPE)
    if args[1] not in ("0", "1", "2", "3"):
        raise Terminate(MSG_AI_TYPE)
    game_type, ai_type = int(args[0]), int(args[1])
    if game_type == 0 and ai_type == 3:
        raise Terminate(MSG_AI3_VANILLA)
    return game_type, ai_type


def run(text: str, game_type: int, ai_type: int) -> str:
    """Return the exact stdout for an input file's contents.

    Raises Terminate's message is caught and returned; a Crash propagates to
    the generator, which records it in AMBIGUITIES.md instead of emitting a test.
    """
    out: list[str] = []
    game = Game(out, game_type, ai_type)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    try:
        game.setup(lines)
        if ai_type != 0:
            game.attach_ai()
        game.play(lines)
    except Terminate as stop:
        out.append(stop.message + "\n")
    return "".join(out)


def run_args(args: list[str], text: str) -> str:
    """Validate ``args`` then run. Used by the verifier and the generator."""
    try:
        game_type, ai_type = validate_args(args)
    except Terminate as stop:
        return stop.message + "\n"
    return run(text, game_type, ai_type)


_COUNT_FEEDBACK = re.compile(r"(?:Replay: )?(\d) (appears (\d) times|maps to (\d))\.")



class AgenticAI(VanillaAI):
    """Section 10.3: cipher strategy, minimax lock strategy, card selection.

    The AI reads its own history straight off ``game.rows``, which is exactly
    what a player would see, so no information is used that the feedback table
    does not already show.
    """

    def __init__(self, game: Game, use_lock_strategy: bool = True) -> None:
        super().__init__(game.true_passcode, game.true_cipher,
                         use_lock_strategy=use_lock_strategy)
        self.game = game
        self.last_bonus: tuple[str, str | None] | None = None

    # -- observation ---------------------------------------------------------

    def observe(self, guess_lock: str, true_crack: str, reveal: str,
                card: AgentCard | None = None, digit: str | None = None,
                bonus: str = "") -> None:
        """Fold one completed round into both pools and the Replay memory."""
        self.ciphers.filter_reveal(self.last_cipher, reveal)

        if card is not None and card.bonus not in ("N", "R"):
            self.last_bonus = (card.bonus, digit)
        if bonus.startswith("Replay: ") and self.last_bonus is None:
            self.last_bonus = None

        # Bonus effects the AI just triggered may reveal more information.
        if card is not None and card.bonus != "R":
            self.apply_bonus_pool_update(card.bonus, digit, bonus)

        # Section 10.3: a Replay performs the deck action of the effect it
        # repeats, so it must apply the same pool update as that effect. This
        # was missing: only the feedback *text* was replayed, so a replayed
        # Hindsight never narrowed the cipher pool and the AI happily re-guessed
        # a cipher the replay had just ruled out.
        #
        # The replayed effect lives on the Game (Game.bonus_effect is what
        # remembers it), so read it from there rather than from a second copy
        # kept on the AI, which would never be written.
        if card is not None and card.bonus == "R" and self.game.last_bonus is not None:
            prior_effect, prior_digit = self.game.last_bonus
            rep_digit = digit if digit is not None else prior_digit
            self.apply_bonus_pool_update(prior_effect, rep_digit, bonus)

        # Lock pool, section 10.2 step 3. The minimax of step 5 is deferred to
        # next_move, because the ``ordered`` flag it scores with is the crack
        # effect of the card that is about to be played, which is not known yet.
        if true_crack == NONE_CRACK:
            self.refilter_lock_pool()
            return
        if true_crack == FULL * 4:
            self.locks.solved = True
            self.pending_lock = guess_lock
            self.refilter_lock_pool()
            return
        # Step 3: remove the guess from G, then step 4 constrains S.
        self.locks.G = [c for c in self.locks.G if c != guess_lock]
        self.refilter_lock_pool()

    def apply_bonus_pool_update(self, effect: str, digit: str | None,
                                bonus: str) -> None:
        """Fold one bonus effect's information into the pools.

        Shared by a directly-played effect and by a Replay of it, so both take
        the identical pool update and only the feedback text differs.
        """
        if digit is None:
            return
        if effect == "M":
            self.ciphers.force_position(int(digit) - 1, self.mapped_digit(bonus))
        elif effect == "H":
            row = self.game.rows[int(digit) - 1]
            self.ciphers.filter_reveal(row.cipher, row.reveal)
        elif effect == "C":
            self.locks.apply_count(digit, self.counted_amount(bonus))

    def refilter_lock_pool(self) -> None:
        """Rebuild S from every crack currently visible in the feedback table.

        Section 10.2 step 4 constrains S by each guess's crack, but a Promote card
        can upgrade a row that was already played: none becomes unordered, or
        unordered becomes ordered. That turns a row which carried no information
        into a real constraint, so S is rebuilt from the table as it now stands
        rather than accumulated one guess at a time. Rows whose crack effect is
        none still constrain nothing and are skipped.
        """
        pool = all_lockcodes()
        for row in self.game.rows:
            if row.crack_kind in ("U", "O"):
                pool = [c for c in pool
                        if crack_with(row.lock, c, row.crack_kind) == row.crack]
        # Count narrows S without leaving any crack in the table, so it has to be
        # re-applied after the rebuild or the rebuild silently discards it.
        for digit, count in self.locks.last_bonus_count.items():
            pool = [c for c in pool if c.count(digit) == count]
        self.locks.S = pool

    @staticmethod
    def mapped_digit(bonus: str) -> str:
        """Read "1 maps to 6." back out of the bonus feedback."""
        match = _COUNT_FEEDBACK.match(bonus)
        return match.group(4) if match.group(4) is not None else match.group(1)

    @staticmethod
    def counted_amount(bonus: str) -> int:
        """Read "1 appears 2 times." back out of the Count-style feedback."""
        return int(_COUNT_FEEDBACK.match(bonus).group(3))

    # -- agent digits, section 10.3.1 ---------------------------------------

    def promotable_rounds(self) -> list[int]:
        return [i + 1 for i, r in enumerate(self.game.rows)
                if r.crack_kind in ("N", "U")]

    def hidden_rounds(self) -> list[int]:
        return [i + 1 for i, r in enumerate(self.game.rows)
                if r.reveal == HIDDEN_REVEAL]

    def hindsight_score(self, guess_no: int) -> int:
        """Section 10.3.1: digits still possible, summed over still-possible cells."""
        allowed = self.ciphers.allowed_digits()
        cipher = self.game.rows[guess_no - 1].cipher
        total = 0
        for i, digit in enumerate(cipher):
            if digit in allowed[i]:
                total += len(allowed[i])
        return total

    def promote_score(self, guess_no: int) -> int:
        """Section 10.3.1: minimax score of a promotable guess-lockcode."""
        row = self.game.rows[guess_no - 1]
        return self.locks.score(row.lock, ordered=row.crack_kind == "U")

    def best_hindsight_digit(self) -> tuple[int, int]:
        """Return (guess number, hindsight_score); -1 means "not available"."""
        rounds = self.hidden_rounds()
        if not rounds:
            return -1, -1
        scores = [(no, self.hindsight_score(no)) for no in rounds]
        top = max(score for _no, score in scores)
        return min(no for no, score in scores if score == top), top

    def best_promote_digit(self) -> tuple[int, int]:
        rounds = self.promotable_rounds()
        if not rounds:
            return -1, -1
        scores = [(no, self.promote_score(no)) for no in rounds]
        low = min(score for _no, score in scores)
        return min(no for no, score in scores if score == low), low

    def digit_for(self, effect: str) -> str | None:
        """The agent digit for an effect, or None when it needs none / has none."""
        if effect == "C":
            return self.locks.count_digit()[0]
        if effect == "M":
            return str(self.ciphers.map_score()[1] + 1)
        if effect == "H":
            guess_no, _score = self.best_hindsight_digit()
            # 10.3.1 selects digit 0 when there is nothing to expose. Validation
            # of that digit is skipped, so the game just reports no hidden
            # reveals and moves on.
            return "0" if guess_no < 0 else str(guess_no)
        if effect == "P":
            guess_no, _score = self.best_promote_digit()
            return "0" if guess_no < 0 else str(guess_no)
        if effect == "R":
            if self.last_bonus is None:
                return None
            return self.digit_for(self.last_bonus[0])
        return None

    # -- bonus values, section 10.3.4 ---------------------------------------

    def extend_value(self, remaining: int) -> int:
        if remaining == 1:
            return 7
        if remaining <= 3:
            return 4
        if remaining <= 6:
            return 2
        return 1

    def bonus_value(self, effect: str, first: bool) -> int:
        remaining = self.game.guesses_remaining
        if effect == "E":
            return self.extend_value(remaining)
        if effect == "T":
            return 0
        if effect == "N":
            return -1
        if effect == "R":
            # Replay copies the value of the effect it repeats, and is worth -1
            # only when there is nothing to replay. A replayed effect that needs
            # no agent digit of its own (Extend, Toss) is still worth its own
            # value; demanding a digit here wrongly scored every such Replay as
            # -1 and made the AI prefer a worthless card over it.
            if self.last_bonus is None:
                return -1
            return self.bonus_value(self.last_bonus[0], first)
        if effect == "C":
            if first:
                return 5
            _digit, count_score = self.locks.count_digit()
            if count_score < 0 or self.locks.known:
                return -1
            return _floor_five(count_score, len(self.locks.S))
        if effect == "M":
            map_score = self.ciphers.map_score()[0]
            return -1 if map_score == 1 else map_score - 1
        if effect == "H":
            _guess_no, score = self.best_hindsight_digit()
            if score < 0 or self.ciphers.unknown_mappings() == 0:
                return -1
            return _floor_five(score, 36)
        if effect == "P":
            _guess_no, score = self.best_promote_digit()
            if score < 0 or self.locks.known:
                return -1
            return _floor_five(score, len(self.locks.S))
        raise Crash(f"unhandled bonus effect {effect}")

    # -- the move ------------------------------------------------------------

    def next_move(self) -> str:
        cipher = self.ciphers.smallest()
        self.last_cipher = cipher
        first = not self.game.rows

        pool_size = len(self.locks.S)
        solved = self.locks.known
        unknown = self.ciphers.unknown_mappings()

        best_value = -1
        best_card: AgentCard | None = None
        best_digit: str | None = None
        for card in self.game.deck.hand:
            digit = self.digit_for(card.bonus)
            value = (crack_score(card.crack, pool_size, solved)
                     + reveal_value(card.reveal, unknown)
                     + self.bonus_value(card.bonus, first))
            if best_card is None or value > best_value:
                best_value, best_card, best_digit = value, card, digit
            elif value == best_value and card.name < best_card.name:
                best_card, best_digit = card, digit

        # The card actually played, which is not ``best_card`` when every card
        # scores negative and section 10.3 says to play none.
        played = best_card if best_card is not None and best_value >= 0 else None

        if first:
            # Section 10.2 step 2: the first guess-lockcode of the lockcode
            # strategy is always 1122. The cipher strategy plays 1111 from the
            # very first guess, so it must not be overridden here.
            self.pending_lock = "1122" if self.use_lock_strategy else "1111"
        elif not self.locks.solved and self.use_lock_strategy:
            # Section 10.2 step 5. The crack effect that this round's card applies
            # is what decides whether the minimax scores with ordered or unordered
            # cracks. Scoring an ordered-crack card as unordered silently picks the
            # wrong guess-lockcode.
            self.locks.ordered = played is not None and played.crack == "O"
            self.pending_lock = self.locks.best_guess()

        passcode = self.passcode_for(self.pending_lock, cipher)

        if played is None:
            return f"{passcode} {cipher}"
        if best_digit is None:
            return f"{passcode} {cipher} {played.name}"
        return f"{passcode} {cipher} {played.name} {best_digit}"
