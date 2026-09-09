"""Self-consistency voting with three independently sampled solutions and a verifier tie-breaker for GSM8K."""
import re
from typing import Optional
from ..harness_base import MathHarness

class GsmGsmDeepseekS0G2(MathHarness):
    def _extract_answer(self, text: str) -> Optional[str]:
        if not text:
            return None

        # Prefer the explicit GSM8K format: "#### 42"
        match = re.findall(r'####\s*(-?\d[\d,\.]*)', text)
        if match:
            return match[-1].replace(",", "")

        # Common prose patterns
        patterns = [
            r'(?:The\s+)?answer\s+is\s*:?\s*(-?\d[\d,\.]*)',
            r'=\s*(-?\d[\d,\.]*)\s*\.?\s*$',
            r'(-?\d[\d,\.]*)\s*\.?\s*$'
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[-1].replace(",", "")
        return None

    def _normalize(self, ans: Optional[str]) -> Optional[str]:
        if ans is None:
            return None
        try:
            value = float(ans.replace(",", ""))
            if value.is_integer():
                return str(int(value))
            return str(value)
        except ValueError:
            return None

    def solve(self, question: str) -> str:
        system = (
            "You are an expert grade-school math word problem solver. "
            "Solve step by step, then write the final answer on a line starting with '####'."
        )

        answers = []
        for _ in range(3):
            reply = self.llm(question, system=system, temperature=0.6, n=1)
            if isinstance(reply, list):
                reply = reply[0] if reply else ""
            elif isinstance(reply, tuple):
                reply = reply[0] if reply else ""

            ans = self._normalize(self._extract_answer(reply))
            answers.append(ans)

        counts = {}
        for ans in answers:
            if ans is not None:
                counts[ans] = counts.get(ans, 0) + 1

        if counts:
            best_ans, best_count = max(counts.items(), key=lambda kv: kv[1])
            if best_count >= 2:
                return best_ans

        valid_answers = [ans for ans in answers if ans is not None]
        if len(valid_answers) == 1:
            return valid_answers[0]

        attempt_text = "\n".join(
            f"Candidate {i + 1}: {ans if ans is not None else 'unparsed'}"
            for i, ans in enumerate(answers)
        )

        verifier_prompt = (
            f"Problem: {question}\n\n"
            "Several candidate solutions produced these final answers:\n"
            f"{attempt_text}\n\n"
            "Check each answer against the problem. If one candidate is correct, choose it; "
            "if none are correct, solve the problem yourself. "
            "End with a line starting with '####' followed by the answer."
        )

        reply = self.llm(verifier_prompt, system=system, temperature=0.0, n=1)
        if isinstance(reply, list):
            reply = reply[0] if reply else ""
        elif isinstance(reply, tuple):
            reply = reply[0] if reply else ""

        verified_ans = self._normalize(self._extract_answer(reply))
        if verified_ans is not None:
            return verified_ans

        if valid_answers:
            return valid_answers[0]
        return "0"