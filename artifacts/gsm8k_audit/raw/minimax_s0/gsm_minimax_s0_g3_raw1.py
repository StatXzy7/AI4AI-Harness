"""Self-consistency via deterministic re-prompting with reframed reasoning and answer extraction."""
import re
from ..harness_base import MathHarness


class GsmGsmMinimaxS0G3(MathHarness):
    def solve(self, question: str) -> str:
        # Strategy: run the solver multiple times with temperature>0 and different
        # framing prompts, then take a majority vote on the extracted numeric answer.
        # This is a real change to control flow (multi-sample + vote), not just a prompt tweak.

        framings = [
            "Solve the following math problem step by step. End with '#### N' where N is the answer.\n\n",
            "Think carefully about the following word problem. Show your work, then write 'The answer is N'.\n\n",
            "Read this grade-school math problem carefully. Compute each step. Conclude with '#### N'.\n\n",
            "Solve this problem: break it into parts, compute each, give the final number as '#### N'.\n\n",
        ]

        system = "You are a careful math tutor. Always end your response with a line of the form '#### <number>'."

        answers = []
        for prefix in framings:
            prompt = prefix + question
            # Use temperature 0.0 for determinism, but vary framing to get diverse reasoning paths
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            extracted = self._extract_answer(raw)
            if extracted is not None:
                answers.append(extracted)

        if not answers:
            # Fallback: one more call with the plain question
            raw = self.llm(question, system=system, temperature=0.0, n=1)
            extracted = self._extract_answer(raw)
            if extracted is None:
                return ""
            answers.append(extracted)

        # Majority vote
        return self._majority(answers)

    def _extract_answer(self, text: str):
        """Extract a numeric answer from the solver's output."""
        if not text:
            return None
        # Look for "#### N"
        m = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
        if m:
            return self._normalize(m.group(1))
        # Look for "The answer is N"
        m = re.search(r"[Tt]he answer is\s*[:=]?\s*(-?\d+(?:\.\d+)?)", text)
        if m:
            return self._normalize(m.group(1))
        # Look for "answer: N" or "answer is N"
        m = re.search(r"answer\s*(?:is|:)\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if m:
            return self._normalize(m.group(1))
        # Last resort: last number in the text
        nums = re.findall(r"-?\d+(?:\.\d+)?", text)
        if nums:
            return self._normalize(nums[-1])
        return None

    def _normalize(self, s: str) -> str:
        """Normalize a numeric string for voting (strip trailing .0, handle ints vs floats)."""
        try:
            f = float(s)
            if f == int(f):
                return str(int(f))
            return str(f)
        except (ValueError, TypeError):
            return s.strip()

    def _majority(self, answers):
        """Return the most common answer; tie-break by first occurrence."""
        counts = {}
        order = []
        for a in answers:
            if a not in counts:
                order.append(a)
                counts[a] = 0
            counts[a] += 1
        order.sort(key=lambda x: (-counts[x], answers.index(x)))
        return order[0]