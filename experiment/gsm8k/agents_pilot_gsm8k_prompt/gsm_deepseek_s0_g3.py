"""Self-consistency with majority voting over diverse solver samples, falling back to greedy decoding on ties or parse failures."""
import re
from collections import Counter
from typing import List, Optional

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G3(MathHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Solve the following grade-school math problem step by step. "
            "End your response with the final numeric answer on a new line in the form `#### answer`.\n\n"
            f"Question: {question}\n"
        )

        samples = self._collect_samples(prompt, temperature=0.7, n=8)
        answers = []
        for sample in samples:
            ans = self._extract_answer(sample)
            if ans is not None:
                answers.append(ans)

        if answers:
            counts = Counter(answers)
            most = counts.most_common()
            if len(most) == 1 or most[0][1] > most[1][1]:
                return most[0][0]

        # If no single majority answer emerged, fall back to greedy.
        try:
            greedy = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(greedy, list):
                greedy = greedy[0] if greedy else ""
            ans = self._extract_answer(greedy)
            if ans is not None:
                return ans
        except Exception:
            pass

        if answers:
            return answers[0]

        # Last resort: return a number found in any sample.
        for sample in samples:
            ans = self._extract_answer(sample)
            if ans is not None:
                return ans
        return "0"

    def _collect_samples(self, prompt: str, temperature: float, n: int) -> List[str]:
        samples = []
        try:
            out = self.llm(prompt, system="", temperature=temperature, n=n)
            if isinstance(out, list):
                samples.extend([x for x in out if x])
            elif out is not None:
                samples.append(out)
        except Exception:
            pass

        while len(samples) < n:
            try:
                out = self.llm(prompt, system="", temperature=temperature, n=1)
                if isinstance(out, list):
                    valid = [x for x in out if x]
                    if valid:
                        samples.extend(valid)
                    else:
                        break
                elif out is not None:
                    samples.append(out)
                else:
                    break
            except Exception:
                break

        return samples

    @staticmethod
    def _clean_number(token: str) -> Optional[str]:
        if token is None:
            return None
        cleaned = token.strip().replace(",", "")
        cleaned = cleaned.replace("$", "").strip()
        if not cleaned:
            return None
        cleaned = cleaned.rstrip(".")
        return cleaned

    @classmethod
    def _extract_answer(cls, text: str) -> Optional[str]:
        if not text:
            return None
        if isinstance(text, (list, tuple)):
            text = "\n".join(str(t) for t in text)
        text = str(text)

        patterns = [
            r"####\s*\$?(-?[\d,]+(?:\.\d+)?)",
            r"(?:final\s+answer|answer)\s*(?:is|:|=)\s*\$?(-?[\d,]+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            if matches:
                return cls._clean_number(matches[-1])

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in reversed(lines):
            if re.fullmatch(r"\$?-?[\d,]+(?:\.\d+)?\.?", line):
                return cls._clean_number(line)
            if re.search(r"(?:answer|####)", line, flags=re.IGNORECASE):
                nums = re.findall(r"-?[\d,]+(?:\.\d+)?", line)
                if nums:
                    return cls._clean_number(nums[-1])

        for line in reversed(lines):
            nums = re.findall(r"-?[\d,]+(?:\.\d+)?", line)
            if nums:
                return cls._clean_number(nums[-1])

        return None