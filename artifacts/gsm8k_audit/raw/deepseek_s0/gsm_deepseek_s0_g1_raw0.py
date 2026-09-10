"""Improved MATH harness that samples multiple independent solutions, takes a majority vote, and uses an LLM verifier to break ties."""

import re
from collections import Counter
from typing import List, Optional

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G1(MathHarness):
    NUM_SAMPLES = 4
    SAMPLING_TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        prompt = self._build_solver_prompt(question)

        candidate_answers: List[str] = []
        candidate_solutions: List[str] = []
        for _ in range(self.NUM_SAMPLES):
            raw = self._call_llm(prompt, temperature=self.SAMPLING_TEMPERATURE)
            answer = self._extract_final(raw)
            if answer is not None:
                candidate_answers.append(answer)
                candidate_solutions.append(raw)

        if not candidate_answers:
            raw = self._call_llm(prompt, temperature=0.0)
            return self._extract_final(raw) or self._last_line(raw)

        majority = self._majority_answer(candidate_answers)
        if majority is not None:
            return majority

        verified = self._verifier_choose(question, candidate_answers, candidate_solutions)
        return verified if verified is not None else candidate_answers[0]

    def _call_llm(self, prompt: str, temperature: float) -> str:
        try:
            out = self.llm(prompt, system="", temperature=temperature, n=1)
        except Exception:
            return ""
        if out is None:
            return ""
        if isinstance(out, list):
            return str(out[0]).strip() if out else ""
        return str(out).strip()

    def _build_solver_prompt(self, question: str) -> str:
        return (
            "You are solving a competition math problem. "
            "Think through the problem carefully and provide a clear, concise solution. "
            "On the final line, put the final answer in exactly this format:\n"
            "#### <answer>\n\n"
            f"Problem: {question}\n"
        )

    def _extract_final(self, text: str) -> Optional[str]:
        if not text:
            return None

        # Prefer the last line containing the requested final-answer marker.
        for line in reversed(text.splitlines()):
            if "####" in line:
                answer = line.split("####", 1)[1].strip()
                if answer:
                    return self._clean_answer(answer)

        # Fallback: a boxed expression anywhere in the output.
        boxed_matches = re.findall(
            r"\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", text
        )
        if boxed_matches:
            return self._clean_answer(boxed_matches[-1].strip())

        return None

    def _clean_answer(self, answer: str) -> str:
        answer = answer.strip()

        # Remove surrounding math delimiters.
        if answer.startswith('$') and answer.endswith('$'):
            answer = answer[1:-1].strip()
        if answer.startswith('\\(') and answer.endswith('\\)'):
            answer = answer[2:-2].strip()

        answer = re.sub(r"\s+", "", answer)

        # Unwrap a boxed answer if it appears in the extracted text.
        boxed = re.search(
            r"\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", answer
        )
        if boxed:
            answer = boxed.group(1).strip()

        # Drop accidental trailing punctuation that shouldn't be part of a compact answer.
        answer = answer.rstrip('.,;')
        return answer.strip()

    def _normalize_answer(self, answer: str) -> str:
        answer = answer.strip()

        if answer.startswith('$') and answer.endswith('$'):
            answer = answer[1:-1].strip()
        if answer.startswith('\\(') and answer.endswith('\\)'):
            answer = answer[2:-2].strip()

        answer = re.sub(r"\s+", "", answer)
        answer = answer.replace("\\left", "").replace("\\right", "")
        answer = answer.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        answer = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", answer)
        answer = answer.replace("\\,", "").replace("\\;", "")
        answer = answer.rstrip('.,;')
        return answer

    def _majority_answer(self, answers: List[str]) -> Optional[str]:
        counts = Counter()
        representatives = {}
        for answer in answers:
            key = self._normalize_answer(answer)
            counts[key] += 1
            representatives.setdefault(key, answer)

        most_common = counts.most_common()
        if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
            return representatives[most_common[0][0]]
        return None

    def _verifier_choose(
        self, question: str, answers: List[str], solutions: List[str]
    ) -> Optional[str]:
        candidate_blocks = []
        for idx, (answer, solution) in enumerate(zip(answers, solutions), 1):
            snippet = solution.strip()
            if len(snippet) > 1200:
                snippet = snippet[-1200:]
            candidate_blocks.append(
                f"[{idx}] Answer: {answer}\nReasoning snippet: {snippet}\n"
            )

        prompt = (
            "You are an expert math verifier. Below is a problem and several candidate answers. "
            "Read the problem and the candidates, then select the correct final answer. "
            "Your final answer must be on the last line in the form '#### <answer>'.\n\n"
            f"Problem: {question}\n\n"
            + "\n".join(candidate_blocks)
        )

        raw = self._call_llm(prompt, temperature=0.0)
        return self._extract_final(raw)

    def _last_line(self, text: str) -> str:
        if not text:
            return ""
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line:
                return line
        return ""