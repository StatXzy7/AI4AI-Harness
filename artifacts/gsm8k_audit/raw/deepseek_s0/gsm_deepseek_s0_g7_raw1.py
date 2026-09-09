"""Self-consistency mechanism: sample multiple high-temperature solutions, extract final numeric answers, and return the most frequent answer with a greedy zero-temperature fallback."""

import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G7(MathHarness):
    NUM_SAMPLES = 7
    SAMPLE_TEMPERATURE = 0.7
    REQUIRED_AGREEMENT = 2

    def solve(self, question: str) -> str:
        sampling_prompt = (
            question
            + "\n\nPlease reason step-by-step and end with a final answer line: #### <number>."
        )

        greedy_text = self._call_llm(question, temperature=0.0)
        greedy_answer = self._extract_answer(greedy_text)

        answers = []
        for _ in range(self.NUM_SAMPLES):
            text = self._call_llm(sampling_prompt, temperature=self.SAMPLE_TEMPERATURE)
            ans = self._extract_answer(text)
            if ans is not None:
                answers.append(ans)

        candidate_answer, candidate_count = self._rank_answers(answers, greedy_answer) if answers else (None, 0)

        if candidate_answer is not None and candidate_count >= self.REQUIRED_AGREEMENT:
            return candidate_answer

        if greedy_answer is not None:
            return greedy_answer

        if candidate_answer is not None:
            return candidate_answer

        return self._last_number(greedy_text) or ""

    def _call_llm(self, prompt: str, temperature: float) -> str:
        res = self.llm(prompt, system="", temperature=temperature, n=1)
        if isinstance(res, str):
            return res
        if isinstance(res, (list, tuple)):
            return res[0] if res else ""
        return str(res)

    def _extract_answer(self, text: str):
        if not text:
            return None

        for line in reversed(text.splitlines()):
            if "####" in line:
                candidate = line.split("####", 1)[1].strip().lstrip(":").strip()
                if candidate:
                    num = self._number_from_candidate(candidate)
                    if num is not None:
                        return num

        phrase_patterns = [
            r'(?:the\s+)?(?:final\s+)?answer\s*(?:is|:|=)\s*[^\d-\n]*(-?\$?\d[\d,]*(?:\.\d+)?)',
            r'(?:answer\s*=\s*)[^\d-\n]*(-?\$?\d[\d,]*(?:\.\d+)?)',
        ]
        for pattern in phrase_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return self._normalize_number(m.group(1))

        return self._last_number(text)

    def _number_from_candidate(self, candidate: str):
        if not candidate:
            return None
        m = re.search(r'-?\$?\d[\d,]*(?:\.\d+)?', candidate)
        if not m:
            return None
        return self._normalize_number(m.group(0))

    def _last_number(self, text: str):
        if not text:
            return None
        matches = re.findall(r'-?\$?\d[\d,]*(?:\.\d+)?', text)
        if not matches:
            return None
        return self._normalize_number(matches[-1].replace('$', ''))

    def _normalize_number(self, raw: str):
        if raw is None:
            return None

        s = raw.strip().replace('$', '').replace('%', '').replace(',', '')
        s = s.rstrip('.')
        if not s:
            return None

        neg = s.startswith('-')
        if s.startswith('-') or s.startswith('+'):
            s = s[1:]

        if not s:
            return None

        if re.fullmatch(r'\d+', s):
            s = s.lstrip('0') or '0'
            return ('-' if neg else '') + s

        try:
            value = Decimal(s)
            if value == value.to_integral_value():
                return ('-' if neg else '') + str(int(value))
            formatted = format(value, 'f').rstrip('0').rstrip('.')
            if formatted.startswith('-'):
                formatted = formatted[1:]
            return ('-' if neg else '') + formatted
        except (InvalidOperation, ValueError):
            return ('-' if neg else '') + s

    def _rank_answers(self, answers, greedy_answer):
        counts = Counter(answers)
        if not counts:
            return None, 0

        max_count = max(counts.values())
        top_answers = [a for a, c in counts.items() if c == max_count]

        if len(top_answers) == 1:
            return top_answers[0], max_count

        if greedy_answer in top_answers:
            return greedy_answer, max_count

        first_seen = {}
        for idx, ans in enumerate(answers):
            if ans not in first_seen:
                first_seen[ans] = idx

        top_answers.sort(key=lambda a: first_seen[a])
        return top_answers[0], max_count