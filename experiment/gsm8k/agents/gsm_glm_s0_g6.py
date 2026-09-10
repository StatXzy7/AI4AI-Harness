"""Improves on a single greedy call by running the frozen solver under five distinct reasoning strategies, early-exiting once one answer clinches a majority of the equivalence-normalised '#### ' extractions, and adjudicating the leading candidates from scratch when the vote is split."""

import re
from fractions import Fraction

from ..harness_base import MathHarness


class GsmGsmGlmS0G6(MathHarness):
    r"""Multi-strategy deterministic self-consistency around a frozen solver.

    Control flow (a real change vs. one greedy call):
      1. DECODE: fire the frozen solver once per reasoning strategy (plain
         step-by-step, meticulous setup, solve-then-verify, forced alternative
         method, concise expert), all at temperature 0.0. Distinct prompts
         decorrelate the greedy chains, supplying the diversity that
         self-consistency normally gets from sampling.
      2. EXTRACT: pull the '#### <answer>' line from each response (with
         \boxed{...} and last-line/'answer is' fallbacks), and stop early once
         some answer already holds a majority of all planned attempts.
      3. VOTE: fingerprint every answer (LaTeX/units/whitespace normalisation
         plus exact numeric equivalence via Fraction) and majority-vote.
      4. ADJUDICATE: on disagreement, show the leading candidates to the
         solver, which re-solves from scratch and checks each candidate; a
         careful re-solve is the tie-break of last resort, then plurality.
    """

    NUM_RE = re.compile(
        r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:/[+-]?(?:\d+(?:\.\d+)?|\.\d+))?$"
    )
    FRAC_RE = re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    MAX_ADJ_CANDIDATES = 3

    STRATEGIES = (
        (
            "",
            "Solve the problem step by step, justifying each step briefly.",
        ),
        (
            "You are a meticulous competition mathematician who never skips a check.",
            "First restate what is given and what is asked, define variables, set up "
            "the governing equations or relationships, and solve them. Re-check every "
            "arithmetic and algebraic manipulation before moving on.",
        ),
        (
            "",
            "Solve the problem, then VERIFY your result: substitute it back into the "
            "original conditions, test a boundary or special case, or check every "
            "constraint explicitly. If the verification fails, find the error, fix "
            "it, and re-verify before giving the final answer.",
        ),
        (
            "",
            "Solve the problem with a method that is NOT your first instinct -- for "
            "example work backwards from the target quantity, enumerate small cases "
            "and find a pattern, introduce coordinates, or exploit symmetry.",
        ),
        (
            "You are a concise competition coach writing model solutions.",
            "Give the shortest fully rigorous solution you can: only the essential "
            "steps, no filler, but no unjustified leaps.",
        ),
    )

    # ------------------------------------------------------------------ solve

    def solve(self, question: str) -> str:
        question = str(question or "").strip()
        majority_of_all = len(self.STRATEGIES) // 2 + 1  # 3 of 5 attempts

        candidates = []
        for system, tactic in self.STRATEGIES:
            answer = self._extract(
                self._call(self._solve_prompt(question, tactic), system)
            )
            if not answer:
                continue
            candidates.append(answer)
            # Early consensus: this answer already holds a majority of all
            # planned attempts, so the remaining calls cannot change the winner.
            if self._top_count(candidates) >= majority_of_all:
                break

        groups = self._tally(candidates)
        if not groups:  # nothing extractable at all -> strict-format rescue call
            rescue = self._extract(self._call(self._rescue_prompt(question), ""))
            return self._compact(rescue)

        need = len(candidates) // 2 + 1
        if len(groups) == 1 or groups[0]["count"] >= need:
            return self._compact(self._representative(groups[0]))

        winner = self._adjudicate(question, groups)
        return self._compact(winner or self._representative(groups[0]))

    # -------------------------------------------------------------- prompting

    def _solve_prompt(self, question, tactic):
        return (
            f"Problem:\n{question}\n\n"
            f"Approach: {tactic}\n\n"
            "Work out the solution, then give the final answer on the last line, "
            "formatted exactly as:\n"
            "#### <answer>\n"
            "The <answer> must be the compact final result only -- a number (42), "
            "a fraction (\\frac{3}{4} or 3/4), a LaTeX expression (2\\sqrt{3}, "
            "6+9i), an interval ((3,4]), or a tuple ((2, 5)). No units and no "
            "explanation on that line."
        )

    def _rescue_prompt(self, question):
        return (
            f"Problem:\n{question}\n\n"
            "Solve the problem. You MUST finish your reply with a final line of "
            "exactly the form:\n"
            "#### <answer>\n"
            "where <answer> is the compact final result only -- a number (42), a "
            "fraction (\\frac{3}{4} or 3/4), a LaTeX expression (2\\sqrt{3}), an "
            "interval ((3,4]), or a tuple ((2, 5))."
        )

    def _adjudicate(self, question, groups):
        cands = [self._representative(g) for g in groups[: self.MAX_ADJ_CANDIDATES]]
        listing = "\n".join(
            f"({label}) {cand}" for label, cand in zip("ABCDEF", cands)
        )
        prompt = (
            f"Problem:\n{question}\n\n"
            "Independent solution attempts produced these candidate final answers:\n"
            f"{listing}\n\n"
            "Solve the problem yourself from scratch. Then judge every candidate: "
            "substitute each one back into the problem's conditions, check boundary "
            "or special cases, and re-derive the key step. Select the candidate that "
            "is actually correct; if every candidate is wrong, give your own "
            "answer.\n"
            "End with the final answer on the last line, formatted exactly as:\n"
            "#### <answer>\n"
            "The <answer> must be the compact final result only -- a number (42), a "
            "fraction (\\frac{3}{4} or 3/4), a LaTeX expression (2\\sqrt{3}), an "
            "interval ((3,4]), or a tuple ((2, 5))."
        )
        answer = self._extract(
            self._call(prompt, system="You are a rigorous competition-math grader.")
        )
        if answer:
            canon, num = self._fingerprint(answer)
            for group in groups:
                if self._same(group, canon, num):
                    return self._representative(group)
            return answer  # adjudicator re-derived a fresh answer

        careful = (
            "Solve the problem with extreme care: write out every step, double-check "
            "each computation, and explicitly verify the final result against the "
            "problem statement before answering."
        )
        return self._extract(self._call(self._solve_prompt(question, careful), ""))

    def _call(self, prompt, system=""):
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                out = self.llm(prompt, system)
            except TypeError:
                out = self.llm(prompt)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if isinstance(out, dict):
            out = next(
                (
                    out[k]
                    for k in ("text", "content", "output", "response", "completion")
                    if k in out
                ),
                "",
            )
        if out is None:
            return ""
        if not isinstance(out, str):
            for attr in ("text", "content", "output", "response"):
                value = getattr(out, attr, None)
                if isinstance(value, str):
                    return value
            return str(out)
        return out

    # ------------------------------------------------------------- extraction

    def _extract(self, text):
        text = text or ""

        # 1) explicit '#### <answer>' marker (last occurrence wins)
        marker = text.rfind("####")
        if marker != -1:
            for line in text[marker + 4 :].splitlines():
                line = line.strip()
                if line:
                    return self._clean_answer(line)

        # 2) last \boxed{...}
        boxed = self._last_boxed(text)
        if boxed:
            return self._clean_answer(boxed)

        # 3) last non-empty line, with common answer labels stripped
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            if line.startswith("####"):
                inner = line[4:].strip()
                if inner:
                    return self._clean_answer(inner)
            m = re.search(
                r"(?:final\s+answer|answer)\s*(?:is|:|=)\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if m:
                return self._clean_answer(m.group(1))
            if len(line) <= 100:
                return self._clean_answer(line)
            return ""
        return ""

    @staticmethod
    def _last_boxed(text):
        idx = text.rfind("\\boxed")
        if idx == -1:
            return ""
        start = text.find("{", idx)
        if start == -1:
            return ""
        depth = 0
        for pos in range(start, len(text)):
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1 : pos]
        return ""

    @staticmethod
    def _clean_answer(answer):
        s = str(answer or "").strip()
        s = s.replace("\\$", "").replace("$", "")
        s = s.strip().lstrip(":").strip()
        s = re.sub(r"\s+", " ", s)
        if len(s) > 1 and s.endswith(".") and s[-2] != ".":
            s = s[:-1].strip()
        return s

    @staticmethod
    def _compact(answer):
        s = str(answer or "").strip()
        s = s.replace("\\$", "").replace("$", "")
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r",\s+", ",", s)  # "(2, 5)" -> "(2,5)"
        if len(s) > 1 and s.endswith(".") and s[-2] != ".":
            s = s[:-1].strip()
        return s

    # ---------------------------------------------------------------- voting

    def _top_count(self, candidates):
        groups = self._tally(candidates)
        return groups[0]["count"] if groups else 0

    def _tally(self, answers):
        groups = []
        for answer in answers:
            canon, num = self._fingerprint(answer)
            if not canon:
                continue
            for group in groups:
                if self._same(group, canon, num):
                    group["members"].append(answer)
                    break
            else:
                groups.append({"canon": canon, "num": num, "members": [answer]})
        for group in groups:
            group["count"] = len(group["members"])
        groups.sort(key=lambda g: (-g["count"], g["canon"]))
        return groups

    @staticmethod
    def _representative(group):
        # shortest equivalent form == compact output string
        return min(group["members"], key=lambda m: (len(m), m))

    @staticmethod
    def _same(group, canon, num):
        gnum = group["num"]
        if num is not None and gnum is not None:
            return num == gnum
        if num is None and gnum is None:
            return canon == group["canon"]
        return False

    def _fingerprint(self, answer):
        canon = self._canon(answer)
        return canon, self._numeric(canon)

    def _numeric(self, canon):
        if not canon or not self.NUM_RE.match(canon):
            return None
        try:
            return Fraction(canon)
        except (ValueError, ZeroDivisionError, ArithmeticError):
            return None

    # --------------------------------------------------------- normalisation

    def _canon(self, answer):
        s = str(answer or "").strip()
        if not s:
            return ""
        for src, dst in (
            ("π", "\\pi"), ("√", "\\sqrt"), ("≤", "\\le"), ("≥", "\\ge"),
            ("×", "\\times"), ("·", "\\cdot"), ("−", "-"), ("–", "-"),
        ):
            s = s.replace(src, dst)
        s = s.replace("\\$", "").replace("$", "")
        s = re.sub(r"\\[dtc]frac", r"\\frac", s)
        for _ in range(4):  # flatten \frac{a}{b} (handles simple nesting)
            flattened = self.FRAC_RE.sub(r"\1/\2", s)
            if flattened == s:
                break
            s = flattened
        s = re.sub(r"\\(?:text|mbox|mathrm)\s*\{([^{}]*)\}", r"\1", s)
        for mac in ("\\left", "\\right", "\\Bigg", "\\bigg", "\\Big", "\\big"):
            s = s.replace(mac, "")
        for mac in ("\\!", "\\,", "\\;", "\\:", "\\quad", "\\qquad", "~", "\\ "):
            s = s.replace(mac, "")
        s = s.replace("{", "").replace("}", "")
        s = re.sub(r"\^?\\circ", "", s)  # 90^\circ == 90
        s = s.replace("\\%", "%")
        s = re.sub(r"\s+", "", s)
        prefix = re.match(r"^([A-Za-z])=(.+)$", s)
        if prefix and not re.search(r"[A-Za-z]", prefix.group(2)):
            s = prefix.group(2)  # drop a decorative "x=" before a pure value
        if len(s) > 1 and s.endswith(".") and s[-2] != ".":
            s = s[:-1]
        return s