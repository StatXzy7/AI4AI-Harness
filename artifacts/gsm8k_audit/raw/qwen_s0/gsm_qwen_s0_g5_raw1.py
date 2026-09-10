"""Uses a draft answer, an independent audit, and a reconciling judge call to choose the final #### answer."""

try:
    from ..harness_base import MathHarness
except Exception:
    if "MathHarness" not in globals():
        class MathHarness:
            def llm(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
                return ""

import re
import ast


class GsmGsmQwenS0G5(MathHarness):
    ANSWER_RE = re.compile(r"####\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    FINAL_ANSWER_RE = re.compile(
        r"(?:final\s+answer|answer)\s*(?:is|:)?\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    def solve(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return ""

        common_rules = (
            "Put the final answer on the last line in exactly this form:\n"
            "#### <answer>\n"
            "The answer must be a compact mathematical value only, with no variable names, units, or sentences. "
            "Examples: 42, -5, 3/4, \\frac{3}{4}, 2\\sqrt{3}, (3,4], (2,5).\n"
            "Do not write anything after the final answer line. Do not use #### anywhere else."
        )

        draft_system = (
            "You are a careful competition-math solver. Solve accurately and concisely. "
            + common_rules
        )
        draft_prompt = (
            f"Problem:\n{q}\n\n"
            "Solve step by step. Check signs, cases, boundary conditions, and arithmetic. "
            "When done, put the final answer on the last line as #### <answer>."
        )
        draft_raw = self._llm_safe(draft_prompt, draft_system)
        draft_ans = self._extract_answer(draft_raw)

        if not draft_ans:
            repair_prompt = (
                f"Problem:\n{q}\n\n"
                "A previous attempt did not clearly produce a final answer.\n"
                "Solve the problem now and output the final answer in the required format.\n"
                f"{common_rules}"
            )
            repair_raw = self._llm_safe(repair_prompt, draft_system)
            draft_ans = self._extract_answer(repair_raw)
            if not draft_ans:
                draft_ans = self._extract_answer(draft_raw + "\n" + repair_raw)

        audit_system = (
            "You are an independent competition-math auditor. Solve from scratch. "
            "Be skeptical of shortcuts; verify constraints, cases, and arithmetic. "
            + common_rules
        )
        audit_prompt = (
            f"Problem:\n{q}\n\n"
            "Independently solve this problem. Do not assume any previous answer is correct. "
            "Use a different approach if possible, such as direct computation, working backwards, "
            "case analysis, or substitution. End with #### <answer>."
        )
        audit_raw = self._llm_safe(audit_prompt, audit_system)
        audit_ans = self._extract_answer(audit_raw)

        if draft_ans and audit_ans and self._equivalent(draft_ans, audit_ans):
            return self._compact(draft_ans)

        if not draft_ans:
            fallback = audit_ans or self._last_nonempty_line(draft_raw) or self._last_nonempty_line(audit_raw)
            return self._compact(fallback)

        if not audit_ans:
            return self._compact(draft_ans)

        judge_system = (
            "You are a final judge for competition-math answers. Re-solve carefully and choose the correct answer. "
            + common_rules
        )
        judge_prompt = (
            f"Problem:\n{q}\n\n"
            f"Candidate answer A: {draft_ans}\n"
            f"Candidate answer B: {audit_ans}\n\n"
            "One or both may be wrong. Re-solve the problem carefully, check arithmetic and constraints, "
            "and determine which candidate is correct. If both are wrong, provide the corrected answer. "
            "End with #### <answer>."
        )
        judge_raw = self._llm_safe(judge_prompt, judge_system)
        judge_ans = self._extract_answer(judge_raw)

        if judge_ans:
            return self._compact(judge_ans)

        return self._compact(self._better_answer(draft_ans, audit_ans))

    def _llm_safe(self, prompt: str, system: str) -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if out is None:
            return ""
        if isinstance(out, str):
            return out
        try:
            return str(out)
        except Exception:
            return ""

    def _extract_answer(self, text: str) -> str:
        if not text:
            return ""

        text = str(text)

        matches = self.ANSWER_RE.findall(text)
        if matches:
            ans = matches[-1].strip()
            if ans:
                return self._compact(ans)

        boxed = self._extract_last_boxed(text)
        if boxed:
            return self._compact(boxed)

        matches = self.FINAL_ANSWER_RE.findall(text)
        if matches:
            ans = matches[-1].strip()
            if ans and len(ans) <= 120:
                return self._compact(ans)

        last = self._last_nonempty_line(text)
        if last:
            return self._compact(last)

        return ""

    def _extract_last_boxed(self, text: str) -> str:
        idx = text.rfind("\\boxed{")
        while idx != -1:
            start = text.find("{", idx)
            if start == -1:
                break

            depth = 0
            for i in range(start, len(text)):
                ch = text[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start + 1:i].strip()

            idx = text.rfind("\\boxed{", 0, idx)

        return ""

    def _last_nonempty_line(self, text: str) -> str:
        if not text:
            return ""

        for line in reversed(str(text).splitlines()):
            line = line.strip()
            if not line:
                continue

            line = re.sub(r"^[-*•]\s*", "", line)
            line = re.sub(r"^(?:final\s+answer|answer)\s*(?:is|:)?\s*", "", line, flags=re.IGNORECASE)
            line = re.sub(r"^####\s*", "", line)
            return line.strip()

        return ""

    def _compact(self, ans: str) -> str:
        s = (ans or "").strip()
        if not s:
            return ""

        s = re.sub(r"^`+|`+$", "", s)
        s = re.sub(r"^\\\[|\\\]$", "", s)
        s = s.replace("$$", "").replace("$", "")

        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"(?i)^(?:final\s+answer|answer)\s*(?:is|:)?\s*", "", s)
        s = s.strip().rstrip(".;,")

        s = re.sub(
            r"\\(?:left|right|bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr)\s*",
            "",
            s,
        )
        s = re.sub(r"\\[,;!:\s]|\\quad|\\qquad", "", s)
        s = re.sub(r"\\[dt]frac\b", "\\frac", s)
        s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|operatorname)\{([^{}]*)\}", r"\1", s)

        s = re.sub(r"\s+", " ", s).strip()

        if re.match(r"^[\(\[\{]", s) and re.search(r"[\)\]\}]$", s):
            s = re.sub(r"\s*,\s*", ",", s)
            s = re.sub(r"\(\s+", "(", s)
            s = re.sub(r"\s+\)", ")", s)
            s = re.sub(r"\[\s+", "[", s)
            s = re.sub(r"\s+\]", "]", s)
            s = re.sub(r"\{\s+", "{", s)
            s = re.sub(r"\s+\}", "}", s)

        return s.strip()

    def _equivalent(self, a: str, b: str) -> bool:
        if not a or not b:
            return False

        ca = self._compact(a)
        cb = self._compact(b)
        if ca == cb:
            return True

        na = self._normalize_for_comparison(ca)
        nb = self._normalize_for_comparison(cb)
        if na == nb:
            return True

        va = self._numeric_value(na)
        vb = self._numeric_value(nb)
        if va is not None and vb is not None:
            try:
                return abs(va - vb) <= 1e-9
            except Exception:
                return False

        fa = self._fraction_value(na)
        fb = self._fraction_value(nb)
        if fa is not None and fb is not None:
            return fa == fb

        return False

    def _normalize_for_comparison(self, s: str) -> str:
        t = self._compact(s)
        t = t.lower()
        t = t.replace(" ", "")

        t = re.sub(
            r"\\(?:left|right|bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr)\s*",
            "",
            t,
        )
        t = re.sub(r"\\[,;!:\s]|\\quad|\\qquad", "", t)
        t = re.sub(r"\\[dt]frac\b", "\\frac", t)

        for _ in range(4):
            new_t = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", t)
            if new_t == t:
                break
            t = new_t

        t = t.replace("{", "").replace("}", "")
        t = t.replace("\\", "")

        t = t.replace("−", "-").replace("–", "-").replace("—", "-")
        t = t.replace("×", "*").replace("÷", "/")

        for old, new in (
            ("½", "1/2"),
            ("⅓", "1/3"),
            ("⅔", "2/3"),
            ("¼", "1/4"),
            ("¾", "3/4"),
        ):
            t = t.replace(old, new)

        t = t.replace("infty", "infinity")
        t = t.replace("**", "^")

        return t

    def _numeric_value(self, s: str):
        if not s:
            return None

        t = s.strip()

        while t.startswith("(") and t.endswith(")"):
            inner = t[1:-1]
            if self._balanced(inner):
                t = inner.strip()
            else:
                break

        if re.fullmatch(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", t):
            try:
                return float(t)
            except Exception:
                return None

        if re.search(r"[a-zA-Z]", t):
            return None

        if not re.fullmatch(r"[-+*/^().\d\s]+", t):
            return None

        if len(t) > 200:
            return None

        expr = t.replace("^", "**")
        try:
            return self._safe_eval(expr)
        except Exception:
            return None

    def _fraction_value(self, s: str):
        if not s:
            return None

        t = s.strip()
        m = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)/([-+]?\d+(?:\.\d+)?)", t)
        if not m:
            return None

        try:
            num = float(m.group(1))
            den = float(m.group(2))
            if den == 0:
                return None
            return num / den
        except Exception:
            return None

    def _balanced(self, s: str) -> bool:
        depth = 0
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    def _safe_eval(self, expr: str):
        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Pow,
            ast.USub,
            ast.UAdd,
        )

        tree = ast.parse(expr, mode="eval")

        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise ValueError("disallowed expression")
            if isinstance(node, ast.Constant):
                if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                    raise ValueError("disallowed constant")

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)

            if isinstance(node, ast.Constant):
                return node.value

            if isinstance(node, ast.UnaryOp):
                operand = _eval(node.operand)
                if isinstance(node.op, ast.UAdd):
                    return +operand
                if isinstance(node.op, ast.USub):
                    return -operand
                raise ValueError("bad unary operator")

            if isinstance(node, ast.BinOp):
                left = _eval(node.left)
                right = _eval(node.right)

                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div):
                    if right == 0:
                        raise ZeroDivisionError("division by zero")
                    return left / right
                if isinstance(node.op, ast.Pow):
                    if abs(right) > 1000:
                        raise OverflowError("exponent too large")
                    return left ** right

                raise ValueError("bad binary operator")

            raise ValueError("bad expression node")

        return float(_eval(tree))

    def _better_answer(self, a: str, b: str) -> str:
        sa = self._answer_score(a)
        sb = self._answer_score(b)

        if sa > sb:
            return a
        if sb > sa:
            return b

        return b or a

    def _answer_score(self, ans: str) -> int:
        s = self._compact(ans)
        if not s:
            return -10

        score = 0

        if len(s) <= 80:
            score += 2
        if len(s) <= 30:
            score += 1
        if not re.search(r"[a-zA-Z]{4,}", s):
            score += 1
        if self._numeric_value(self._normalize_for_comparison(s)) is not None:
            score += 2
        if self._fraction_value(self._normalize_for_comparison(s)) is not None:
            score += 1
        if re.search(r"\d", s):
            score += 1
        if "\n" in s:
            score -= 3
        if len(s) > 200:
            score -= 3

        return score