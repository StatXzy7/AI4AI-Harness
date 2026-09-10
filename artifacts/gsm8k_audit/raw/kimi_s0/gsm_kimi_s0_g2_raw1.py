"""Self-consistency harness: combine one greedy and several sampled solutions, normalize their '#### answers, majority-vote, and resolve ties with a verifier re-check."""

import re
from collections import Counter
from fractions import Fraction

from ..harness_base import MathHarness


_SOLVE_SYSTEM = (
    "You are an expert competition mathematician. Solve each problem with "
    "clear, careful step-by-step reasoning, and always finish with the final "
    "answer on the last line in the form '#### <answer>'."
)

_SOLVE_PROMPT = (
    "Solve the following competition math problem. Reason step by step, then "
    "give the final answer (a number, fraction, LaTeX expression, interval, "
    "or tuple) on the last line in exactly this form:\n"
    "#### <answer>\n\n"
    "Problem:\n{question}"
)

_VERIFY_PROMPT = (
    "Problem:\n{question}\n\n"
    "Several candidate final answers were produced by different solvers:\n"
    "{candidates}\n\n"
    "Recompute the answer yourself, then decide which candidate is correct. "
    "On the last line write '#### <k>' where <k> is the number of the "
    "correct candidate (or the correct answer itself if none are right)."
)


class GsmGsmKimiS0G2(MathHarness):
    NUM_SAMPLES = 5      # extra sampled solutions on top of the greedy one
    SAMPLE_TEMP = 0.7    # sampling temperature for diversity

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        prompt = _SOLVE_PROMPT.format(question=question)
        candidates = []          # list of (canonical_key, compact_answer)
        last_text = ""
        greedy_compact = ""

        # 1) Greedy solution (the baseline single call).
        last_text = self._call(prompt, _SOLVE_SYSTEM, 0.0)
        ans = self._extract(last_text)
        if ans:
            greedy_compact = self._compact(ans)
            candidates.append((self._key(ans), greedy_compact))

        # 2) Diverse sampled solutions.
        for _ in range(self.NUM_SAMPLES):
            last_text = self._call(prompt, _SOLVE_SYSTEM, self.SAMPLE_TEMP)
            ans = self._extract(last_text)
            if ans:
                candidates.append((self._key(ans), self._compact(ans)))

        if not candidates:
            return self._last_line(last_text)

        # 3) Majority vote over canonicalized answers.
        counts = Counter(k for k, _ in candidates)
        ranked = counts.most_common()
        top = ranked[0][1]
        winners = [k for k, c in ranked if c == top]
        first_of = {}
        for k, c in candidates:
            first_of.setdefault(k, c)

        if len(winners) == 1:
            return first_of[winners[0]]

        # 4) Tie: ask the frozen solver to verify/adjudicate.
        options = [first_of[k] for k in winners]
        chosen = self._verify(question, options)
        if chosen is not None:
            return chosen
        # Fallback: trust the greedy answer if it is among the tied winners.
        if greedy_compact and self._key(greedy_compact) in winners:
            return greedy_compact
        return options[0]

    # ------------------------------------------------------------- helpers

    def _call(self, prompt: str, system: str, temperature: float) -> str:
        """Call the frozen solver, degrading gracefully to temperature 0."""
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            try:
                out = self.llm(prompt, system=system, temperature=0.0, n=1)
            except Exception:
                return ""
        return out if isinstance(out, str) else str(out or "")

    def _verify(self, question: str, options):
        listing = "\n".join(f"{i + 1}) {o}" for i, o in enumerate(options))
        text = self._call(
            _VERIFY_PROMPT.format(question=question, candidates=listing),
            _SOLVE_SYSTEM,
            0.0,
        )
        ans = self._extract(text)
        if not ans:
            return None
        m = re.search(r"\d+", ans)
        if m:
            k = int(m.group())
            if 1 <= k <= len(options):
                return options[k - 1]
        key = self._key(ans)
        for o in options:
            if self._key(o) == key:
                return o
        return None

    # ------------------------------------------------- extraction & voting

    @classmethod
    def _extract(cls, text: str) -> str:
        """Pull the final answer out of a solver response."""
        if not text:
            return ""
        idx = text.rfind("####")
        if idx != -1:
            tail = text[idx + 4:].strip()
            if tail:
                return tail.splitlines()[0].strip()
            return ""
        boxed = cls._boxed(text)
        if boxed:
            return boxed
        return cls._last_line(text)

    @staticmethod
    def _boxed(text: str) -> str:
        idx = text.rfind("\\boxed{")
        if idx == -1:
            return ""
        i = idx + len("\\boxed{")
        depth, out = 1, []
        while i < len(text) and depth:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            out.append(ch)
            i += 1
        return "".join(out).strip()

    @staticmethod
    def _last_line(text: str) -> str:
        lines = [l.strip() for l in str(text).strip().splitlines() if l.strip()]
        return lines[-1] if lines else ""

    @staticmethod
    def _compact(ans: str) -> str:
        """Compact display form, e.g. '42', '\\frac{3}{4}', '(3,4]'."""
        s = str(ans).strip().rstrip(".").strip()
        s = s.replace("$", "")
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        for junk in ("\\!", "\\,", "\\;", "\\ "):
            s = s.replace(junk, "")
        s = s.replace(" ", "")
        return s

    @classmethod
    def _key(cls, ans: str):
        """Canonical key so '3/4', '\\frac{3}{4}' and '0.75' vote together."""
        s = cls._compact(ans)
        s = re.sub(r"\\text\s*\{[^{}]*\}", "", s)
        s = re.sub(r"(?<=\d),(?=\d)", "", s)  # thousands separators

        def mixed(m):  # 2\frac{3}{4} -> 11/4
            w, a, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            sign = -1 if w < 0 else 1
            return f"{sign * (abs(w) * b + a)}/{b}"

        t = re.sub(r"(-?\d+)\\frac\{(-?\d+)\}\{(-?\d+)\}", mixed, s)
        t = re.sub(r"\\frac\{(-?\d+)\}\{(-?\d+)\}", r"\1/\2", t)
        try:
            f = Fraction(t)  # accepts '42', '3/4', '-2', '0.75'
            return ("num", f.numerator, f.denominator)
        except Exception:
            pass
        return ("str", s)