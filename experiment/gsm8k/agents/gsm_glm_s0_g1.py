"""Self-consistency harness for GSM8K: a greedy anchor chain plus temperature-sampled chains are aggregated by a marker-weighted majority vote over extracted final answers, with the greedy answer breaking ties."""

import re
from collections import Counter
from fractions import Fraction

from ..harness_base import MathHarness

# A numeric token: optional sign/currency, digits with thousands commas or a
# decimal part, optionally a trailing "3 / 4"-style fraction.
_TOKEN = r"-?\$?\d[\d,]*(?:\.\d+)?(?:[ \t]*/[ \t]*\d+)?"
_MARKER_RE = re.compile(r"####\s*" + _TOKEN)
_ANSWER_RE = re.compile(
    r"(?:final\s+)?answer(?:\s+is|\s*[:=])\s*:?\s*" + _TOKEN, re.IGNORECASE
)
_NUM_RE = re.compile(_TOKEN)

# Chains that emit an explicit final-answer marker ("#### n" / "the answer is
# n") are trusted more than chains where we had to grab the last number.
_MARKER_WEIGHT = 2.0
_FALLBACK_WEIGHT = 1.0


def _canon(token):
    """Normalize a numeric token to a canonical answer string, or None."""
    if not token:
        return None
    t = token.strip().replace("$", "").replace("%", "").replace(",", "").strip()
    t = t.rstrip(".")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?|-?\d+/\d+", t):
        return None
    try:
        value = float(Fraction(t)) if "/" in t else float(t)
    except (ValueError, ZeroDivisionError):
        return None
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(value)


def _extract(text):
    """Return (canonical_answer, confidence_weight) from a solver reply."""
    if not text:
        return None, 0.0
    # Prefer the *last* explicit marker in the reply (GSM8K style puts the
    # final answer on the final line).
    for regex in (_MARKER_RE, _ANSWER_RE):
        last = None
        for match in regex.finditer(text):
            last = match
        if last is not None:
            answer = _canon(last.group(0))
            if answer is not None:
                return answer, _MARKER_WEIGHT
    # Fallback: the last number appearing anywhere in the reply.
    numbers = _NUM_RE.findall(text)
    if numbers:
        answer = _canon(numbers[-1])
        if answer is not None:
            return answer, _FALLBACK_WEIGHT
    return None, 0.0


class GsmGsmGlmS0G1(MathHarness):
    # Mechanism (control flow, not just prompt length):
    #   A) one greedy (temperature=0) chain acts as an anchor answer;
    #   B) N sampled chains at nonzero temperature provide diversity;
    #   C) answers are extracted and combined via weighted majority vote
    #      (explicit "#### n" markers count double; the greedy answer gets a
    #      bonus vote and wins any tie), replacing single-call argmax decoding.
    N_SAMPLES = 8
    TEMPERATURE = 0.7
    GREEDY_WEIGHT = 2.0

    PROMPT = (
        "Solve this grade-school math word problem step by step. Reason "
        "carefully about the quantities, then end your reply with the final "
        "numeric answer on its own last line in the exact format:\n"
        "#### <number>\n\n"
        "Problem: {q}\n\n"
        "Solution:"
    )

    def _call_one(self, prompt, temperature):
        """Single solver call, tolerating backends that return lists."""
        out = self.llm(prompt, system="", temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return "" if out is None else str(out)

    def _sample(self, prompt, k, temperature):
        """Get k sampled chains: try one batched n=k call, else k single calls."""
        texts = []
        try:
            batch = self.llm(prompt, system="", temperature=temperature, n=k)
            if isinstance(batch, (list, tuple)):
                texts = [t for t in batch if isinstance(t, str)]
            elif isinstance(batch, str) and batch:
                texts = [batch]  # backend ignored n=; top up below
        except Exception:
            texts = []
        attempts = 0
        while len(texts) < k and attempts < 2 * k + 2:
            attempts += 1
            try:
                texts.append(self._call_one(prompt, temperature))
            except Exception:
                break
        return texts[:k]

    def solve(self, question: str) -> str:
        prompt = self.PROMPT.format(q=question.strip())

        # Stage A: greedy anchor.
        greedy_answer = None
        try:
            greedy_answer, _ = _extract(self._call_one(prompt, 0.0))
        except Exception:
            greedy_answer = None

        # Stage B: self-consistency sampling + weighted majority vote.
        votes = Counter()
        first_seen = {}
        for text in self._sample(prompt, self.N_SAMPLES, self.TEMPERATURE):
            answer, weight = _extract(text)
            if answer is None:
                continue
            if answer not in first_seen:
                first_seen[answer] = len(first_seen)
            votes[answer] += weight

        # The greedy answer casts a bonus (tie-breaking) vote.
        if greedy_answer is not None:
            if greedy_answer not in first_seen:
                first_seen[greedy_answer] = len(first_seen)
            votes[greedy_answer] += self.GREEDY_WEIGHT

        if not votes:
            return greedy_answer if greedy_answer is not None else ""

        top = max(votes.values())
        tied = [a for a, w in votes.items() if w == top]
        if greedy_answer is not None and greedy_answer in tied:
            return greedy_answer
        return min(tied, key=lambda a: first_seen[a])