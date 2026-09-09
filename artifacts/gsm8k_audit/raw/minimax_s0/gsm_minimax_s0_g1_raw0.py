"""Self-consistency with answer normalization: sample multiple greedy-decoded reasoning paths and return the majority final answer."""
import re
from collections import Counter
from ..harness_base import MathHarness


class GsmGsmMinimaxS0G1(MathHarness):
    # Patterns that capture the final numeric answer from a GSM8K-style reply.
    _ANSWER_PATTERNS = [
        re.compile(r"####\s*([-+]?\d+(?:[,]\d{3})*(?:\.\d+)?)"),
        re.compile(r"[Tt]he answer is\s*[:=]?\s*([-+]?\d+(?:[,]\d{3})*(?:\.\d+)?)"),
        re.compile(r"[Aa]nswer\s*[:=]\s*([-+]?\d+(?:[,]\d{3})*(?:\.\d+)?)"),
        re.compile(r"=\s*([-+]?\d+(?:[,]\d{3})*(?:\.\d+)?)\s*\.?\s*$"),
        re.compile(r"([-+]?\d+(?:[,]\d{3})*(?:\.\d+)?)\s*(?:dollars|cents|miles|hours|minutes|seconds|feet|inches|yards|meters|cm|kg|lbs|years|months|weeks|days|oranges|apples|cars|books|pens|cookies|candies|toys|balls|chickens|rabbits|dogs|cats|birds|fish|cups|bowls|plates|glasses|bottles|cans|boxes|bags|pairs|pieces|units|items|students|people|kids|children|boys|girls|men|women|workers|friends|siblings|brothers|sisters|tickets|games|movies|songs|problems|questions|points|percent|%|times|x)\b"),
    ]

    def _extract_final_number(self, text: str) -> str | None:
        """Pull the final numeric answer out of a raw model reply."""
        if not text:
            return None
        # Prefer the last explicit "answer" marker.
        for pattern in self._ANSWER_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                raw = matches[-1].replace(",", "")
                try:
                    # Normalize to a canonical string so 42, 42.0, +42 all agree.
                    value = float(raw)
                    if value.is_integer():
                        return str(int(value))
                    return str(value).rstrip("0").rstrip(".")
                except ValueError:
                    continue
        # Fallback: last standalone number anywhere in the text.
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
        if not nums:
            return None
        raw = nums[-1]
        try:
            value = float(raw)
            if value.is_integer():
                return str(int(value))
            return str(value).rstrip("0").rstrip(".")
        except ValueError:
            return None

    def solve(self, question: str) -> str:
        # Self-consistency with low-temperature sampling: take several
        # independent reasoning traces and majority-vote their final answers.
        n_samples = 5
        system_prompt = (
            "You are a careful grade-school math tutor. "
            "Read the problem, reason step by step, and finish with a line "
            "of the form '#### <number>' containing only the final answer."
        )
        votes: Counter[str] = Counter()
        last_valid_answer: str | None = None

        for _ in range(n_samples):
            reply = self.llm(question, system=system_prompt, temperature=0.4, n=1)
            answer = self._extract_final_number(reply)
            if answer is None:
                # Fallback: try a greedy, marker-free second pass.
                retry = self.llm(
                    question + "\nReply with only the final number.",
                    system=system_prompt,
                    temperature=0.0,
                    n=1,
                )
                answer = self._extract_final_number(retry)
            if answer is not None:
                votes[answer] += 1
                last_valid_answer = answer

        if not votes:
            # Could not parse any answer; return an empty string rather than
            # fabricating one.
            return ""

        # Pick the majority; tie-break by the most recent valid answer.
        top_count = max(votes.values())
        winners = [ans for ans, c in votes.items() if c == top_count]
        if len(winners) == 1:
            return winners[0]
        return last_valid_answer if last_valid_answer in winners else winners[0]