"""Use a zero-temperature greedy answer as a tie-breaker for self-consistency voting over multiple stochastic rollouts."""
import re
from collections import Counter
from typing import List, Optional

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G5(MathHarness):
    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7
    SYSTEM_PROMPT = ""

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        greedy_answer = self._parse_answer(self._call(prompt, temperature=0.0))

        samples: List[str] = []
        for _ in range(self.NUM_SAMPLES):
            answer = self._parse_answer(self._call(prompt, temperature=self.SAMPLE_TEMPERATURE))
            if answer:
                samples.append(answer)

        if not samples:
            return greedy_answer or ""

        if greedy_answer:
            samples.append(greedy_answer)

        counts = Counter(self._normalize(answer) for answer in samples)
        max_count = max(counts.values())
        candidates = [key for key, count in counts.items() if count == max_count]

        selected_key = self._select_key(candidates, samples, greedy_answer)

        if greedy_answer and self._normalize(greedy_answer) == selected_key:
            return greedy_answer

        for answer in samples:
            if self._normalize(answer) == selected_key:
                return answer

        return samples[-1]

    def _build_prompt(self, question: str) -> str:
        return (
            "Solve the following competition math problem carefully. "
            "Write a concise step-by-step solution, then put the final answer "
            "on the last line in the exact format '#### <answer>'. "
            "The <answer> must be compact, e.g. 42, \\frac{3}{4}, 2\\sqrt{3}, "
            "6+9i, (3,4], or (2,5).\n\n"
            f"Problem: {question}\n"
        )

    def _call(self, prompt: str, temperature: float) -> str:
        result = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=temperature, n=1)
        if isinstance(result, list):
            return result[0] if result else ""
        return result or ""

    def _parse_answer(self, text: str) -> Optional[str]:
        if not text:
            return None

        # The expected format: the answer is on a line beginning with '####'.
        hash_matches = re.findall(r'####\s*(.*?)\s*$', text, flags=re.MULTILINE)
        if hash_matches:
            raw = hash_matches[-1].strip()
            if raw:
                return self._compact_answer(raw)

        # Fallback for models that prefer \boxed{}.
        boxed_matches = re.findall(r'\\boxed\{([^{}]+)\}', text)
        if boxed_matches:
            return self._compact_answer(boxed_matches[-1].strip())

        return None

    def _compact_answer(self, raw: str) -> Optional[str]:
        # If the answer itself is wrapped in \boxed{}, unwrap it first.
        boxed_inner = re.search(r'\\boxed\{([^{}]+)\}', raw)
        if boxed_inner:
            raw = boxed_inner.group(1)

        raw = re.sub(r'\s+', '', raw)
        raw = raw.replace('\\[', '').replace('\\]', '')
        raw = raw.replace('\\(', '').replace('\\)', '')
        raw = raw.replace('$', '')
        if raw.endswith('.'):
            raw = raw[:-1]
        return raw or None

    def _normalize(self, answer: str) -> str:
        normalized = self._compact_answer(answer) or answer
        normalized = normalized.replace('\\left', '').replace('\\right', '')
        normalized = normalized.replace('\\displaystyle', '')
        # Make common fraction syntaxes compare equal.
        normalized = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', normalized)
        normalized = re.sub(r'\\dfrac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', normalized)
        normalized = re.sub(r'\\tfrac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', normalized)
        return normalized

    def _select_key(
        self,
        candidates: List[str],
        samples: List[str],
        greedy_answer: Optional[str],
    ) -> str:
        if len(candidates) == 1:
            return candidates[0]

        if greedy_answer:
            greedy_key = self._normalize(greedy_answer)
            if greedy_key in candidates:
                return greedy_key

        for answer in samples:
            key = self._normalize(answer)
            if key in candidates:
                return key

        return candidates[0]