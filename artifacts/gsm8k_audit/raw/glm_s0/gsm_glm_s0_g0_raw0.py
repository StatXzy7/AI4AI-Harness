"""Self-consistency voting: sample several chain-of-thought solutions at nonzero temperature, majority-vote their extracted final numbers, let the greedy decode cast an anchor vote, and re-solve once to adjudicate any remaining tie."""

import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmGlmS0G0(MathHarness):
    """GSM8K harness that improves on a single greedy call via majority voting.

    Control flow inside solve():
      1. One greedy (temperature=0) decode produces an "anchor" answer.
      2. K sampled decodes (temperature>0) produce diverse reasoning paths.
      3. A final number is extracted from every generation ("#### n",
         "answer is n", or last number as a last resort) and normalized.
      4. The most frequent answer wins; the greedy answer gets one extra
         tie-breaking vote, and if the top two candidates are still tied,
         one fresh greedy re-solve shown the tied candidates picks between
         them. No executor is used -- the solver's own text is the only signal.
    """

    K = 8                  # number of sampled chains of thought
    SAMPLE_TEMPERATURE = 0.7

    SYSTEM = (
        "You are a careful grade-school math tutor. Reason step by step with "
        "short numbered steps, then end your reply with the final numeric "
        "answer alone on the last line in the format '#### <number>'."
    )

    SOLVE_PROMPT = (
        "{question}\n\n"
        "Solve this problem step by step, then end with the final answer on "
        "its own last line in the format '#### <number>'."
    )

    JUDGE_PROMPT = (
        "{question}\n\n"
        "Several final answers were proposed for this problem:\n{options}\n\n"
        "Re-solve the problem carefully step by step, then end with the one "
        "correct final answer on its own last line in the format "
        "'#### <number>'."
    )

    _HASH_RE = re.compile(r"####\s*\$?\s*(-?\d[\d,]*(?:\.\d+)?)")
    _ANSWER_RE = re.compile(
        r"answer(?:\s+is)?\s*[:=]?\s*\$?\s*(-?\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _NUM_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?")

    # ------------------------------------------------------------------ #
    # public entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        prompt = self.SOLVE_PROMPT.format(question=question.strip())

        # 1) greedy anchor decode
        greedy_text = self._generate(prompt, temperature=0.0, n=1)[0] or ""
        greedy_ans = self._extract(greedy_text)

        # 2) sampled chains of thought
        samples = self._generate(
            prompt, temperature=self.SAMPLE_TEMPERATURE, n=self.K
        )
        sample_answers = [
            a for a in (self._extract(s) for s in samples) if a is not None
        ]

        # 3) nothing parsed anywhere -> best-effort fallback to greedy text
        if not sample_answers and greedy_ans is None:
            lines = [ln.strip() for ln in greedy_text.splitlines() if ln.strip()]
            return lines[-1] if lines else ""

        # 4) vote (greedy decode casts one extra, tie-breaking vote)
        votes = Counter(sample_answers)
        if greedy_ans is not None:
            votes[greedy_ans] += 1

        ranked = votes.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            tied = [cand for cand, v in ranked if v == ranked[0][1]]
            choice = self._adjudicate(question, tied)
            if choice is not None:
                return choice

        return ranked[0][0]

    # ------------------------------------------------------------------ #
    # tie adjudication: one fresh greedy re-solve shown the tied candidates
    # ------------------------------------------------------------------ #
    def _adjudicate(self, question: str, candidates):
        options = "\n".join(
            "({}) {}".format(i + 1, cand) for i, cand in enumerate(candidates)
        )
        prompt = self.JUDGE_PROMPT.format(
            question=question.strip(), options=options
        )
        text = self._generate(prompt, temperature=0.0, n=1)[0] or ""
        ans = self._extract(text)
        return ans if ans in candidates else None

    # ------------------------------------------------------------------ #
    # answer extraction / normalization
    # ------------------------------------------------------------------ #
    def _extract(self, text):
        """Return the normalized final number in `text`, or None."""
        if not text:
            return None
        for regex in (self._HASH_RE, self._ANSWER_RE):
            matches = regex.findall(text)
            if matches:
                return self._normalize(matches[-1])
        nums = self._NUM_RE.findall(text)
        if nums:
            return self._normalize(nums[-1])
        return None

    @staticmethod
    def _normalize(raw):
        s = str(raw).replace(",", "").replace("$", "").strip().rstrip(".")
        try:
            f = float(s)
        except (TypeError, ValueError):
            return s or None
        if f.is_integer():
            return str(int(f))
        return str(f)

    # ------------------------------------------------------------------ #
    # thin wrapper over the frozen solver, tolerant of return shapes
    # ------------------------------------------------------------------ #
    def _generate(self, prompt, temperature, n):
        texts = []
        try:
            texts = self._as_texts(
                self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=n)
            )
        except TypeError:
            texts = []
        # if the backend ignored n>1, fill in with repeated single calls
        while len(texts) < n:
            texts.extend(
                self._as_texts(
                    self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
                )
            )
        return texts[:n]

    @staticmethod
    def _as_texts(out):
        if out is None:
            return []
        if isinstance(out, str):
            return [out]
        if isinstance(out, dict):
            for key in ("text", "content", "completion", "response"):
                val = out.get(key)
                if isinstance(val, str):
                    return [val]
            return []
        if isinstance(out, (list, tuple)):
            texts = []
            for item in out:
                texts.extend(GsmGsmGlmS0G0._as_texts(item))
            return texts
        return [str(out)]