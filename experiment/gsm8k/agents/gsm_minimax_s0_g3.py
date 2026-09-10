"""Self-consistency with answer normalization: sample multiple chains, parse and canonicalize each final answer, then return the majority-voted canonical form."""
import re
from collections import Counter
from ..harness_base import MathHarness


class GsmGsmMinimaxS0G3(MathHarness):
    # Patterns to extract the final answer line
    _ANSWER_LINE_RE = re.compile(r"####\s*(.+?)\s*$", re.MULTILINE)
    _FRAC_TEX_RE = re.compile(r"\\frac\s*\{\s*([^{}]+?)\s*\}\s*\{\s*([^{}]+?)\s*\}")
    _TUPLE_RE = re.compile(r"\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)")

    def solve(self, question: str) -> str:
        system = (
            "You are a competition-math solver. Solve the problem step by step. "
            "On the last line of your response, write the final answer in the form "
            "'#### <answer>' where <answer> is a compact string "
            "(a number, a fraction like 3/4 or \\frac{3}{4}, an expression like 2\\sqrt{3}, "
            "or an interval / tuple)."
        )
        # Sample several independent chains (small, deterministic temperature)
        n_samples = 5
        raw_responses = self.llm(
            question,
            system=system,
            temperature=0.7,
            n=n_samples,
        )
        # Normalize each response's final answer, then majority-vote
        canon_counter: Counter = Counter()
        last_canonical = None
        for resp in raw_responses:
            canon = self._canonical(self._extract_answer(resp))
            if canon == "":
                continue
            canon_counter[canon] += 1
            last_canonical = canon
        if not canon_counter:
            # Fallback: try the first response's raw final line
            return self._extract_answer(raw_responses[0]) if raw_responses else ""
        # Pick the most common; ties broken by order of first appearance
        most_common = canon_counter.most_common()
        top_count = most_common[0][1]
        winners = [c for c, k in most_common if k == top_count]
        # Stable tiebreak: prefer the one we saw first (already in iteration order)
        return winners[0]

    def _extract_answer(self, text: str) -> str:
        """Pull the substring after the last '####' marker."""
        if text is None:
            return ""
        # Prefer the LAST occurrence of #### (in case the model echoes the format earlier)
        matches = list(self._ANSWER_LINE_RE.finditer(text))
        if matches:
            return matches[-1].group(1).strip()
        # Fallback: last non-empty line
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        return lines[-1] if lines else ""

    def _canonical(self, ans: str) -> str:
        """Canonicalize an answer string for voting equivalence.

        - Strips outer whitespace and trailing periods.
        - Lowercases.
        - Removes '$' delimiters.
        - Normalizes \\frac{a}{b} <-> a/b.
        - Collapses whitespace inside.
        - Treats simple numeric forms as equal (e.g. '3.0' ~ '3').
        """
        if ans is None:
            return ""
        s = ans.strip()
        # Strip surrounding LaTeX display math delimiters
        s = s.strip("$").strip()
        # Drop a trailing period
        if s.endswith("."):
            s = s[:-1].rstrip()
        s = s.lower()
        s = s.replace("\\,", "").replace("\\;", "").replace("\\!", "")
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\cdot", "*")
        s = s.replace("\\sqrt", "sqrt")
        # Normalize \frac{a}{b} <-> a/b
        m = self._FRAC_TEX_RE.fullmatch(s)
        if m:
            s = f"{m.group(1).strip()}/{m.group(2).strip()}"
        else:
            # Replace any \frac{a}{b} substrings
            def _frac_sub(mm):
                return f"{mm.group(1).strip()}/{mm.group(2).strip()}"
            s = self._FRAC_TEX_RE.sub(_frac_sub, s)
        # Trim a trailing "/1"
        if s.endswith("/1") and "/" in s[:-2]:
            s = s[:-2]
        # Collapse whitespace
        s = re.sub(r"\s+", "", s)
        # Numeric normalization
        try:
            # Only safe for plain numbers / fractions of ints
            if "/" in s and all(p.lstrip("-").isdigit() for p in s.split("/")):
                num, den = s.split("/")
                if int(den) != 0:
                    val = int(num) / int(den)
                    # Represent as reduced fraction if close to a rational
                    s = f"{num}/{den}"  # keep reduced form below
            elif re.fullmatch(r"-?\d+(?:\.\d+)?", s):
                # Strip trailing .0
                if "." in s:
                    try:
                        f = float(s)
                        if f.is_integer():
                            s = str(int(f))
                    except Exception:
                        pass
        except Exception:
            pass
        return s