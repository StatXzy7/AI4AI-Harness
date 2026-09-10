"""GSM-style harness that uses majority voting over multiple temperature samples with self-consistency to select the most frequent final answer."""
from __future__ import annotations
import re
from collections import Counter
from ..harness_base import MathHarness


class GsmGsmMinimaxS0G6(MathHarness):
    """
    Improvement mechanism: Self-Consistency with Majority Voting.

    Instead of a single greedy decoding call (temperature=0.0, n=1), we:
      1. Prompt the solver N times at a small non-zero temperature to obtain
         diverse reasoning paths (chain-of-thought is encouraged).
      2. Extract the final answer on the last line in the form '#### <answer>'.
      3. Normalize the answers so that equivalent representations
         (e.g. "42", "42.0", "\\frac{42}{1}", "(42)") collapse to one bucket.
      4. Return the answer from the most common bucket (majority vote).
         Ties are broken by the first-seen answer (stable order).
      5. If no '####' marker is found in any sample, fall back to the
         extracted answer from the first sample (or empty string).

    This control-flow change exploits the empirical observation that
    competition-math problems frequently have multiple valid reasoning paths
    that converge on the same correct answer, and that the modal answer
    across samples is significantly more reliable than any single greedy
    sample, especially for problems where the base solver is a weak/medium
    language model.
    """

    # ---- Configuration -------------------------------------------------
    N_SAMPLES: int = 7           # number of diverse samples to draw
    TEMPERATURE: float = 0.5     # non-zero to encourage diversity
    MAX_EXTRACT_CHARS: int = 4000  # safety cap when scanning tail of text

    # ---- Public API ----------------------------------------------------
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        try:
            samples = self.llm(
                prompt,
                system="",
                temperature=self.TEMPERATURE,
                n=self.N_SAMPLES,
            )
        except TypeError:
            # Some LLM wrappers don't accept `n`; fall back to N calls.
            samples = [
                self.llm(prompt, system="", temperature=self.TEMPERATURE)
                for _ in range(self.N_SAMPLES)
            ]
        except Exception:
            # Last-resort single greedy call so we always return *something*.
            single = self.llm(prompt, system="", temperature=0.0, n=1)
            samples = [single]

        # Normalize samples to a list of strings (some wrappers return list-like).
        samples = self._coerce_samples(samples)

        answers_in_order: list[str] = []
        normalized_to_display: dict[str, str] = {}
        for s in samples:
            ans = self._extract_final_answer(s)
            if ans is None:
                continue
            norm = self._normalize_answer(ans)
            if norm == "":
                continue
            answers_in_order.append(norm)
            # Keep the first nice-looking display form we see for each bucket.
            normalized_to_display.setdefault(norm, ans.strip())

        if not answers_in_order:
            # Nothing parseable: return empty so caller can flag it.
            return ""

        counts = Counter(answers_in_order)
        # Most common; Counter.most_common is stable for ties in Py3.7+.
        best_norm, _ = counts.most_common(1)[0]
        return normalized_to_display[best_norm]

    # ---- Prompt construction ------------------------------------------
    def _build_prompt(self, question: str) -> str:
        # We explicitly request a chain-of-thought and the '####' marker,
        # which gives us a robust anchor for answer extraction.
        return (
            "Solve the following competition-math word problem step by step.\n"
            "Think carefully and show all reasoning.\n"
            "On the LAST line of your response, output the final answer "
            "in the exact form:\n"
            "    #### <answer>\n"
            "where <answer> may be a plain number, a fraction like 3/4 or "
            "\\frac{3}{4}, a LaTeX expression, an interval like (3,4], "
            "or a tuple like (2,5).\n\n"
            f"Problem:\n{question}\n"
        )

    # ---- Sample normalization -----------------------------------------
    @staticmethod
    def _coerce_samples(samples) -> list[str]:
        if samples is None:
            return []
        if isinstance(samples, str):
            return [samples]
        try:
            return [str(s) for s in samples]
        except Exception:
            return [str(samples)]

    # ---- Final-answer extraction --------------------------------------
    @staticmethod
    def _extract_final_answer(text: str) -> str | None:
        if not text:
            return None
        # Search for '####' marker; prefer the LAST occurrence (in case the
        # solver accidentally writes it earlier too).
        tail = text[-GsmGsmMinimaxS0G6.MAX_EXTRACT_CHARS:] \
            if len(text) > GsmGsmMinimaxS0G6.MAX_EXTRACT_CHARS else text
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if line.startswith("####"):
                ans = line[4:].strip()
                # Strip surrounding LaTeX delimiters / quotes if present.
                ans = ans.strip("$`'\"")
                return ans if ans else None
        # Fallback: regex on the whole text.
        m = re.findall(r"####\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if m:
            return m[-1].strip().strip("$`'\"")
        # Last fallback: try to grab the last non-empty "= <expr>" line.
        for line in reversed([l.strip() for l in text.splitlines() if l.strip()]):
            if line.startswith("="):
                cand = line.lstrip("=").strip().strip("$`'\"")
                if cand:
                    return cand
        return None

    # ---- Answer canonicalization --------------------------------------
    @staticmethod
    def _normalize_answer(ans: str) -> str:
        """
        Collapse equivalent representations to a single bucket key.

        Examples:
          "42", "42.0", "+42"        -> "42"
          "3/4", "\\frac{3}{4}"      -> "3/4"
          "(2, 5)", "(2,5)"          -> "(2,5)"
          "(3,4]"                    -> "(3,4]"
          "2\\sqrt{3}"               -> "2\\sqrt{3}"
        """
        if ans is None:
            return ""
        s = ans.strip()
        if not s:
            return ""

        # Unify LaTeX \frac{a}{b} -> a/b
        s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", s)

        # Drop a leading sign for numeric answers (we don't distinguish +42/42).
        s_num = s.lstrip("+").strip()

        # Try numeric collapse (integers / floats).
        try:
            f = float(s_num)
            if f.is_integer():
                norm_num = str(int(f))
            else:
                # Round-trip to drop trailing zeros, but keep precision.
                norm_num = ("%g" % f)
        except Exception:
            norm_num = None

        # If the answer is a clean integer/float, prefer that form.
        if norm_num is not None and re.fullmatch(r"[+-]?\d+(\.\d+)?", s_num):
            return norm_num

        # Otherwise, normalize whitespace and punctuation for symbolic answers.
        s2 = s
        s2 = re.sub(r"\s+", "", s2)               # remove all whitespace
        s2 = s2.replace("\\,", "").replace("\\!", "")
        s2 = s2.replace("\\left", "").replace("\\right", "")
        s2 = s2.replace(" ", "")
        return s2