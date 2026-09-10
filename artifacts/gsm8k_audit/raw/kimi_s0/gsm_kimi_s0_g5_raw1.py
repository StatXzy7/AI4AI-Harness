"""Self-consistency harness: one greedy solve plus several sampled solves are aggregated by a normalized majority vote, and ties at the top are broken by a separate reconciliation call that re-derives the answer."""

import re
from collections import Counter
from fractions import Fraction

from ..harness_base import MathHarness


class GsmGsmKimiS0G5(MathHarness):
    """Wrap the frozen solver with self-consistency voting + tie reconciliation.

    Mechanism (real control-flow change vs. a single greedy call):
      1. Run one greedy (temperature 0.0) solve -- the anchor candidate.
      2. Run NUM_SAMPLES additional solves at temperature 0.7.
      3. Extract the '#### <answer>' (or \\boxed{...}) from every completion
         and normalize answers so that numerically/LaTeX-equivalent forms
         (3/4 vs \\frac{3}{4} vs 0.75, '1,000' vs '1000') vote together.
      4. Majority vote; the greedy anchor wins ties by ordering.
      5. If two or more *distinct* normalized answers tie for the top, issue
         one extra reconciliation call that re-examines the problem and must
         pick among the tied candidates; its choice wins if parseable.
    """

    NUM_SAMPLES = 4
    SAMPLE_TEMPERATURE = 0.7

    SOLVE_SYSTEM = (
        "You are an expert competition mathematician. Solve problems with "
        "clear, careful step-by-step reasoning, and always finish with the "
        "final answer on the last line in exactly the form '#### <answer>'."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        prompt = self._solve_prompt(question)

        # Phase 1: greedy anchor.
        greedy_text = self._as_text(
            self.llm(prompt, system=self.SOLVE_SYSTEM, temperature=0.0, n=1)
        )
        greedy_answer = self._extract(greedy_text)

        candidates = []  # list of (normalized_key, raw_answer), greedy first
        if greedy_answer is not None:
            candidates.append((self._key(greedy_answer), greedy_answer))

        # Phase 2: sampled solutions for self-consistency.
        for _ in range(self.NUM_SAMPLES):
            text = self._as_text(
                self.llm(
                    prompt,
                    system=self.SOLVE_SYSTEM,
                    temperature=self.SAMPLE_TEMPERATURE,
                    n=1,
                )
            )
            ans = self._extract(text)
            if ans is not None:
                candidates.append((self._key(ans), ans))

        if not candidates:
            return self._last_resort(greedy_text)

        # Phase 3: normalized majority vote (greedy-first order = greedy
        # wins any tie unless the reconciliation pass says otherwise).
        counts = Counter(k for k, _ in candidates)
        best = max(counts.values())
        top_keys = [k for k in counts if counts[k] == best]

        if len(top_keys) == 1:
            win_key = top_keys[0]
        else:
            # Phase 4: reconciliation tie-break among distinct top answers.
            tied_raws, seen = [], set()
            for k, r in candidates:
                if k in top_keys and k not in seen:
                    seen.add(k)
                    tied_raws.append(r)
            win_key = self._reconcile(question, tied_raws)
            if win_key not in top_keys:
                # Reconciliation failed to pick a tied answer: fall back to
                # the greedy anchor when it is tied at the top.
                win_key = candidates[0][0] if candidates[0][0] in top_keys else top_keys[0]

        for k, r in candidates:
            if k == win_key:
                return self._compact(r)
        return self._compact(candidates[0][1])  # defensive; unreachable

    # ------------------------------------------------------------- prompting

    @staticmethod
    def _solve_prompt(question: str) -> str:
        return (
            "Solve the following competition mathematics problem. Reason step "
            "by step, then give the final answer on its own last line in "
            "exactly this format:\n"
            "#### <answer>\n"
            "The <answer> must be only the final result -- a number, a "
            "fraction, a LaTeX expression, an interval, or a tuple -- with no "
            "units and no extra words after it.\n\n"
            f"Problem:\n{question}"
        )

    def _reconcile(self, question: str, tied_raws):
        """Ask the solver to re-derive and choose among tied candidates."""
        labels = "ABCDEFGH"
        options = "\n".join(
            f"({labels[i]}) {raw}" for i, raw in enumerate(tied_raws)
        )
        prompt = (
            "Several independent solutions to the problem below produced "
            "different final answers, listed as candidates. Re-examine the "
            "problem from scratch, redo the decisive steps carefully, and "
            "determine which candidate is correct.\n\n"
            f"Problem:\n{question}\n\n"
            f"Candidate answers:\n{options}\n\n"
            "End your response with the correct candidate's answer (the "
            "answer itself, not its label) on the last line in the form "
            "'#### <answer>'."
        )
        text = self._as_text(
            self.llm(prompt, system=self.SOLVE_SYSTEM, temperature=0.0, n=1)
        )
        ans = self._extract(text)
        return self._key(ans) if ans is not None else None

    # ----------------------------------------------------------- extraction

    @classmethod
    def _extract(cls, text):
        """Pull the final answer out of a completion, or return None."""
        if not text:
            return None

        ans = None
        matches = re.findall(r"####\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if matches:
            ans = matches[-1]
        else:
            boxed = cls._last_boxed(text)
            if boxed is not None:
                ans = boxed

        if ans is None:
            return None

        # A '#### \boxed{...}' line: unwrap the box.
        boxed = cls._last_boxed(ans)
        if boxed is not None:
            ans = boxed

        ans = ans.strip().strip("$").strip()
        if ans.endswith("."):
            ans = ans[:-1].rstrip()
        return ans or None

    @staticmethod
    def _last_boxed(text):
        """Return the contents of the last \\boxed{...} with brace matching."""
        idx = text.rfind("\\boxed")
        if idx == -1:
            return None
        open_brace = text.find("{", idx)
        if open_brace == -1:
            return None
        depth = 0
        for j in range(open_brace, len(text)):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[open_brace + 1 : j]
        return None

    # ---------------------------------------------------------- normalization

    @classmethod
    def _key(cls, ans):
        """Canonical key so equivalent answers vote together."""
        s = str(ans).strip()
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        s = s.replace("$", "")
        s = re.sub(r"\s+", "", s)
        s = s.rstrip(".")

        # Strip thousands separators: '1,000' -> '1000'.
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")

        value = cls._as_fraction(s)
        if value is not None:
            return ("num", value)
        return ("str", s)

    @staticmethod
    def _as_fraction(s):
        """Parse plain numbers, a/b, and \\frac{a}{b} into a Fraction."""
        # Handles '42', '-3', '0.75', '3/4', '-3/4'.
        if re.fullmatch(r"-?\d+(\.\d+)?|-?\d+/-?\d+", s):
            try:
                return Fraction(s)
            except (ValueError, ZeroDivisionError):
                return None
        m = re.fullmatch(r"(-?)\\frac\{(-?\d+)\}\{(-?\d+)\}", s)
        if m:
            try:
                value = Fraction(int(m.group(2)), int(m.group(3)))
                return -value if m.group(1) == "-" else value
            except ZeroDivisionError:
                return None
        return None

    @staticmethod
    def _compact(ans) -> str:
        """Compact, clean final-answer string for the harness to return."""
        s = str(ans).strip().strip("$").strip()
        s = re.sub(r"\s+", " ", s)
        if s.endswith("."):
            s = s[:-1].rstrip()
        return s

    # -------------------------------------------------------------- utilities

    @staticmethod
    def _as_text(result) -> str:
        """Tolerate llm() returning a string or a list of strings."""
        if isinstance(result, str):
            return result
        if isinstance(result, (list, tuple)):
            return "\n".join(str(x) for x in result)
        return str(result)

    @staticmethod
    def _last_resort(text) -> str:
        """If no answer marker was ever produced, return the last number."""
        nums = re.findall(r"-?\d+(?:\.\d+)?", text or "")
        return nums[-1] if nums else "0"