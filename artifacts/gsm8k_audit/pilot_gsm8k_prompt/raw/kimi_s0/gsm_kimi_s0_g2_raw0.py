"""Self-consistency with majority voting and meta-verification for GSM8K math word problems."""
from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmKimiS0G2(MathHarness):
    def solve(self, question: str) -> str:
        n_samples = 5

        # Step 1: Generate multiple diverse reasoning paths via self-consistency
        cot_prompt = (
            "Solve the following grade-school math word problem step by step. "
            "Show your work clearly, then write the final answer on a line that "
            "starts with '#### ' followed by just the number.\n\n"
            f"Question: {question}\n\n"
            "Solution:"
        )

        responses = []
        for _ in range(n_samples):
            resp = self.llm(cot_prompt, system="", temperature=0.7, n=1)
            if resp:
                responses.append(resp)

        if not responses:
            return "0"

        # Step 2: Extract and normalise answers from each reasoning path
        answers = []
        for resp in responses:
            ans = self._extract_answer(resp)
            if ans is not None:
                answers.append(ans)

        if not answers:
            return "0"

        # Step 3: Majority vote -- if a clear winner exists, return it
        counter = Counter(answers)
        top_answer, top_count = counter.most_common(1)[0]
        if top_count >= 3:
            return top_answer

        # Step 4: Meta-verification -- no clear majority, so ask the model to
        # review all candidate solutions and pick the correct one
        all_solutions = "\n\n".join(
            f"--- Solution {i + 1} ---\n{resp}"
            for i, resp in enumerate(responses)
        )

        meta_prompt = (
            f"Question: {question}\n\n"
            f"I have {len(responses)} different solution attempts:\n\n"
            f"{all_solutions}\n\n"
            "Review all solutions carefully. Identify which solution is correct "
            "and what the right final answer is. Respond with ONLY the numerical "
            "answer, nothing else."
        )

        meta_response = self.llm(meta_prompt, system="", temperature=0.0, n=1)
        meta_answer = self._extract_answer(meta_response)

        if meta_answer is not None:
            return meta_answer

        # Fallback: return the plurality answer even without a strong majority
        return top_answer

    def _extract_answer(self, text: str) -> str | None:
        """Extract the final numerical answer from a response string."""
        if not text:
            return None

        # Primary: "#### <number>" pattern
        match = re.search(r"####\s*([+-]?\d+(?:\.\d+)?)", text)
        if match:
            return self._normalize_number(match.group(1))

        # Secondary: "the answer is <number>" / "final answer: <number>" patterns
        match = re.search(
            r"(?:the\s+)?(?:final\s+)?answer\s*(?:is|:)\s*([+-]?\d+(?:\.\d+)?)",
            text,
            re.IGNORECASE,
        )
        if match:
            return self._normalize_number(match.group(1))

        # Tertiary: last number appearing in the text
        numbers = re.findall(r"[+-]?\d+(?:\.\d+)?", text)
        if numbers:
            return self._normalize_number(numbers[-1])

        return None

    def _normalize_number(self, num_str: str) -> str:
        """Normalise a number string so that equivalent answers compare equal."""
        try:
            val = float(num_str)
            if val == int(val):
                return str(int(val))
            return str(val)
        except ValueError:
            return num_str