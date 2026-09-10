"""Self-consistency harness: generate one greedy and three sampled solutions, majority-vote over normalized '#### <answer>' extractions, and settle ties with a zero-temperature verification pass."""

import math
import re
from collections import Counter
from fractions import Fraction

from ..harness_base import MathHarness

_SOLVE_SYSTEM = (
    "You are an expert competition mathematician. Solve the problem with "
    "clear, efficient reasoning, then put the final answer on the last line "
    "in the exact form '#### <answer>'. The answer may be a plain number, a "
    "fraction, a LaTeX expression, an interval, or a tuple. Do not write "
    "anything after that line."
)

_VERIFY_SYSTEM = (
    "You are a meticulous competition-math checker. Work the problem again "
    "from scratch, decide which candidate answer is correct, and put that "
    "answer on the last line in the exact form '#### <answer>'."
)

_HASH_RE = re.compile(r"####\s*(.+)")
_FRAC_RE = re.compile(r"\\[dt]?frac\{([^{}]+)\}\{([^{}]+)\}")
_ASSIGN_RE = re.compile(r"^[A-Za-z](?:_\{?[A-Za-z0-9]+\}?)?\s*=\s*")
_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")
_SIMPLE_FRAC_RE = re.compile(r"^(-?)\(?(-?\d+)\)?/\(?(-?\d+)\)?$")
_INDEX_RE = re.compile(r"^\(?(\d+)\)?$")


class GsmGsmKimiS0G3(MathHarness):
    """Self-consistency wrapper around the frozen solver.

    Mechanism (vs. a single greedy call):
      1. Sample the solver once greedily and three times at T>0.
      2. Extract '#### <answer>' (with a \\boxed{} fallback) from each.
      3. Canonicalize answers so that e.g. '3/4', '\\frac{3}{4}' and '0.75'
         vote together.
      4. Majority vote; on a tie, run a zero-temperature verification pass
         that re-solves the problem against the tied candidates.
      5. Fallbacks: prefer the greedy candidate, else the most compact one.
    """

    NUM_SAMPLES = 3
    SAMPLE_TEMPERATURE = 0.7

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        prompt = (
            question.strip()
            + "\n\nRemember: the last line of your response must be "
              "'#### <answer>'."
        )

        answers = []
        greedy_answer = None
        for i in range(self.NUM_SAMPLES + 1):
            temperature = 0.0 if i == 0 else self.SAMPLE_TEMPERATURE
            text = self._generate(prompt, _SOLVE_SYSTEM, temperature)
            ans = self._extract_answer(text)
            if not ans:
                continue
            if i == 0:
                greedy_answer = ans
            answers.append(ans)

        if not answers:
            return self._last_resort(question)

        counts = Counter(self._normalize(a) for a in answers)
        reps = {}
        for a in answers:  # first-seen (greedy-preferred) representative
            reps.setdefault(self._normalize(a), a)
        ranked = counts.most_common()

        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            return reps[ranked[0][0]]

        tied = [reps[k] for k, c in ranked if c == ranked[0][1]]
        verified = self._verify(question, tied)
        if verified is not None:
            return verified
        if greedy_answer is not None and greedy_answer in tied:
            return greedy_answer
        return min(tied, key=len)

    # ------------------------------------------------------- LLM plumbing

    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _verify(self, question: str, tied: list):
        options = "\n".join(f"({i + 1}) {a}" for i, a in enumerate(tied))
        prompt = (
            "Problem:\n" + question.strip()
            + "\n\nCandidate answers:\n" + options
            + "\n\nSolve the problem again from scratch and decide which "
              "candidate is correct. Output the correct candidate's answer "
              "exactly, on the last line, as '#### <answer>'."
        )
        ans = self._extract_answer(self._generate(prompt, _VERIFY_SYSTEM, 0.0))
        if not ans:
            return None
        key = self._normalize(ans)
        for a in tied:
            if self._normalize(a) == key:
                return a
        m = _INDEX_RE.fullmatch(ans.strip())  # model echoed an option index
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(tied):
                return tied[idx]
        return None

    def _last_resort(self, question: str) -> str:
        prompt = (
            question.strip()
            + "\n\nAnswer with only the final answer, no explanation, on the "
              "last line as '#### <answer>'."
        )
        text = self._generate(prompt, _SOLVE_SYSTEM, 0.0)
        ans = self._extract_answer(text)
        if ans:
            return ans
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return self._clean(lines[-1])[:200] if lines else ""

    # ------------------------------------------------------- extraction

    @classmethod
    def _extract_answer(cls, text: str):
        if not text:
            return None
        hits = _HASH_RE.findall(text)
        if hits:
            ans = cls._clean(hits[-1])
            if ans:
                return ans
        return cls._last_boxed(text)

    @staticmethod
    def _last_boxed(text: str):
        idx = text.rfind("\\boxed{")
        if idx == -1:
            return None
        i = idx + len("\\boxed{")
        depth, start = 1, i
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth:
            return None
        ans = text[start:i - 1].strip()
        return ans or None

    # --------------------------------------------------- canonicalization

    @staticmethod
    def _clean(ans) -> str:
        s = str(ans).strip()
        for open_t, close_t in (("$$", "$$"), ("$", "$"),
                                ("\\[", "\\]"), ("\\(", "\\)"),
                                ("**", "**")):
            if s.startswith(open_t) and s.endswith(close_t) \
                    and len(s) > len(open_t) + len(close_t):
                s = s[len(open_t):len(s) - len(close_t)].strip()
        s = _ASSIGN_RE.sub("", s)          # "x = 42" -> "42"
        while s.endswith("."):             # trailing sentence period
            s = s[:-1].rstrip()
        return s.strip()

    @classmethod
    def _normalize(cls, ans):
        s = cls._clean(ans)
        s = re.sub(r"\s+", "", s)
        s = s.replace("\\left", "").replace("\\right", "")
        for tok in ("\\!", "\\,", "\\;", "\\ "):
            s = s.replace(tok, "")
        if not (s[:1] in "([" and s[-1:] in ")]"):
            s = _COMMA_RE.sub("", s)       # "1,000" -> "1000"
        if s.endswith("\\%"):
            s = s[:-2]
        elif s.endswith("%"):
            s = s[:-1]
        prev = None
        while prev != s:                   # \frac{a}{b} -> (a)/(b), nested
            prev = s
            s = _FRAC_RE.sub(r"(\1)/(\2)", s)
        m = _SIMPLE_FRAC_RE.fullmatch(s)
        if m:
            try:
                sign = -1 if m.group(1) == "-" else 1
                return ("num", sign * Fraction(int(m.group(2)),
                                               int(m.group(3))))
            except (ValueError, ZeroDivisionError):
                pass
        try:
            return ("num", Fraction(s))
        except (ValueError, ZeroDivisionError, OverflowError):
            pass
        try:
            f = float(s)
            if math.isfinite(f):
                return ("num", f)
        except (ValueError, OverflowError):
            pass
        if "i" in s:                       # e.g. "6+9i"
            try:
                return ("num", complex(s.replace("i", "j")))
            except ValueError:
                pass
        return ("str", s)