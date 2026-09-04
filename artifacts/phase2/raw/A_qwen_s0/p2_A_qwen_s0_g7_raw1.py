"""Sample multiple SQL candidates and choose the best one using execution results."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G7(SQLHarness):
    SAMPLE_COUNT = 3
    SYSTEM_PROMPT = (
        "You are an expert SQL engineer. Output only one executable SQL query. "
        "No explanation, no markdown."
    )

    def _as_text(self, response):
        if response is None:
            return ""
        if isinstance(response, list):
            if not response:
                return ""
            return self._as_text(response[0])
        if isinstance(response, dict):
            if "choices" in response:
                return self._as_text(response.get("choices"))
            if "message" in response and isinstance(response["message"], dict):
                return str(response["message"].get("content", ""))
            for key in ("text", "content", "completion"):
                if key in response:
                    return str(response[key])
        return str(response)

    def _generate(self, prompt, temperature):
        response = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=temperature,
            n=1,
        )
        return self._as_text(response)

    def _remove_fences(self, text):
        text = (text or "").strip()
        if "