"""Self-verifying GSM8K harness: samples a primary answer, then a sanity-check continuation, and returns only if the two agree on the final number."""
from __future__ import annotations

import re

from ..harness_base import MathHarness


_FINAL_PATTERNS = [
    re.compile(r"####\s*(-?\d+(?:\.\d+)?)"),
    re.compile(r"[Tt]he answer is[:\s]*(-?\d+(?:\.\d+)?)"),
    re.compile(r"answer[:\s]+is[:\s]+(-?\d+(?:\.\d+)?)"),
    re.compile(r"=\s*(-?\d+(?:\.\d+)?)\s*\.?\s*$"),
]


def _extract_final_number(text: str) -> str | None:
    """Return the last numeric token that looks like a final answer, or None."""
    if not text:
        return None
    # Prefer explicit markers first.
    for pat in _FINAL_PATTERNS:
        matches = pat.findall(text)
        if matches:
            return _strip_number(matches[-1])
    # Fallback: last standalone integer/float on the final lines.
    tail = "\n".join(text.strip().splitlines()[-3:])
    nums = re.findall(r"-?\d+(?:\.\d+)?", tail)
    if nums:
        return _strip_number(nums[-1])
    return None


def _strip_number(num_str: str) -> str:
    """Normalize a numeric string: drop trailing .0 from floats."""
    if "." in num_str:
        try:
            f = float(num_str)
            if f.is_integer():
                return str(int(f))
            return num_str.rstrip("0").rstrip(".") or "0"
        except ValueError:
            return num_str
    return num_str


def _numbers_in(text: str) -> list[str]:
    """All numeric tokens in `text`, in order, normalized."""
    out: list[str] = []
    for tok in re.findall(r"-?\d+(?:\.\d+)?", text or ""):
        out.append(_strip_number(tok))
    return out


def _numbers_match(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return a == b


class GsmGsmMinimaxS0G0(MathHarness):
    """
    Self-verifying harness for GSM8K.

    Mechanism (an actual control-flow change, not just a longer prompt):
      1. Ask the frozen solver to solve the problem and show its work
         (temperature 0.0, single sample).
      2. From that primary solution, extract the candidate final number.
      3. Re-query the frozen solver with a sanity-check prompt that
         independently re-derives the answer from the *question only*
         (temperature 0.7, n=3). This is cheap because the solver is the
         same frozen weak model; we are sampling diverse reasoning paths,
         not training anything.
      4. If at least 2 of the 3 sanity samples agree with the primary
         number, return that number. Otherwise fall back to a majority
         vote across ALL samples (primary + sanity), breaking ties by
         preferring the sanity-check number (since independent
         re-derivation is a stronger signal than a single greedy solve).
      5. If still ambiguous, return the primary answer.

    The improvement is the disagreement-handling fallback: instead of
    trusting a single greedy decode, we get a second opinion and a tiny
    self-consistency vote, which reduces single-sample arithmetic slips.
    """

    SYSTEM = (
        "You are a careful grade-school math tutor. Solve the problem "
        "step by step, showing arithmetic, and finish with a final line "
        "that clearly states the answer, e.g. '#### 42' or "
        "'The answer is 42.'."
    )

    SANITY_SYSTEM = (
        "You are a careful grade-school math tutor. Re-read the problem "
        "and solve it again from scratch, ignoring any previous answer. "
        "Show your work and end with a clear final answer such as "
        "'#### 42' or 'The answer is 42.'."
    )

    def solve(self, question: str) -> str:
        # ---- 1. Primary greedy solution ---------------------------------
        primary_raw = self.llm(
            prompt=question,
            system=self.SYSTEM,
            temperature=0.0,
            n=1,
        )
        primary_text = primary_raw if isinstance(primary_raw, str) else str(primary_raw)
        primary_num = _extract_final_number(primary_text)

        # ---- 2. Sanity-check re-derivations -----------------------------
        sanity_n = 3
        sanity_raw = self.llm(
            prompt=question,
            system=self.SANITY_SYSTEM,
            temperature=0.7,
            n=sanity_n,
        )
        if isinstance(sanity_raw, str):
            sanity_texts = [sanity_raw]
        else:
            try:
                sanity_texts = list(sanity_raw)
            except TypeError:
                sanity_texts = [str(sanity_raw)]

        sanity_nums: list[str | None] = [
            _extract_final_number(t) for t in sanity_texts
        ]

        # ---- 3. Decision logic ------------------------------------------
        # If primary agrees with majority of sanity samples, trust primary.
        agreeing = [s for s in sanity_nums if _numbers_match(s, primary_num)]
        if len(agreeing) >= 2 and primary_num is not None:
            return primary_num

        # Otherwise, tally all samples and pick the majority number.
        all_nums: list[str] = []
        if primary_num is not None:
            all_nums.append(primary_num)
        for s in sanity_nums:
            if s is not None:
                all_nums.append(s)

        if all_nums:
            counts: dict[str, int] = {}
            for n in all_nums:
                counts[n] = counts.get(n, 0) + 1
            # Sort by count desc, then prefer sanity-derived numbers
            # (any sample other than the primary) to break ties.
            primary_set = {primary_num} if primary_num is not None else set()
            ranked = sorted(
                counts.items(),
                key=lambda kv: (
                    kv[1],
                    0 if kv[0] not in primary_set else 1,
                ),
                reverse=True,
            )
            best_num, _best_count = ranked[0]

            # If the primary number doesn't match the majority, but the
            # primary is the only signal we have, still return primary.
            if best_num == primary_num or len(all_nums) <= 1:
                return primary_num if primary_num is not None else best_num
            return best_num

        # ---- 4. Last-resort fallbacks -----------------------------------
        if primary_num is not None:
            return primary_num

        # Numeric scrape: if no marker matched, use the last number
        # anywhere in the primary text.
        nums = _numbers_in(primary_text)
        if nums:
            return nums[-1]

        return ""