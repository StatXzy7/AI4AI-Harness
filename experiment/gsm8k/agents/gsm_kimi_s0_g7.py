"""Self-consistency harness: run the frozen solver once greedily plus several times at nonzero temperature, extract each reply's numeric answer, and majority-vote with the greedy answer breaking ties."""

from ..harness_base import MathHarness

import re
from collections import Counter


class GsmGsmKimiS0G7(MathHarness):
    """Self-consistency wrapper around the frozen GSM8K solver.

    A single greedy sample from a weak solver often contains one arithmetic
    slip. Sampling several diverse completions and taking the modal numeric
    answer cancels out such independent errors (Wang et al., self-consistency).
    The greedy run is kept as a privileged vote that wins all ties, so the
    harness never does worse than plain greedy decoding by accident of a
    coin-flip among equally popular alternatives.
    """

    _NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
    _N_SAMPLES = 4          # extra samples beyond the greedy one
    _SAMPLE_TEMP = 0.7      # nonzero to obtain genuinely diverse reasoning paths

    # ---------- answer extraction ----------

    @classmethod
    def _normalize(cls, raw: str):
        """Turn '1,234.0' / '42' into a canonical numeric string."""
        s = raw.replace(",", "").strip().rstrip(".")
        if not s:
            return None
        try:
            f = float(s)
        except ValueError:
            return None
        if f == int(f):
            return str(int(f))
        return ("%f" % f).rstrip("0").rstrip(".")

    @classmethod
    def _extract(cls, text: str):
        """Pull the final numeric answer out of a raw solver reply."""
        if not text:
            return None
        # 1) Canonical GSM8K marker: '#### 42'
        m = re.search(r"####\s*([^\n]+)", text)
        if m:
            nums = cls._NUM_RE.findall(m.group(1))
            if nums:
                return cls._normalize(nums[-1])
        # 2) 'The answer is 42' style phrasing.
        m = re.search(r"answer\s+is[:\s]*\$?([^\n]+)", text, re.IGNORECASE)
        if m:
            nums = cls._NUM_RE.findall(m.group(1))
            if nums:
                return cls._normalize(nums[-1])
        # 3) Fallback: the last number appearing anywhere in the reply.
        nums = cls._NUM_RE.findall(text)
        if nums:
            return cls._normalize(nums[-1])
        return None

    # ---------- solver access ----------

    def _ask(self, question: str, temperature: float) -> str:
        prompt = (
            "Solve the following grade-school math word problem step by step, "
            "showing each arithmetic step. End your reply with a line of the "
            "form '#### <answer>' where <answer> is the final numeric answer "
            "with no units and no thousands separators.\n\n"
            f"Problem: {question}"
        )
        system = (
            "You are a careful grade-school math tutor. "
            "Compute every step explicitly and double-check the arithmetic."
        )
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            return out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    # ---------- main control flow ----------

    def solve(self, question: str) -> str:
        # 1) Greedy baseline (identical to the un-wrapped solver).
        greedy_text = self._ask(question, temperature=0.0)
        greedy_ans = self._extract(greedy_text)

        # 2) Diverse additional reasoning paths for self-consistency.
        votes = []
        if greedy_ans is not None:
            votes.append(greedy_ans)
        for _ in range(self._N_SAMPLES):
            sample_text = self._ask(question, temperature=self._SAMPLE_TEMP)
            ans = self._extract(sample_text)
            if ans is not None:
                votes.append(ans)

        # 3) If every reply was unparseable, degrade gracefully to whatever
        #    the greedy pass produced (even unextracted text's last resort).
        if not votes:
            return greedy_ans if greedy_ans is not None else ""

        # 4) Majority vote; the greedy answer breaks ties.
        ranked = Counter(votes).most_common()
        top_count = ranked[0][1]
        winners = [ans for ans, c in ranked if c == top_count]
        if greedy_ans in winners:
            return greedy_ans
        return winners[0]