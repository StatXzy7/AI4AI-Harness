"""Single greedy generation with self-consistency voting across diverse prompt framings."""
from __future__ import annotations

import re
from collections import Counter
from ..harness_base import MathHarness


_ANSWER_RE = re.compile(r"####\s*(.+?)\s*$", re.MULTILINE)


def _extract_answer(text: str) -> str | None:
    """Return the answer on the last '#### ...' line, or None if absent."""
    matches = _ANSWER_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip().rstrip(".").strip()


def _normalize(ans: str) -> str:
    """Canonicalize an answer string so trivially equivalent forms vote together."""
    if ans is None:
        return ""
    s = ans.strip()
    # strip surrounding delimiters like \( \) or \[ \] or $...$
    if (s.startswith("$") and s.endswith("$")) or (s.startswith(r"\(") and s.endswith(r"\)")) \
            or (s.startswith(r"\[") and s.endswith(r"\]")):
        s = s[2:-2] if s.startswith(r"\(") else s[1:-1]
    # remove latex spacing/approx
    s = s.replace(r"\,", "").replace(r"\;", "").replace(r"\!", "")
    s = s.replace(" ", "").replace("{", "").replace("}", "")
    # fraction slash vs \frac
    s = s.replace("\\frac", "").replace("\\dfrac", "")
    return s.lower()


_SYSTEM = (
    "You are an expert competition-math solver. Solve the problem step by step, "
    "showing clear reasoning. On the FINAL line of your response, output the answer "
    "in the form '#### <answer>' where <answer> is a plain number, a fraction "
    "(like 3/4 or \\frac{3}{4}), a LaTeX expression (like 2\\sqrt{3}), an interval "
    "(like (3,4]), or a tuple (like (2, 5)). Nothing may follow that line."
)

_FRAMINGS = [
    "",
    "Think carefully and show all work.\n\n",
    "First restate the problem, then solve it. Verify your answer before finalizing.\n\n",
    "Use a clean, rigorous approach. Double-check each step.\n\n",
]


class GsmGsmMinimaxS0G2(MathHarness):
    def solve(self, question: str) -> str:
        # Diverse self-consistency: sample N candidates with different framings,
        # then take a majority vote over extracted final answers.
        candidates: list[str] = []
        extracted: list[str] = []
        for extra_preamble in _FRAMINGS:
            prompt = extra_preamble + question.strip()
            try:
                text = self.llm(prompt, system=_SYSTEM, temperature=0.0, n=1)
            except TypeError:
                # harness llm may not accept system kw
                text = self.llm(prompt, temperature=0.0, n=1)
            candidates.append(text)
            ans = _extract_answer(text)
            if ans is not None:
                extracted.append(ans)

        if not extracted:
            # No '####' line was produced; fall back to the first response's
            # last non-empty line as a best effort.
            last = candidates[0].strip().splitlines() if candidates else [""]
            for line in reversed(last):
                if line.strip():
                    return line.strip()
            return ""

        # Majority vote on normalized forms; break ties by first occurrence order.
        norm_to_display: dict[str, str] = {}
        counts: Counter[str] = Counter()
        order: list[str] = []
        for a in extracted:
            n = _normalize(a)
            if not n:
                continue
            if n not in norm_to_display:
                norm_to_display[n] = a
                order.append(n)
            counts[n] += 1

        if not counts:
            return extracted[0]

        top_count = max(counts.values())
        winners = [n for n in order if counts[n] == top_count]
        chosen = winners[0]
        return norm_to_display[chosen]