"""Self-consistency with answer-extraction repair: sample multiple greedy generations, then fall back to a re-prompt that asks for a corrected numeric answer if extraction fails or majority is weak."""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Tuple

from ..harness_base import MathHarness


def _extract_answer(text: str) -> Optional[str]:
    """Extract the final numeric answer from solver output.

    Tries several patterns in priority order:
      1. "#### N" (GSM8K canonical)
      2. "the answer is N" / "answer: N"
      3. last standalone number in the text
    """
    if not text:
        return None

    # 1. GSM8K-style "#### N"
    m = re.search(r"####\s*([-+]?\d+(?:[.,]\d+)?)", text)
    if m:
        return _normalize(m.group(1))

    # 2. "the answer is N" / "answer: N" / "= N" at end
    patterns = [
        r"(?:the\s+)?(?:final\s+)?answer\s+is\s*[:=]?\s*([-+]?\d+(?:[.,]\d+)?)",
        r"answer\s*[:=]\s*([-+]?\d+(?:[.,]\d+)?)",
        r"=\s*([-+]?\d+(?:[.,]\d+)?)\s*\.?\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            return _normalize(m.group(1))

    # 3. last standalone number on its own line or sentence
    nums = re.findall(r"([-+]?\d+(?:[.,]\d+)?)", text)
    if nums:
        return _normalize(nums[-1])

    return None


def _normalize(num_str: str) -> str:
    """Normalize a numeric string: strip commas, drop trailing .0 for ints."""
    s = num_str.replace(",", "").strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        # Keep up to 4 decimal places, trim trailing zeros
        s2 = ("%.4f" % f).rstrip("0").rstrip(".")
        return s2
    except ValueError:
        return s


def _majority_or_none(answers: List[str]) -> Optional[str]:
    """Return the majority answer if it appears in >= half of samples, else None."""
    if not answers:
        return None
    counts = Counter(answers)
    top, n = counts.most_common(1)[0]
    if n >= max(1, len(answers) // 2 + 1):
        return top
    # Soft majority: at least 2 votes and unique count <= half
    if n >= 2 and len(counts) <= len(answers) - n + 1:
        return top
    return None


class GsmGsmMinimaxS0G7(MathHarness):
    """Harness using self-consistency voting with extraction repair.

    Mechanism:
      1. Run the frozen solver once (greedy, T=0).
      2. Extract the numeric answer robustly.
      3. If extraction succeeded AND answer is a clean integer/rational,
         return it (fast path).
      4. Otherwise, sample N additional independent generations (also T=0
         but with n=N) and vote by majority on extracted answers.
      5. If still no consensus, run a targeted re-prompt that asks the
         solver to output ONLY the final number, and extract from that.
    """

    N_SAMPLES = 5  # total solver calls including the first one

    def solve(self, question: str) -> str:
        # ---- Step 1: initial greedy pass ----
        first_reply = self.llm(question, system="", temperature=0.0, n=1)
        first_ans = _extract_answer(first_reply)

        # ---- Step 2: if we got a clean answer, accept it immediately ----
        if first_ans is not None:
            return first_ans

        # ---- Step 3: self-consistency sampling ----
        # Re-sample with temperature 0 but n=N. The harness interface allows
        # n>1 even at T=0; we use it to get multiple independent decodes
        # (the underlying sampler may inject minor variance or we may rely
        # on prompt perturbations below).
        samples_text: List[str] = self.llm(
            question + "\n\nThink step by step, then write '#### <number>' on the last line.",
            system="",
            temperature=0.0,
            n=self.N_SAMPLES,
        )
        if isinstance(samples_text, str):
            samples_text = [samples_text]

        # Prepend the first reply so it counts too
        all_replies = [first_reply] + list(samples_text)
        extracted = [_extract_answer(r) for r in all_replies]
        valid = [a for a in extracted if a is not None]

        majority = _majority_or_none(valid)
        if majority is not None:
            return majority

        # ---- Step 4: targeted repair prompt ----
        # No consensus. Ask the solver explicitly for just the number,
        # grounded in its own previous reasoning when available.
        repair_prompt = (
            "Based on the following solution, output ONLY the final numeric "
            "answer with no explanation. Write it as '#### <number>'.\n\n"
            f"Question:\n{question}\n\n"
            f"Previous solution:\n{first_reply}"
        )
        repair_reply = self.llm(repair_prompt, system="", temperature=0.0, n=1)
        repair_ans = _extract_answer(repair_reply)
        if repair_ans is not None:
            return repair_ans

        # ---- Step 5: last-ditch numeric scrape across all replies ----
        # Pool every number seen anywhere; pick the most frequent.
        pool: List[str] = []
        for r in all_replies + [repair_reply]:
            for n in re.findall(r"([-+]?\d+(?:[.,]\d+)?)", r or ""):
                pool.append(_normalize(n))
        if pool:
            return Counter(pool).most_common(1)[0][0]

        # Absolute fallback: return 0 rather than crash the harness.
        return "0"