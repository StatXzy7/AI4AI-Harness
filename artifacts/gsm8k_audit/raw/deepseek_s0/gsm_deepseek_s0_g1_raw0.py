"""Sample several high-temperature solution paths and return the most common final numeric answer, using greedy as tie-break."""

from collections import Counter
from decimal import Decimal, InvalidOperation
import re

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G1(MathHarness):
    """Grade-school math harness that uses self-consistency over multiple sampled solutions."""

    def solve(self, question: str) -> str:
        system = "You are a careful math tutor. Solve word problems step by step and end with exactly '#### <number>'."
        prompt = (
            "Solve the following grade-school math word problem.\n"
            "Explain your reasoning step by step, and end your response with the final answer "
            "in the format '#### <number>'.\n\n"
            f"Question: {question}\n"
        )

        # Generate a single greedy answer to use as a stable tie-break/fallback.
        greedy_text = self._first(self._call_llm(prompt, system=system, temperature=0.0, n=1))

        # Generate diverse samples for majority voting.
        sampled_texts = []
        for _ in range(5):
            sampled_texts.extend(self._call_llm(prompt, system=system, temperature=0.7, n=1))

        all_texts = ([greedy_text] if greedy_text else []) + sampled_texts
        numeric_answers = []
        for text in all_texts:
            number = self._extract_final_number(text)
            if number is not None:
                numeric_answers.append(number)

        if numeric_answers:
            counts = Counter(numeric_answers)
            max_count = max(counts.values())
            top = [number for number, count in counts.items() if count == max_count]

            if len(top) == 1:
                return str(top[0])

            # In a tie, prefer the greedy answer if it is among the tied candidates.
            greedy_number = self._extract_final_number(greedy_text) if greedy_text else None
            if greedy_number is not None and greedy_number in top:
                return str(greedy_number)

            return str(numeric_answers[0])

        # Fallback to greedy parse.
        greedy_number = self._extract_final_number(greedy_text) if greedy_text else None
        if greedy_number is not None:
            return str(greedy_number)

        # Last resort: ask directly for the number.
        direct_prompt = (
            "What is the final numeric answer to the following math word problem?\n"
            f"Question: {question}\n"
            "Answer with just the number."
        )
        direct_text = self._first(self._call_llm(direct_prompt, system=system, temperature=0.0, n=1))
        direct_number = self._extract_final_number(direct_text)
        if direct_number is not None:
            return str(direct_number)

        if direct_text:
            match = re.search(r"[-+]?[\d,]+(?:\.\d+)?", direct_text)
            if match:
                return self._clean_number(match.group(0))

        return ""

    def _call_llm(self, prompt, system, temperature=0.0, n=1):
        """Call the frozen solver and always normalize its output to a list of strings."""
        output = self.llm(prompt, system=system, temperature=temperature, n=n)
        if output is None:
            return []
        if isinstance(output, list):
            return [o for o in output if isinstance(o, str)]
        if isinstance(output, tuple):
            return [o for o in output if isinstance(o, str)]
        if isinstance(output, str):
            return [output]
        return [str(output)]

    @staticmethod
    def _first(outputs):
        if not outputs:
            return ""
        first = outputs[0]
        return first if isinstance(first, str) else str(first)

    def _extract_final_number(self, text: str):
        """Extract a final numeric answer from solver text."""
        if not isinstance(text, str) or not text.strip():
            return None
        text = text.strip()

        patterns = [
            r"####\s*\$?([-+]?[\d,]+(?:\.\d+)?)\$?",
            r"\\boxed\s*\{\s*\$?([-+]?[\d,]+(?:\.\d+)?)\s*\$?\}",
            r"answer\s+is\s*:?\s*\$?([-+]?[\d,]+(?:\.\d+)?)",
            r"(?:\$|USD)?\s*([-+]?[\d,]+(?:\.\d+)?)\s*(?:dollars?|cents?)?\.?\s*$",
            r"([-+]?[\d,]+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            if matches:
                return self._clean_number(matches[-1])
        return None

    @staticmethod
    def _clean_number(token: str):
        token = token.strip().replace(",", "").replace("$", "")
        if not token:
            return None
        try:
            value = Decimal(token)
            if value == value.to_integral_value():
                return str(int(value))
            return format(value, "f").rstrip("0").rstrip(".")
        except (InvalidOperation, ValueError):
            return token.rstrip(".")
        except Exception:
            return token.rstrip(".")