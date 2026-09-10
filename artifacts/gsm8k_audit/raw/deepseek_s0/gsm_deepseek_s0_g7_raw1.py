"""Draft-and-verify: generate an initial answer, then ask the solver to independently check and correct it before returning the final answer."""
from ..harness_base import MathHarness


class GsmGsmDeepseekS0G7(MathHarness):
    @staticmethod
    def _response_to_text(response):
        if response is None:
            return ""
        if isinstance(response, list):
            return str(response[0]) if response else ""
        if isinstance(response, str):
            return response
        return str(response)

    @staticmethod
    def _clean_answer(answer):
        if not answer:
            return answer
        answer = answer.strip()
        if answer.startswith("$") and answer.endswith("$") and len(answer) > 2:
            answer = answer[1:-1].strip()
        if answer.startswith("\\boxed{") and answer.endswith("}"):
            answer = answer[len("\\boxed{"):-1].strip()
            if answer.startswith("$") and answer.endswith("$") and len(answer) > 2:
                answer = answer[1:-1].strip()
        return answer

    @staticmethod
    def _extract_final_answer(text):
        if not text:
            return None

        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if not lines:
            return None

        # Prefer the last line containing the required delimiter.
        for line in reversed(lines):
            if "####" in line:
                answer = line.split("####", 1)[1].strip()
                if answer:
                    return answer

        # Fallback: use the last non-empty line.
        return lines[-1]

    def solve(self, question: str) -> str:
        first_prompt = (
            "Solve the following competition math problem. "
            "Think carefully and show your work. "
            "Put your final answer on the last line exactly in the form: #### <answer>\n\n"
            f"Problem: {question}"
        )
        first_response = self.llm(
            first_prompt,
            system="",
            temperature=0.0,
            n=1,
        )
        first_text = self._response_to_text(first_response)
        first_answer = self._extract_final_answer(first_text)

        second_prompt = (
            "You are checking a previous answer to the following problem.\n\n"
            f"Problem: {question}\n\n"
            f"Previous answer: {first_answer if first_answer else 'No answer'}\n\n"
            "Solve the problem independently to check that answer. "
            "If your independent answer agrees with the previous answer, repeat that answer. "
            "If it disagrees, provide the correct answer. "
            "Put your final answer on the last line exactly in the form: #### <answer>"
        )
        second_response = self.llm(
            second_prompt,
            system="",
            temperature=0.0,
            n=1,
        )
        second_text = self._response_to_text(second_response)
        second_answer = self._extract_final_answer(second_text)

        final_answer = second_answer or first_answer
        if final_answer is None:
            return ""

        return self._clean_answer(final_answer)