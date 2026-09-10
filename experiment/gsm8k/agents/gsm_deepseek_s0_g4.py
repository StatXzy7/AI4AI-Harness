"""Uses four sampled candidate solutions with self-consistency voting and a verification pass on disagreement."""
import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G4(MathHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are a careful competition math solver. Provide a concise step-by-step "
            "solution and put the final answer on the last line as '#### <answer>'. "
            "Do not write anything after that line."
        )
        initial_prompt = (
            f"Solve the following math problem. The last line must be exactly "
            f"'#### <answer>'.\n\nProblem: {question}\n\nSolution:"
        )

        responses = self._call_llm(initial_prompt, system=system, temperature=0.6, n=4)

        valid = []
        for response in responses:
            ans = self._extract_final_answer(response)
            if ans:
                valid.append(ans)

        if not valid:
            fallback = self._call_llm(initial_prompt, system=system, temperature=0.0, n=1)
            if fallback:
                ans = self._extract_final_answer(fallback[0])
                if ans:
                    return self._compact(ans)
            return ""

        normalized = [self._normalize_answer(ans) for ans in valid]
        counts = Counter(normalized)
        most_common, count = counts.most_common(1)[0]

        if len(valid) == 1 or count * 2 > len(valid):
            for ans, norm in zip(valid, normalized):
                if norm == most_common:
                    return self._compact(ans)

        candidates = "\n".join(f"({i + 1}) {ans}" for i, ans in enumerate(valid))
        choose_prompt = (
            f"Problem: {question}\n\n"
            f"Several candidate final answers were proposed:\n{candidates}\n\n"
            "Choose the correct final answer. Explain briefly, then put the final answer "
            "on the last line in the form '#### <answer>'."
        )

        chosen_responses = self._call_llm(choose_prompt, system=system, temperature=0.0, n=1)
        if chosen_responses:
            chosen = self._extract_final_answer(chosen_responses[0])
            if chosen:
                return self._compact(chosen)

        return self._compact(valid[0])

    def _call_llm(self, prompt, system, temperature, n):
        response = self.llm(prompt, system=system, temperature=temperature, n=n)
        if response is None:
            return []
        if isinstance(response, str):
            return [response]
        if isinstance(response, (list, tuple)):
            texts = []
            for item in response:
                if isinstance(item, str):
                    texts.append(item)
                elif hasattr(item, "text"):
                    texts.append(item.text)
                elif hasattr(item, "message") and hasattr(item.message, "content"):
                    texts.append(item.message.content)
                else:
                    texts.append(str(item))
            return texts
        if hasattr(response, "choices"):
            texts = []
            for choice in response.choices:
                if hasattr(choice, "text"):
                    texts.append(choice.text)
                elif hasattr(choice, "message") and hasattr(choice.message, "content"):
                    texts.append(choice.message.content)
                else:
                    texts.append(str(choice))
            return texts
        return [str(response)]

    def _extract_final_answer(self, text: str) -> str:
        if not text:
            return ""
        for line in reversed(text.splitlines()):
            line = line.strip()
            if "####" in line:
                _, _, ans = line.partition("####")
                ans = ans.strip()
                if ans:
                    return ans
        return ""

    def _normalize_answer(self, ans: str) -> str:
        a = ans.strip()
        a = a.replace("\\left", "").replace("\\right", "")
        a = a.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
        return re.sub(r"\s+", "", a)

    def _compact(self, ans: str) -> str:
        a = ans.strip()
        a = re.sub(r"\s+", "", a)
        return a