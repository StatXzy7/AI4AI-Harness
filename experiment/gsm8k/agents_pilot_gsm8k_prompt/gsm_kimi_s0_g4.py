"""Self-consistency sampling with majority voting and meta-reasoning adjudication for GSM8K math word problems."""

from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmKimiS0G4(MathHarness):
    def solve(self, question: str) -> str:
        # Phase 1: Generate diverse reasoning paths via temperature sampling
        num_samples = 8
        prompt = self._build_prompt(question)
        responses = []
        for _ in range(num_samples):
            resp = self.llm(prompt, system="", temperature=0.7, n=1)
            if isinstance(resp, list):
                resp = resp[0] if resp else ""
            responses.append(resp)

        # Phase 2: Extract candidate answers from each response
        answer_pairs = []  # (answer_string, full_response)
        for resp in responses:
            ans = self._extract_answer(resp)
            if ans is not None:
                answer_pairs.append((ans, resp))

        # Fallback if no answers could be extracted at all
        if not answer_pairs:
            greedy = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(greedy, list):
                greedy = greedy[0] if greedy else ""
            return self._extract_answer(greedy) or "0"

        # Phase 3: Majority vote across all extracted answers
        answers = [a for a, _ in answer_pairs]
        counts = Counter(answers)
        top_answer, top_count = counts.most_common(1)[0]

        # Clear majority threshold (>= 3 out of 8 agrees)
        if top_count >= 3:
            return top_answer

        # Phase 4: No clear majority — adjudicate via meta-reasoning
        return self._adjudicate(question, answer_pairs)

    def _build_prompt(self, question: str) -> str:
        return (
            "Solve the following grade-school math problem step by step. "
            "Show all your work and reasoning clearly. "
            "End your solution with the final answer after '#### '.\n\n"
            f"Question: {question}\n\n"
            "Solution:\n"
        )

    def _extract_answer(self, text: str):
        """Extract the final numerical answer from solver output."""
        if not text:
            return None

        # Pattern 1: GSM8K standard "#### number"
        match = re.search(r'####\s*([-\d,\.]+)', text)
        if match:
            return self._normalize(match.group(1))

        # Pattern 2: "The answer is X" / "Therefore, X" / "Final answer: X"
        match = re.search(
            r'(?:the\s+answer\s+is|therefore[,]?\s|so\s+the\s+answer|final\s+answer\s*[:=])\s*([-\d,\.]+)',
            text, re.IGNORECASE
        )
        if match:
            return self._normalize(match.group(1))

        # Pattern 3: Last number appearing in the text
        numbers = re.findall(r'[-]?\d[\d,\.]*', text)
        if numbers:
            return self._normalize(numbers[-1])

        return None

    def _normalize(self, num_str: str):
        """Normalize a number string by removing commas and validating."""
        if not num_str:
            return None
        cleaned = num_str.replace(',', '').strip().rstrip('.')
        try:
            float(cleaned)
            return cleaned
        except ValueError:
            return None

    def _adjudicate(self, question: str, answer_pairs: list) -> str:
        """When no majority exists, present all attempts and ask the model to pick the best."""
        summary_parts = []
        for i, (ans, resp) in enumerate(answer_pairs[:5]):
            summary_parts.append(f"--- Attempt {i+1} (answer: {ans}) ---\n{resp}")
        summary = "\n\n".join(summary_parts)

        adjudicate_prompt = (
            f"Question: {question}\n\n"
            f"Several solution attempts were made:\n{summary}\n\n"
            f"Based on the reasoning shown, what is the correct numerical answer? "
            f"Respond with ONLY the number, nothing else."
        )

        result = self.llm(adjudicate_prompt, system="", temperature=0.0, n=1)
        if isinstance(result, list):
            result = result[0] if result else ""
        adjudicated = self._extract_answer(result)

        # If adjudication fails, fall back to the plurality answer
        if adjudicated is None:
            answers = [a for a, _ in answer_pairs]
            adjudicated = Counter(answers).most_common(1)[0][0]

        return adjudicated