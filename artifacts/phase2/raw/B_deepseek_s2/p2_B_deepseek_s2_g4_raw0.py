"""Generate multiple SQL candidates, execute them, and select the one that executes successfully with the most rows."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query to answer the question. Output only SQL."
        )

        # Draw multiple candidate completions with a non-zero temperature.
        responses = self.llm(prompt, temperature=0.7, n=4)
        if isinstance(responses, str):
            response_list = [responses]
        else:
            try:
                response_list = list(responses)
            except TypeError:
                response_list = [str(responses)]

        # If the backend ignored n>1, obtain additional samples via repeated calls.
        extra_attempts = 0
        while len(response_list) < 4 and extra_attempts < 4:
            extra = self.llm(prompt, temperature=0.7, n=1)
            if isinstance(extra, list):
                response_list.extend(extra)
            else:
                response_list.append(extra)
            extra_attempts += 1

        candidates = []
        for response in response_list:
            sql = bridge.extract_sql(str(response))
            if sql:
                candidates.append(sql)

        # Fallback to a single greedy call if no SQL was extracted.
        if not candidates:
            fallback = self.llm(prompt, temperature=0.0, n=1)
            if isinstance(fallback, list):
                fallback = fallback[0] if fallback else ""
            return bridge.extract_sql(str(fallback))

        scored = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception:
                result = {"ok": False, "rows": [], "error": "exception"}

            if result.get("ok"):
                rows = result.get("rows") or []
                # Reward successful execution and non-empty result sets.
                score = 1 + min(len(rows), 10)
            else:
                score = 0

            scored.append((score, sql))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]