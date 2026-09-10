"""Self-consistency harness around a frozen math solver: one greedy anchor generation plus five temperature-sampled re-solves are aggregated by majority vote over normalized '#### <answer>' extractions, with greedy-priority tie-breaking and a single adjudication call to settle split votes."""

import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmGlmS0G5(MathHarness):
    """Majority-vote (self-consistency) wrapper for MATH-500 style problems.

    Control flow of solve():
      1. Greedy anchor: one temperature-0 generation.
      2. Diversity: N_SAMPLES extra generations at SAMPLE_TEMPERATURE
         (odd-indexed ones get a "use your own method" nudge).
      3. Extraction: the '#### <answer>' line is pulled from every
         completion, falling back to the last \\boxed{...} or the last
         non-empty line.
      4. Normalization: answers are canonicalized ($...$, \\dfrac,
         whitespace, 'x =' prefixes, '3/4' vs '\\frac{3}{4}') so that
         equivalent forms vote together.
      5. Aggregation: the normalized answer with the highest vote count
         wins; count ties prefer the greedy anchor, and a vote that is
         still split across distinct answers triggers one adjudication
         call that must select one of the tied candidates in order to
         override the default winner.
    """

    N_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7
    DIVERSITY_SUFFIX = (
        "\nSolve it from scratch using a method of your own choosing."
    )

    SYSTEM = (
        "You are a careful competition mathematician. Solve the given "
        "problem with clear, correct steps, then report the final answer "
        "alone on the last line in the form '#### <answer>'."
    )

    PROMPT_TEMPLATE = (
        "{question}\n\n"
        "Solve this problem step by step, checking your arithmetic as you "
        "go. The final answer must be one compact expression: a number "
        "(42), a fraction (3/4 or \\frac{{3}}{{4}}), a LaTeX expression "
        "(2\\sqrt{{3}}, 6+9i), an interval ((3,4]), or a tuple ((2, 5)).\n"
        "Put the final answer on the very last line, exactly in the form:\n"
        "#### <answer>"
    )

    # --------------------------------------------------------------- #
    # public API
    # --------------------------------------------------------------- #

    def solve(self, question: str) -> str:
        prompt = self.PROMPT_TEMPLATE.format(question=question.strip())

        # Stage 1: greedy anchor generation.
        greedy_text = self._safe_call(prompt, 0.0)
        greedy_ans = self._extract(greedy_text)

        candidates = []  # (normalized, raw, is_greedy, order)
        if greedy_ans is not None:
            candidates.append((self._norm(greedy_ans), greedy_ans, True, 0))

        # Stage 2: sampled re-solves to obtain independent votes.
        for i in range(self.N_SAMPLES):
            p = prompt if i % 2 == 0 else prompt + self.DIVERSITY_SUFFIX
            ans = self._extract(self._safe_call(p, self.SAMPLE_TEMPERATURE))
            if ans is not None:
                candidates.append((self._norm(ans), ans, False, i + 1))

        if not candidates:
            return self._compact(self._last_line(greedy_text))

        # Stage 3: majority vote over normalized answers.
        tally = Counter(norm for norm, _raw, _g, _o in candidates)

        def rank(cand):
            norm, _raw, is_greedy, order = cand
            return (-tally[norm], 0 if is_greedy else 1, order)

        winner = min(candidates, key=rank)
        top_norm = winner[0]

        # Stage 4: settle split votes with one adjudication call.
        tied = [n for n, c in tally.items() if c == tally[top_norm]]
        if len(tied) > 1:
            picked = self._adjudicate(question, tied)
            if picked is not None and picked in tied:
                top_norm = picked
                winner = next(c for c in candidates if c[0] == top_norm)

        return self._compact(winner[1])

    # --------------------------------------------------------------- #
    # LLM plumbing
    # --------------------------------------------------------------- #

    def _safe_call(self, prompt: str, temperature: float) -> str:
        """Call the frozen solver, never letting an exception escape."""
        try:
            return self._call(prompt, temperature)
        except Exception:
            return ""

    def _call(self, prompt: str, temperature: float) -> str:
        """Single generation, tolerant of stricter solver signatures."""
        try:
            out = self.llm(prompt, system=self.SYSTEM,
                           temperature=temperature, n=1)
        except TypeError:
            try:
                out = self.llm(prompt, system=self.SYSTEM,
                               temperature=temperature)
            except TypeError:
                out = self.llm(prompt)
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("output") or ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            out = ""
        elif not isinstance(out, str):
            out = str(out)
        return out

    def _adjudicate(self, question: str, options):
        """One extra call that must pick one of the tied `options`."""
        options = list(options)
        listing = "\n".join(
            "({}) {}".format(i + 1, opt) for i, opt in enumerate(options)
        )
        prompt = (
            "Problem:\n"
            + question.strip()
            + "\n\nA solver produced these candidate final answers:\n"
            + listing
            + "\n\nDecide which candidate is the correct final answer to "
              "the problem; rederive the key step if that helps. Reply "
              "with the chosen answer alone on the last line in the "
              "form:\n#### <answer>"
        )
        ans = self._extract(self._safe_call(prompt, 0.0))
        if ans is None:
            return None
        norm = self._norm(ans)
        if norm in options:
            return norm
        # The judge may have replied with just the option number.
        m = re.fullmatch(r"\(?(\d+)\)?", ans.strip())
        if m:
            k = int(m.group(1)) - 1
            if 0 <= k < len(options):
                return options[k]
        return None

    # --------------------------------------------------------------- #
    # answer extraction
    # --------------------------------------------------------------- #

    @staticmethod
    def _extract(text):
        """Return the final answer string from a completion, or None."""
        if not text:
            return None
        idx = text.rfind("####")
        if idx != -1:
            first, _, rest = text[idx + 4:].partition("\n")
            line = first.strip()
            if not line and rest.strip():
                # Answer placed on the line after the marker.
                line = rest.lstrip().split("\n", 1)[0].strip()
            if line:
                cleaned = GsmGsmGlmS0G5._clean_line(line)
                if cleaned is not None:
                    return cleaned
        boxed = GsmGsmGlmS0G5._last_boxed(text)
        if boxed:
            return boxed
        line = GsmGsmGlmS0G5._last_line(text)
        if line:
            return GsmGsmGlmS0G5._clean_line(line)
        return None

    @staticmethod
    def _last_boxed(text):
        """Content of the last \\boxed{...} (brace-aware), or None."""
        key = "\\boxed{"
        i = text.rfind(key)
        if i == -1:
            return None
        j = i + len(key)
        depth = 1
        out = []
        while j < len(text) and depth > 0:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            out.append(ch)
            j += 1
        return "".join(out).strip() or None

    @staticmethod
    def _last_line(text):
        for line in reversed((text or "").strip().split("\n")):
            line = line.strip()
            if line:
                return line
        return None

    @staticmethod
    def _clean_line(line):
        """Strip discourse so only the answer expression remains."""
        s = line.strip()
        if not s:
            return None
        s = re.sub(r"^(?:therefore|so|thus|hence|finally|in\s+all)[,:;\s]*",
                   "", s, flags=re.I)
        m = re.search(
            r".*\b(?:(?:final\s+)?answers?|results?)\s*(?:are|is|:|=)\s*(.+)$",
            s, re.I,
        )
        if m:
            s = m.group(1).strip()
        if len(s) >= 2 and s[0] == "$" and s[-1] == "$":
            s = s[1:-1].strip()
        if s.endswith("."):
            s = s[:-1].rstrip()
        return s or None

    # --------------------------------------------------------------- #
    # answer normalization (the voting key)
    # --------------------------------------------------------------- #

    @staticmethod
    def _norm(ans):
        """Canonical form so equivalent answers vote together."""
        s = ans.strip()
        for opener, closer in (("$$", "$$"), ("$", "$"),
                               ("\\(", "\\)"), ("\\[", "\\]")):
            if (s.startswith(opener) and s.endswith(closer)
                    and len(s) >= len(opener) + len(closer)):
                s = s[len(opener):len(s) - len(closer)].strip()
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        s = s.replace("\\,", "").replace("\\;", "").replace("\\!", "")
        s = s.replace("~", " ")
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"^[A-Za-z][A-Za-z0-9_]*=", "", s)
        m = re.fullmatch(r"(-?\d+(?:\.\d+)?)/(-?\d+(?:\.\d+)?)", s)
        if m:  # unify 3/4 with \frac{3}{4}
            s = "\\frac{%s}{%s}" % (m.group(1), m.group(2))
        if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+", s):  # unify 1,000 with 1000
            s = s.replace(",", "")
        return s

    # --------------------------------------------------------------- #
    # output formatting
    # --------------------------------------------------------------- #

    @staticmethod
    def _compact(ans):
        """Compact display form of the winning raw answer."""
        s = re.sub(r"\s+", " ", (ans or "").strip())
        if len(s) >= 2 and s[0] == "$" and s[-1] == "$":
            s = s[1:-1].strip()
        if s.endswith("."):
            s = s[:-1].rstrip()
        return s