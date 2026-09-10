"""Majority-vote self-consistency harness that samples multiple diverse solutions and returns the most frequent final answer."""
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G6(MathHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are a careful competition-math problem solver. Solve step by step, "
            "and put your final answer on the last line exactly as '#### <answer>'."
        )
        prompt = (
            f"Problem: {question}\n\n"
            "Solve the problem step by step. Put your final answer on the last line "
            "in the form '#### <answer>'."
        )

        raw = self.llm(prompt, system=system, temperature=0.6, n=6)
        if isinstance(raw, str):
            responses = [raw]
        else:
            responses = list(raw)

        answers = []
        for response in responses:
            if isinstance(response, dict):
                response = response.get("text") or response.get("output") or ""
            answer = self._extract_final_answer(response)
            if answer:
                answers.append(answer)

        if not answers:
            return ""

        canonical_counts = Counter(self._canonicalize(answer) for answer in answers)
        best_key = canonical_counts.most_common(1)[0][0]

        for answer in answers:
            if self._canonicalize(answer) == best_key:
                return answer

        return answers[0]

    @staticmethod
    def _extract_final_answer(text: str) -> str:
        if not isinstance(text, str):
            return ""

        lines = text.strip().splitlines()

        for line in reversed(lines):
            if "####" in line:
                answer = line.split("####", 1)[1].strip()
                if answer:
                    return GsmGsmDeepseekS0G6._clean_answer(answer)

        for line in reversed(lines):
            line = line.strip()
            if line:
                return GsmGsmDeepseekS0G6._clean_answer(line)

        return ""

    @staticmethod
    def _clean_answer(answer: str) -> str:
        answer = answer.strip()

        if answer.startswith("$") and answer.endswith("$"):
            answer = answer[1:-1].strip()

        while answer.startswith("\\boxed{") and answer.endswith("}"):
            answer = answer[len("\\boxed{"):-1].strip()

        return answer

    @staticmethod
    def _canonicalize(answer: str) -> str:
        answer = GsmGsmDeepseekS0G6._clean_answer(answer)
        answer = answer.replace("\\dfrac", "\\frac")
        answer = answer.replace("\\left", "").replace("\\right", "")
        answer = "".join(answer.split())
        return answer