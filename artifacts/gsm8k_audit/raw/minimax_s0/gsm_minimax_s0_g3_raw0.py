"""
Self-consistency style ensemble that samples k completions with the frozen solver
at a non-zero temperature, extracts numeric answers, and returns the majority vote
(breaking ties by lowest variance / shortest reasoning trace as a heuristic tie-break).
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from typing import List, Optional

from ..harness_base import MathHarness


_NUM_RE = re.compile(
    r"(?ix)
    (?:
        \#\#\#\#\s*(?P<hash>-?\d[\d,\.\s]*)
        |
        the\s+answer\s+is\s*[:\-]?\s*(?P<ans>-?\d[\d,\.\s]*)
        |
        answer\s*[:\-=]\s*(?P<eq>-?\d[\d,\.\s]*)
        |
        \\boxed\{\s*(?P<box>-?\d[\d,\.\s]*)\s*\}
        |
        =\s*(?P<eq2>-?\d[\d,\.\s]*)\s*\.?\s*$
    )
    "
)


def _strip_to_number(token: str) -> Optional[float]:
    if token is None:
        return None
    s = token.strip().rstrip(".")
    s = s.replace(",", "").replace(" ", "")
    if s.startswith("$"):
        s = s[1:]
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        # try to peel trailing units / words
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if m:
            try:
                return float(m.group(0))
            except Exception:
                return None
        return None


def _extract_answer(text: str) -> Optional[float]:
    """Pull the most plausible final number from a solver completion."""
    if not text:
        return None
    # Prefer the explicit "#### N" pattern if present.
    for line in text.splitlines()[::-1]:
        line_stripped = line.strip()
        if line_stripped.startswith("####"):
            tail = line_stripped[4:].strip()
            m = re.search(r"-?\d+(?:\.\d+)?", tail.replace(",", ""))
            if m:
                try:
                    return float(m.group(0))
                except Exception:
                    pass
    # Fall back to a regex sweep, last match wins.
    matches = list(_NUM_RE.finditer(text))
    for m in reversed(matches):
        for grp in ("hash", "ans", "eq", "box", "eq2"):
            v = m.group(grp)
            if v is not None:
                num = _strip_to_number(v)
                if num is not None:
                    return num
    # Last resort: last standalone number in the text.
    nums = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if nums:
        try:
            return float(nums[-1])
        except Exception:
            return None
    return None


def _format_number(x: float) -> str:
    """Render a numeric answer the way GSM8K-style evaluators expect."""
    if x is None:
        return ""
    if abs(x - round(x)) < 1e-9 and abs(x) < 1e15:
        return str(int(round(x)))
    # Trim trailing zeros for non-integers.
    s = ("%.6f" % x).rstrip("0").rstrip(".")
    return s if s else "0"


class GsmGsmMinimaxS0G3(MathHarness):
    """Ensemble solver that majority-votes over multiple frozen-solver samples."""

    # --- knobs (kept as class-level constants so they're easy to override) ---
    N_SAMPLES = 5
    TEMPERATURE = 0.7
    TOP_P = 0.95
    SYSTEM_PROMPT = (
        "You are a careful grade-school math tutor. "
        "Solve the problem step by step and finish with '#### <number>' on its own line."
    )

    # ---- internal helpers --------------------------------------------------

    def _sample(self, question: str, n: int) -> List[str]:
        """Draw n independent completions from the frozen solver."""
        return self.llm(
            question,
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            top_p=self.TOP_P,
            n=n,
        ) or []

    def _greedy(self, question: str) -> str:
        """One greedy (temperature=0) completion for the fallback path."""
        outs = self.llm(
            question,
            system=self.SYSTEM_PROMPT,
            temperature=0.0,
            n=1,
        ) or []
        return outs[0] if outs else ""

    def _vote(self, candidates: List[Optional[float]]) -> Optional[float]:
        """Majority vote over numeric candidates; tie-break by lowest spread."""
        valid = [c for c in candidates if c is not None]
        if not valid:
            return None
        # Bin floats into integer-ish buckets so 42.0 == 42 == 42.00 vote together.
        def _bucket(x: float):
            if abs(x - round(x)) < 1e-6 and abs(x) < 1e12:
                return int(round(x))
            return round(x, 6)

        buckets = Counter(_bucket(v) for v in valid)
        top_count = max(buckets.values())
        winners = [k for k, v in buckets.items() if v == top_count]
        if len(winners) == 1:
            return float(winners[0])
        # Tie-break: pick the bucket whose raw candidates have the smallest variance
        # (most "confident" / consistent reasoning).
        best = None
        best_var = float("inf")
        for w in winners:
            group = [v for v in valid if _bucket(v) == w]
            try:
                var = statistics.pvariance(group) if len(group) > 1 else 0.0
            except Exception:
                var = 0.0
            if var < best_var or (var == best_var and (best is None or w < best)):
                best_var = var
                best = w
        return float(best) if best is not None else float(winners[0])

    # ---- public API -------------------------------------------------------

    def solve(self, question: str) -> str:
        # 1) Sample a small ensemble.
        try:
            samples = self._sample(question, self.N_SAMPLES)
        except TypeError:
            # Backend doesn't accept top_p -> drop it.
            samples = self.llm(
                question,
                system=self.SYSTEM_PROMPT,
                temperature=self.TEMPERATURE,
                n=self.N_SAMPLES,
            ) or []
        except Exception:
            samples = []

        # 2) Always also grab one greedy answer so we have a deterministic anchor.
        greedy_text = self._greedy(question)
        greedy_ans = _extract_answer(greedy_text)

        candidates: List[Optional[float]] = [greedy_ans]
        raw_answers: List[Optional[float]] = []
        for s in samples:
            a = _extract_answer(s)
            raw_answers.append(a)
            candidates.append(a)

        # 3) Majority vote, falling back to greedy if sampling failed.
        voted = self._vote(candidates)
        if voted is None:
            voted = greedy_ans
        if voted is None:
            # Absolute last resort: the last number anywhere in the greedy output.
            nums = re.findall(r"-?\d+(?:\.\d+)?", greedy_text.replace(",", ""))
            if nums:
                try:
                    voted = float(nums[-1])
                except Exception:
                    voted = 0.0
            else:
                voted = 0.0

        return _format_number(voted)