"""Uses self-consistency by sampling multiple high-temperature solutions, extracting final numeric answers, and returning the majority-vote result with a single greedy fallback."""

import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G4(MathHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Solve the following grade-school math word problem. "
            "Think step by step, and finish with a line containing exactly '#### <number>'.\n\n"
            f"Problem: {question}\n"
        )

        samples = self._sample_solutions(prompt, num_samples=8, temperature=0.6)
        answers = []
        for sample in samples:
            ans = self._extract_answer(sample)
            if ans is not None:
                answers.append(ans)

        if answers:
            return Counter(answers).most_common(1)[0][0]

        # Fall back to a single greedy attempt if all sampled answers are unparseable.
        greedy = self._call_llm(prompt, temperature=0.0, n=1)
        ans = self._extract_answer(greedy)
        return ans if ans is not None else ""

    def _sample_solutions(self, prompt: str, num_samples: int, temperature: float):
        samples = []
        try:
            response = self.llm(prompt, system="", temperature=temperature, n=num_samples)
        except TypeError:
            response = None

        if isinstance(response, list):
            for r in response:
                if isinstance(r, str) and r.strip():
                    samples.append(r)
        elif isinstance(response, str) and response.strip():
            samples.append(response)

        # If n>1 was not honored or fewer samples were returned, fill by
        # sampling with n=1 one at a time.
        while len(samples) < num_samples:
            sample = self._call_llm(prompt, temperature=temperature, n=1)
            if not sample:
                break
            samples.append(sample)

        return samples

    def _call_llm(self, prompt: str, temperature: float, n: int):
        try:
            r = self.llm(prompt, system="", temperature=temperature, n=n)
        except TypeError:
            try:
                r = self.llm(prompt, system="", temperature=temperature)
            except TypeError:
                r = self.llm(prompt, system="")

        if r is None:
            return ""
        if isinstance(r, list):
            r = r[0] if r else ""
        return r if isinstance(r, str) else str(r)

    def _extract_answer(self, text: str):
        if not isinstance(text, str) or not text.strip():
            return None
        text = text.strip()

        for line in reversed(text.splitlines()):
            if "####" in line:
                m = re.search(r"####\s*[^\d-]*(-?\d+(?:[\s,]\d{3})*(?:\.\d+)?)", line)
                if m:
                    return self._normalize_number(m.group(1))

        patterns = [
            r"(?:answer|Answer|ANSWER)\s*(?:is|:|=)\s*(-?\d+(?:[\s,]\d{3})*(?:\.\d+)?)",
            r"(?:result|Result|RESULT)\s*(?:is|:|=)\s*(-?\d+(?:[\s,]\d{3})*(?:\.\d+)?)",
            r"(?:answer|Answer|ANSWER)\s*[:=]\s*(-?\d+(?:[\s,]\d{3})*(?:\.\d+)?)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return self._normalize_number(m.group(1))

        # Last-resort fallback: use the last number appearing in the response.
        numbers = re.findall(r"-?\d+(?:[\s,]\d{3})*(?:\.\d+)?", text)
        if numbers:
            return self._normalize_number(numbers[-1])
        return None

    def _normalize_number(self, number_str: str):
        cleaned = number_str.replace(",", "").replace(" ", "").strip()
        if not cleaned:
            return None
        try:
            value = float(cleaned)
            return str(int(value)) if value.is_integer() else cleaned
        except ValueError:
            return cleaned