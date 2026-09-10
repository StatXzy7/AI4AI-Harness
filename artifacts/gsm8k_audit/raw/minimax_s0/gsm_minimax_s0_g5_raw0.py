"""Self-consistency harness: samples multiple chain-of-thought solutions and selects the majority final answer."""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ..harness_base import MathHarness


SYSTEM_PROMPT = (
    "You are an expert mathematician solving competition word problems. "
    "Think step by step carefully and show all work. "
    "On the very last line of your response, output the final answer in the exact form: "
    "#### <answer> "
    "where <answer> may be an integer, a fraction like 3/4 or \\frac{3}{4}, a LaTeX expression, "
    "an interval like (3,4], or a tuple like (2,5). Do not write anything after that line."
)


def _normalize_answer(ans: str) -> str:
    """Normalize an extracted final answer so that equivalent strings collide."""
    if ans is None:
        return ""
    s = ans.strip()
    # Strip a leading "####" in case the model repeated the marker.
    s = re.sub(r"^#+\s*", "", s)
    s = s.strip().rstrip(".")
    s = s.replace(" ", "")
    s = s.replace("\\,", "")
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    # Normalize bare fractions: 3/4 <-> \frac{3}{4}
    m = re.fullmatch(r"(-?\d+)/(-?\d+)", s)
    if m:
        s = "\\frac{" + m.group(1) + "}{" + m.group(2) + "}"
    # Normalize signs.
    if s.startswith("+"):
        s = s[1:]
    # Lower-case for case-insensitive tuple/interval matching.
    s = s.lower()
    return s


_FINAL_RE = re.compile(r"####\s*(.+?)\s*$", re.MULTILINE | re.DOTALL)


def _extract_final_answer(text: str) -> Optional[str]:
    """Pull the answer that follows the last '####' marker; fall back to the last numeric-ish token."""
    if not text:
        return None
    matches = _FINAL_RE.findall(text)
    candidate: Optional[str] = None
    if matches:
        candidate = matches[-1]
    else:
        # Fallback: last line that looks like an answer.
        for line in reversed([ln.strip() for ln in text.splitlines() if ln.strip()]):
            if re.search(r"[0-9a-zA-Z\\\}\)]", line):
                candidate = line
                break
    if candidate is None:
        return None
    # Strip any trailing commentary after the answer token on the same line.
    candidate = candidate.splitlines()[0].strip()
    return candidate


def _majority_answer(answers):
    """Return the most common normalized answer, preferring the most 'compact' original form."""
    norm_to_originals: dict[str, list[str]] = {}
    for a in answers:
        n = _normalize_answer(a)
        if not n:
            continue
        norm_to_originals.setdefault(n, []).append(a)
    if not norm_to_originals:
        return ""
    # Pick the bucket with the most votes.
    best_norm, _ = max(norm_to_originals.items(), key=lambda kv: (len(kv[1]), -len(kv[0])))
    originals = norm_to_originals[best_norm]
    # Among the originals in the winning bucket, choose the shortest (most compact) string.
    chosen = min(originals, key=lambda s: (len(s), s.count(" ")))
    return chosen


class GsmGsmMinimaxS0G5(MathHarness):
    """Multi-sample self-consistency: generate k chains, pick the majority final answer."""

    # Sampling budget for the consensus vote.
    NUM_SAMPLES = 7
    # Diversity: a modest temperature so multiple chains disagree when the model is uncertain,
    # but stay accurate when it is confident.
    TEMPERATURE = 0.6

    def solve(self, question: str) -> str:
        prompt = (
            "Solve the following competition-style word problem. "
            "Show clear step-by-step reasoning. "
            "On the last line, output the final answer in the form: #### <answer>\n\n"
            f"Problem:\n{question}"
        )

        # Sample several independent solutions in a single batched call.
        try:
            responses = self.llm(
                prompt,
                system=SYSTEM_PROMPT,
                temperature=self.TEMPERATURE,
                n=self.NUM_SAMPLES,
            )
        except TypeError:
            # Fallback for harnesses whose llm() does not accept `n`.
            responses = [
                self.llm(prompt, system=SYSTEM_PROMPT, temperature=self.TEMPERATURE)
                for _ in range(self.NUM_SAMPLES)
            ]

        answers: list[str] = []
        for resp in responses:
            ans = _extract_final_answer(resp if isinstance(resp, str) else str(resp))
            if ans is not None:
                answers.append(ans)

        if not answers:
            # Nothing parseable came back; return an empty string rather than guessing.
            return ""

        # If every sampled answer agrees, we are done immediately (no need for voting logic).
        if len({_normalize_answer(a) for a in answers}) == 1:
            return answers[0]

        # Otherwise, break ties with a deterministic 0-temperature rerun.
        try:
            tie_breaker = self.llm(
                prompt,
                system=SYSTEM_PROMPT,
                temperature=0.0,
                n=1,
            )
        except TypeError:
            tie_breaker = self.llm(prompt, system=SYSTEM_PROMPT, temperature=0.0)

        tb_ans = _extract_final_answer(
            tie_breaker if isinstance(tie_breaker, str) else str(tie_breaker)
        )
        if tb_ans is not None:
            answers.append(tb_ans)

        return _majority_answer(answers)