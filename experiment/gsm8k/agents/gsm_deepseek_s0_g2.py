"""Uses two independently prompted candidate solutions and, when their final answers disagree, a third verification pass to choose or reconcile the final answer."""
import re
from typing import Any, List, Optional

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G2(MathHarness):
    def solve(self, question: str) -> str:
        # Generate two independent candidate solutions with different prompts.
        prompts = [
            self._prompt_standard(question),
            self._prompt_alternative(question),
        ]

        candidate_texts: List[str] = []
        candidate_answers: List[Optional[str]] = []

        for index, prompt in enumerate(prompts):
            # First pass is greedy; second pass is sampled at a higher temperature.
            temperature = 0.0 if index == 0 else 0.7
            text = self._call_llm(prompt, temperature=temperature)
            candidate_texts.append(text)
            candidate_answers.append(self._extract_final(text))

        answer_a, answer_b = candidate_answers

        # If both candidates produce the same answer, return it directly.
        if (
            answer_a is not None
            and answer_b is not None
            and self._normalize(answer_a) == self._normalize(answer_b)
        ):
            return answer_a

        # If only one candidate produced a parseable answer, return that one.
        if answer_a is not None and answer_b is None:
            return answer_a
        if answer_a is None and answer_b is not None:
            return answer_b

        # If neither candidate yielded a parseable answer, use a fallback direct ask.
        if answer_a is None and answer_b is None:
            fallback_text = self._call_llm(
                self._prompt_fallback(question), temperature=0.0
            )
            fallback_answer = self._extract_final(fallback_text)
            if fallback_answer is not None:
                return fallback_answer
            return self._last_line(fallback_text)

        # Candidate answers differ; ask a verification pass to choose/reconcile.
        verification_text = self._call_llm(
            self._prompt_verify(
                question,
                candidate_texts[0],
                answer_a,
                candidate_texts[1],
                answer_b,
            ),
            temperature=0.0,
        )
        verified_answer = self._extract_final(verification_text)
        return verified_answer if verified_answer is not None else answer_a

    def _call_llm(self, prompt: str, temperature: float) -> str:
        response = self.llm(prompt, system="", temperature=temperature, n=1)
        return self._response_to_text(response)

    def _response_to_text(self, response: Any) -> str:
        if isinstance(response, str):
            return response

        if isinstance(response, list):
            if not response:
                return ""
            first = response[0]
            return self._response_to_text(first)

        if isinstance(response, dict):
            for key in ("text", "content", "message", "output"):
                if key in response:
                    return str(response[key])
            return str(response)

        # Fallback for object-like API responses.
        if hasattr(response, "text"):
            return str(getattr(response, "text"))
        if hasattr(response, "content"):
            return str(getattr(response, "content"))

        return str(response)

    def _extract_final(self, text: str) -> Optional[str]:
        if not text:
            return None

        matches = re.findall(r"(?m)^\s*####\s*(.+?)\s*$", text)
        if not matches:
            return None

        return matches[-1].strip()

    def _normalize(self, answer: str) -> str:
        return (
            re.sub(r"\s+", "", answer)
            .replace("\\frac", "frac")
            .replace("{", "")
            .replace("}", "")
            .lower()
        )

    def _last_line(self, text: str) -> str:
        if not text:
            return ""
        lines = text.strip().splitlines()
        return lines[-1].strip() if lines else ""

    def _prompt_standard(self, question: str) -> str:
        return (
            "Solve the following competition-math problem. Show your work "
            "step by step. Put the final answer on the last line in the exact "
            "form '#### <answer>'.\n\n"
            f"Problem:\n{question}\n"
        )

    def _prompt_alternative(self, question: str) -> str:
        return (
            "Solve the following competition-math problem by first identifying "
            "the relevant mathematical topic and formulas, then carefully "
            "checking your calculations. Put the final answer on the last line "
            "in the exact form '#### <answer>'.\n\n"
            f"Problem:\n{question}\n"
        )

    def _prompt_fallback(self, question: str) -> str:
        return (
            "Solve this competition-math problem and output only the final "
            "answer line in the form '#### <answer>'.\n\n"
            f"Problem:\n{question}\n"
        )

    def _prompt_verify(
        self,
        question: str,
        text_a: str,
        answer_a: str,
        text_b: str,
        answer_b: str,
    ) -> str:
        return (
            "A problem was solved in two different ways, producing different "
            "final answers. Review both solutions and select the correct final "
            "answer. You may reconcile the two solutions if needed. End with "
            "the final answer on the last line in the exact form "
            "'#### <answer>'.\n\n"
            f"Problem:\n{question}\n\n"
            f"Solution A:\n{text_a}\n\n"
            f"Solution B:\n{text_b}\n\n"
            f"Candidate final answer A: {answer_a}\n"
            f"Candidate final answer B: {answer_b}\n\n"
            "Decide the correct final answer and write only the final answer "
            "line."
        )