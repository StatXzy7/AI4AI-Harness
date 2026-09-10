"""Use multi-prompt self-consistency: query the frozen solver with several reasoning prompts, extract final answers, and return the majority normalized answer."""

import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G0(MathHarness):
    def solve(self, question: str) -> str:
        prompts = [
            (
                "Solve the following competition math problem. Think step by step. "
                "Put your final answer on the last line in the form '#### <answer>'.\n\n"
                f"Problem: {question}\n\nSolution:"
            ),
            (
                "You are solving a MATH-500 style problem. Work carefully and concisely. "
                "End your response with:\n#### <answer>\n\n"
                f"Problem: {question}"
            ),
            (
                "Let's work through this math problem in detail. "
                "After your reasoning, write the final answer on the last line as '#### <answer>'.\n\n"
                f"Problem: {question}"
            ),
        ]

        candidates = []
        for prompt in prompts:
            try:
                raw = self.llm(prompt, system="", temperature=0.0, n=1)
            except Exception:
                continue

            if raw is None:
                continue

            if isinstance(raw, list):
                if not raw:
                    continue
                raw = raw[0]

            answer = self._extract_answer(str(raw))
            if answer:
                candidates.append(answer)

        if not candidates:
            return ""

        normalized = [self._normalize_answer(a) for a in candidates]
        counts = Counter(normalized)
        best_norm = counts.most_common(1)[0][0]

        for answer, norm in zip(candidates, normalized):
            if norm == best_norm:
                return self._compact_answer(answer)

        return self._compact_answer(candidates[0])

    def _extract_answer(self, text: str) -> str:
        matches = re.findall(r"####\s*([^\n]+)", text)
        if matches:
            return matches[-1].strip().strip(" .")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            return lines[-1].strip().strip(" .")
        return ""

    def _normalize_answer(self, answer: str) -> str:
        s = answer.strip()
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\,", "").replace("\\;", "").replace("\\!", "")
        s = s.replace("\\ ", "")
        s = s.replace(" ", "")
        s = s.replace("$", "")
        s = s.replace("%", "")

        s = re.sub(
            r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
            r"(\1)/(\2)",
            s,
        )
        s = s.replace("\\dfrac", "").replace("\\tfrac", "")

        s = s.replace("\\sqrt", "sqrt")
        s = s.replace("\\pi", "pi")
        s = s.replace("\\theta", "theta")
        s = s.replace("\\alpha", "alpha")
        s = s.replace("\\beta", "beta")
        s = s.replace("\\gamma", "gamma")
        s = s.replace("\\cdot", "*")
        s = s.replace("\\times", "*")
        s = s.replace("\\div", "/")
        s = s.replace("\\pm", "+-")
        s = s.replace("\\leq", "<=")
        s = s.replace("\\geq", ">=")
        s = s.replace("\\neq", "!=")
        s = s.replace("\\infty", "inf")
        s = s.replace("\\{", "{").replace("\\}", "}")
        s = s.replace("{", "").replace("}", "")
        s = s.replace("\\", "")

        s = re.sub(r"\s+", "", s)
        return s

    def _compact_answer(self, answer: str) -> str:
        return re.sub(r"\s+", "", answer.strip())