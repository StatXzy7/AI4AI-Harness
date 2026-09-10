"""Implements prompt-diverse self-consistency with extraction repair, majority voting, and an adaptive tie-break call."""
try:
    from ..harness_base import MathHarness
except ImportError:
    class MathHarness:
        def llm(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
            raise NotImplementedError

import re


class GsmGsmQwenS0G1(MathHarness):
    _FORMAT = (
        r"The final answer may be a plain number (42), a fraction (\frac{3}{4} or 3/4), "
        r"a LaTeX expression (2\sqrt{3}, 6+9i), an interval ((3,4]), or a tuple ((2, 5)). "
        r"Put your final answer on the last line exactly as '#### <answer>'."
    )

    _SYSTEM_SOLVER = (
        "You are a meticulous competition-math solver. Solve exactly and put the final answer "
        "on the last line as '#### <answer>'."
    )

    _SYSTEM_EXTRACT = (
        "You extract the final answer from a math solution. Output only the final answer "
        "on the last line as '#### <answer>'."
    )

    _SYSTEM_ADJUDGE = (
        "You are a careful math judge. Choose or produce the correct final answer. "
        "Put your final answer on the last line as '#### <answer>'."
    )

    def solve(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return ""

        ans1 = self._solve(q, "careful")
        ans2 = self._solve(q, "skeptical")

        if ans1 and ans2 and self._norm(ans1) == self._norm(ans2):
            return self._compact(ans1)

        ans3 = self._solve(q, "concise")
        candidates = [a for a in (ans1, ans2, ans3) if a and self._norm(a)]

        if not candidates:
            return self._compact(ans1 or ans2 or ans3 or "")

        best, count = self._majority(candidates)
        if count >= 2 or len(candidates) == 1:
            return best

        unique = self._unique_candidates(candidates)
        ans4 = self._adjudicate(q, unique)

        if ans4:
            k4 = self._norm(ans4)
            for cand in candidates:
                if self._norm(cand) == k4:
                    return self._compact(cand)
            return self._compact(ans4)

        return best

    def _solve(self, question: str, style: str) -> str:
        prompt = self._solve_prompt(question, style)
        out = self._call(prompt, self._SYSTEM_SOLVER, 0.0)
        ans = self._extract_final(out)

        if not ans and out:
            ans = self._repair_extraction(out)

        ans = self._compact(ans) if ans else ""
        if ans.lower().startswith("####"):
            ans = re.sub(r"^####\s*", "", ans, flags=re.IGNORECASE).strip()
        return ans

    def _adjudicate(self, question: str, candidates: list) -> str:
        prompt = self._adjudicate_prompt(question, candidates)
        out = self._call(prompt, self._SYSTEM_ADJUDGE, 0.0)
        ans = self._extract_final(out)

        if not ans and out:
            ans = self._repair_extraction(out)

        return self._compact(ans) if ans else ""

    def _call(self, prompt: str, system: str, temperature: float) -> str:
        try:
            return self.llm(prompt, system=system, temperature=temperature, n=1) or ""
        except Exception:
            return ""

    def _solve_prompt(self, question: str, style: str) -> str:
        if style == "careful":
            return (
                "Solve the following competition-math problem step by step.\n"
                f"{self._FORMAT}\n\nQuestion:\n{question}\n\nSolution:\n"
            )

        if style == "skeptical":
            return (
                "Solve the following competition-math problem, then check your result by substitution, "
                "estimation, or endpoint/domain checks. Correct it if needed.\n"
                f"{self._FORMAT}\n\nQuestion:\n{question}\n\nSolution and check:\n"
            )

        return (
            "Solve the following competition-math problem with minimal exposition. "
            "Focus on the exact final answer.\n"
            f"{self._FORMAT}\n\nQuestion:\n{question}\n\nAnswer:\n"
        )

    def _adjudicate_prompt(self, question: str, candidates: list) -> str:
        cand_lines = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates))
        return (
            "Several candidate answers were proposed for the following competition-math problem.\n"
            "First solve the problem yourself carefully. Then choose the correct candidate if one is correct; "
            "otherwise output the correct answer. Do not assume the first candidate is correct.\n"
            f"{self._FORMAT}\n\nQuestion:\n{question}\n\nCandidates:\n{cand_lines}\n\nFinal answer:\n"
        )

    def _repair_extraction(self, output: str) -> str:
        snippet = output if len(output) <= 4000 else output[-4000:]
        prompt = (
            "The following math solution did not clearly mark its final answer.\n"
            "Extract the final answer and put it on the last line as '#### <answer>'.\n\n"
            f"Solution:\n{snippet}\n\n#### "
        )
        out = self._call(prompt, self._SYSTEM_EXTRACT, 0.0)
        ans = self._extract_final(out)

        if not ans and out:
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            if lines:
                ans = self._strip_markup(lines[-1])

        return ans or ""

    def _majority(self, candidates: list):
        counts = {}
        pretty = {}
        order = []

        for cand in candidates:
            key = self._norm(cand)
            if not key:
                continue

            if key not in counts:
                counts[key] = 0
                pretty[key] = self._compact(cand)
                order.append(key)

            counts[key] += 1

        if not order:
            return "", 0

        best_key = order[0]
        best_count = counts[best_key]

        for key in order[1:]:
            if counts[key] > best_count:
                best_key = key
                best_count = counts[key]

        return pretty[best_key], best_count

    def _unique_candidates(self, candidates: list) -> list:
        seen = set()
        out = []

        for cand in candidates:
            key = self._norm(cand)
            if key and key not in seen:
                seen.add(key)
                out.append(self._compact(cand))

        return out

    def _extract_final(self, text: str) -> str:
        if not text:
            return ""

        text = str(text)

        matches = re.findall(r"####\s*(.+)", text, flags=re.IGNORECASE)
        if not matches:
            matches = re.findall(r"####\s*\n\s*(.+)", text, flags=re.IGNORECASE)

        if matches:
            ans = matches[-1].strip()
        else:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                return ""
            ans = lines[-1]

        ans = re.sub(r"^(?:final\s*answer|answer)\s*[:\-]?\s*", "", ans, flags=re.IGNORECASE)
        ans = self._strip_markup(ans)
        ans = re.sub(r"^####\s*", "", ans, flags=re.IGNORECASE).strip()
        return ans

    def _strip_markup(self, s: str) -> str:
        if not s:
            return ""

        s = str(s).strip()

        while s.startswith("$"):
            s = s[1:].strip()
        while s.endswith("$"):
            s = s[:-1].strip()

        s = self._strip_boxed(s)

        s = re.sub(r"^(?:final\s*answer|answer)\s*[:\-]?\s*", "", s, flags=re.IGNORECASE)

        if len(s) >= 2 and s[0] in "\"'`" and s[-1] == s[0]:
            s = s[1:-1]

        if s.endswith("."):
            s = s[:-1]

        return s.strip()

    def _strip_boxed(self, s: str) -> str:
        pat = re.compile(r"\\boxed\s*")

        while True:
            m = pat.search(s)
            if not m:
                return s

            pos = m.end()
            while pos < len(s) and s[pos].isspace():
                pos += 1

            if pos >= len(s) or s[pos] != "{":
                s = s[:m.start()] + s[pos:]
                continue

            content, new_pos = self._read_braced(s, pos)
            if content is None:
                return s

            s = s[:m.start()] + content + s[new_pos:]

    def _read_braced(self, s: str, start: int):
        if start >= len(s) or s[start] != "{":
            return None, start

        depth = 0
        for idx in range(start, len(s)):
            ch = s[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start + 1:idx], idx + 1

        return None, start

    def _compact(self, ans: str) -> str:
        if not ans:
            return ""

        s = self._strip_markup(ans)
        s = re.sub(r"\s+", "", s)
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\displaystyle", "")
        s = s.replace("\\\\", "\\")
        return s.strip()

    def _norm(self, ans: str) -> str:
        s = self._compact(ans)
        if not s:
            return ""

        s = s.replace("\\\\", "\\")
        s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
        s = s.replace("\u00b7", "*").replace("\u00d7", "*")

        s = self._replace_fracs(s)
        s = self._replace_sqrts(s)
        s = self._replace_texts(s)

        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\displaystyle", "")
        s = re.sub(r"\\[,;:!\s]", "", s)

        s = s.replace("{", "").replace("}", "")
        s = s.replace("\\", "")
        s = s.replace("$", "")
        s = s.lower()
        s = s.replace("infty", "infinity")
        s = re.sub(r"\s+", "", s)

        if re.fullmatch(r"-?\d+\.\d+", s):
            s = s.rstrip("0").rstrip(".")
            if s in ("", "-"):
                s = "0"

        if re.fullmatch(r"-?\d+", s):
            s = str(int(s))

        return s

    def _replace_fracs(self, s: str) -> str:
        pat = re.compile(r"\\[dt]?frac\s*")
        i = 0

        while True:
            m = pat.search(s, i)
            if not m:
                return s

            pos = m.end()
            while pos < len(s) and s[pos].isspace():
                pos += 1

            if pos >= len(s) or s[pos] != "{":
                i = m.end()
                continue

            num, pos2 = self._read_braced(s, pos)
            if num is None:
                i = m.end()
                continue

            while pos2 < len(s) and s[pos2].isspace():
                pos2 += 1

            if pos2 >= len(s) or s[pos2] != "{":
                i = m.end()
                continue

            den, pos3 = self._read_braced(s, pos2)
            if den is None:
                i = m.end()
                continue

            num_s = self._frac_expr(num)
            den_s = self._frac_expr(den)
            repl = f"{num_s}/{den_s}"

            s = s[:m.start()] + repl + s[pos3:]
            i = m.start()

    def _replace_sqrts(self, s: str) -> str:
        pat = re.compile(r"\\sqrt\s*")
        i = 0

        while True:
            m = pat.search(s, i)
            if not m:
                return s

            pos = m.end()
            while pos < len(s) and s[pos].isspace():
                pos += 1

            if pos < len(s) and s[pos] == "{":
                content, pos2 = self._read_braced(s, pos)
                if content is None:
                    i = m.end()
                    continue

                repl = f"sqrt({self._compact(content)})"
                s = s[:m.start()] + repl + s[pos2:]
                i = m.start()
                continue

            m2 = re.match(r"[A-Za-z0-9]+", s[pos:])
            if m2:
                repl = f"sqrt({m2.group(0)})"
                s = s[:m.start()] + repl + s[pos + len(m2.group(0)):]
                i = m.start()
                continue

            i = m.end()

    def _replace_texts(self, s: str) -> str:
        pat = re.compile(r"\\(?:text|mathrm|operatorname)\s*")
        i = 0

        while True:
            m = pat.search(s, i)
            if not m:
                return s

            pos = m.end()
            while pos < len(s) and s[pos].isspace():
                pos += 1

            if pos >= len(s) or s[pos] != "{":
                i = m.end()
                continue

            content, pos2 = self._read_braced(s, pos)
            if content is None:
                i = m.end()
                continue

            repl = self._compact(content)
            s = s[:m.start()] + repl + s[pos2:]
            i = m.start()

    def _frac_expr(self, expr: str) -> str:
        e = self._compact(expr)
        if not e:
            return e

        if re.fullmatch(r"[A-Za-z0-9]+", e):
            return e

        if re.search(r"[+*/^,]", e):
            return f"({e})"

        if "-" in e:
            if e.startswith("-") and "-" not in e[1:] and not re.search(r"[+*/^,]", e[1:]):
                return e
            return f"({e})"

        return e