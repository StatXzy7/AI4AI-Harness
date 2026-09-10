"""Uses multiple prompted generations, normalized answer voting, and a verification tie-breaker."""
try:
    from ..harness_base import MathHarness
except Exception:
    class MathHarness:
        def llm(self, prompt, system="", temperature=0.0, n=1):
            return ""

import re
from collections import Counter


class GsmGsmQwenS0G0(MathHarness):
    SYSTEM = (
        "You are a careful competition-math solver. "
        r"Always put the final answer on the last line in the exact format: #### <answer>. "
        r"The answer should be compact, e.g. 42, \frac{3}{4}, 2\sqrt{3}, (3,4], or (2,5)."
    )

    def solve(self, question: str) -> str:
        q = (question or "").strip()

        attempts = [
            (self._solve_prompt(q, "Work step by step."), 0.0),
            (self._solve_prompt(q, "Solve carefully, then double-check arithmetic, signs, endpoints, and units."), 0.0),
            (self._solve_prompt(q, "Solve the problem; if one approach stalls, try a different valid method."), 0.7),
        ]

        records = []
        for prompt, temp in attempts:
            text = self._generate(prompt, temperature=temp)
            ans = self._extract_answer(text)
            if ans:
                cleaned = self._clean_answer(ans)
                norm = self._normalize(cleaned)
                if norm:
                    records.append((norm, cleaned))

        if not records:
            text = self._generate(self._direct_prompt(q), temperature=0.0)
            ans = self._extract_answer(text)
            if ans:
                cleaned = self._clean_answer(ans)
                if self._normalize(cleaned):
                    return cleaned
            return self._clean_answer(self._last_line(text))

        counts = Counter(norm for norm, _ in records)
        answers = {}
        order = []
        for norm, cleaned in records:
            if norm not in answers:
                answers[norm] = cleaned
                order.append(norm)

        max_count = max(counts.values())
        if max_count >= 2:
            for norm in order:
                if counts[norm] == max_count:
                    return self._clean_answer(answers[norm])

        proposal_norm = order[0]
        proposal_ans = answers[proposal_norm]

        verify_text = self._generate(self._verify_prompt(q, proposal_ans), temperature=0.0)
        verify_ans = self._extract_answer(verify_text)

        if verify_ans:
            verify_cleaned = self._clean_answer(verify_ans)
            verify_norm = self._normalize(verify_cleaned)
            if verify_norm:
                if verify_norm in answers:
                    return self._clean_answer(answers[verify_norm])
                return verify_cleaned

        return self._clean_answer(proposal_ans)

    def _solve_prompt(self, question, extra=""):
        parts = [
            "Solve the competition-math problem below.",
            "Put the final answer on the last line exactly as: #### <answer>.",
            "Do not put any text after that final line.",
        ]
        if extra:
            parts.append(extra)
        parts.extend(["Problem:", question, "Solution:"])
        return "\n".join(parts)

    def _direct_prompt(self, question):
        return "\n".join([
            "Give the final answer to the competition-math problem below.",
            "Put the final answer on the last line exactly as: #### <answer>.",
            "Problem:",
            question,
            "Answer:",
        ])

    def _verify_prompt(self, question, candidate):
        return "\n".join([
            "A proposed answer for the problem below is: " + str(candidate),
            "First solve the problem independently, then compare with the proposal.",
            "If the proposal is exactly correct, output it as the final answer.",
            "If the proposal is wrong, output the correct answer instead.",
            "Put the final answer on the last line exactly as: #### <answer>.",
            "Problem:",
            question,
            "Verification:",
        ])

    def _generate(self, prompt, temperature=0.0):
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        except TypeError:
            try:
                out = self.llm(prompt, system=self.SYSTEM, temperature=temperature)
            except Exception:
                return ""
        except Exception:
            return ""
        return self._as_text(out)

    def _as_text(self, out):
        if out is None:
            return ""

        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""

        if isinstance(out, dict):
            if "choices" in out:
                choices = out.get("choices") or []
                if choices:
                    choice = choices[0]
                    if isinstance(choice, dict):
                        if "text" in choice:
                            out = choice["text"]
                        elif "message" in choice:
                            message = choice["message"]
                            if isinstance(message, dict):
                                out = message.get("content", "")
                            else:
                                out = message
                    else:
                        out = choice
            else:
                for key in ("text", "completion", "content", "output", "message"):
                    if key in out:
                        out = out[key]
                        break

        return str(out)

    def _extract_answer(self, text):
        text = str(text or "")
        if not text.strip():
            return ""

        matches = re.findall(r"^\s*####\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if matches:
            return self._clean_answer(matches[-1])

        matches = re.findall(
            r"(?:final\s*answer|answer)\s*[:=-]\s*(.+?)\s*$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if matches:
            return self._clean_answer(matches[-1])

        unboxed = self._unbox(text)
        if unboxed != text:
            cleaned = self._clean_answer(unboxed)
            if cleaned:
                return cleaned

        return self._clean_answer(self._last_line(text))

    def _last_line(self, text):
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def _clean_answer(self, ans):
        ans = str(ans or "").strip()
        if not ans:
            return ""

        ans = ans.strip("`").strip()
        ans = re.sub(r"^(?:final\s+)?answer\s*[:=-]?\s*", "", ans, flags=re.IGNORECASE)
        ans = self._unbox(ans)
        ans = ans.strip().strip("$").strip()

        if ans.startswith("\\(") and ans.endswith("\\)"):
            ans = ans[2:-2].strip()
        if ans.startswith("\\[") and ans.endswith("\\]"):
            ans = ans[2:-2].strip()

        ans = ans.rstrip(".;,")
        ans = re.sub(r"\s+", "", ans)
        return ans

    def _unbox(self, s):
        s = str(s or "")
        idx = s.rfind("\\boxed")
        if idx == -1:
            return s

        start = s.find("{", idx)
        if start == -1:
            return s

        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return self._unbox(s[start + 1:i])

        return s

    def _normalize(self, ans):
        s = self._clean_answer(ans)
        if not s:
            return ""

        s = s.lower()

        for old, new in [
            ("\u2212", "-"),
            ("\u2013", "-"),
            ("\u2014", "-"),
            ("\u221e", "infty"),
            ("\u03c0", "pi"),
            ("\u00b7", "*"),
            ("\u00d7", "*"),
        ]:
            s = s.replace(old, new)

        s = s.replace("$", "")
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\!", "").replace("\\,", "").replace("\\;", "").replace("\\ ", "")
        s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        s = s.replace("\\displaystyle", "")
        s = s.replace("\\{", "{").replace("\\}", "}")

        prev = None
        while prev != s:
            prev = s
            s = re.sub(r"(?<!\d)\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", s)

        s = re.sub(r"\\(?:text|mathrm|operatorname)\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"(\\[a-zA-Z]+)\{([^{}]+)\}", r"\1\2", s)

        return s