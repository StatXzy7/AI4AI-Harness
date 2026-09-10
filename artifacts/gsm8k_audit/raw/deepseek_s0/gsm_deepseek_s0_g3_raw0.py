"""Use three stochastic solver calls at temperature 0.4 and return the majority final answer, falling back to a single greedy call on ties."""
import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G3(MathHarness):
    def solve(self, question: str) -> str:
        prompt = self._make_prompt(question)

        # Generate three independent candidates, allowing the frozen solver to vary.
        candidates = [self._call_llm(prompt, temperature=0.4) for _ in range(3)]

        # Extract candidate final answers and normalize for voting.
        answers = []
        for candidate in candidates:
            ans = self._extract_final_answer(candidate)
            if ans:
                answers.append((self._normalize_answer(ans), ans))

        # If no candidate had an extractable final answer, fall back to greedy.
        if not answers:
            fallback = self._call_llm(prompt, temperature=0.0)
            ans = self._extract_final_answer(fallback)
            return ans if ans else fallback.strip()

        counts = Counter(norm for norm, _ in answers)
        top_norm, top_count = counts.most_common(1)[0]

        # Majority: at least two of the possible three candidates agree.
        if top_count >= 2:
            for norm, raw in answers:
                if norm == top_norm:
                    return raw

        # No majority: request a single greedy answer and use it to break the tie.
        greedy = self._call_llm(prompt, temperature=0.0)
        greedy_ans = self._extract_final_answer(greedy)
        if greedy_ans:
            greedy_norm = self._normalize_answer(greedy_ans)
            for norm, raw in answers:
                if norm == greedy_norm:
                    return raw
            return greedy_ans

        # Last resort: return the first successfully extracted candidate answer.
        return answers[0][1]

    def _call_llm(self, prompt: str, temperature: float) -> str:
        output = self.llm(prompt, system="", temperature=temperature, n=1)

        # Handle common API return shapes defensively.
        if isinstance(output, str):
            return output
        if isinstance(output, (list, tuple)):
            if not output:
                return ""
            return str(output[0])
        if isinstance(output, dict):
            for key in ("text", "content", "message"):
                if key in output:
                    return str(output[key])
            return str(output)
        if hasattr(output, "text"):
            return str(output.text)

        return str(output)

    def _make_prompt(self, question: str) -> str:
        return (
            "Solve the following competition math problem. "
            "Show your reasoning, and put the final answer on the last line exactly as:\n"
            "#### <answer>\n"
            "The answer may be a plain number, a fraction, a LaTeX expression, "
            "an interval, or a tuple. Do not put any text after the final answer line.\n\n"
            f"Problem: {question}\n"
        )

    def _extract_final_answer(self, text: str) -> str:
        if not text:
            return ""

        # Prefer an explicit '#### <answer>' line, using the last one if multiple.
        matches = re.findall(r"####\s*(.*)", text)
        if matches:
            ans = matches[-1].strip().strip("$").strip()
            return re.sub(r"\s+", "", ans)

        # If the solver ignored the format, use the last nonempty line.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            ans = lines[-1].strip("$").strip()
            return re.sub(r"\s+", "", ans)

        return ""

    def _normalize_answer(self, ans: str) -> str:
        s = ans.strip().strip("$").strip()
        s = s.replace("\\left", "").replace("\\right", "")
        s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        s = re.sub(r"\s+", "", s)

        # Unify simple fractions such as 3/4 with \frac{3}{4}.
        m = re.fullmatch(r"(-?)(\d+)/(\d+)", s)
        if m:
            sign = m.group(1)
            return f"{sign}\\frac{{{m.group(2)}}}{{{m.group(3)}}}"

        return s