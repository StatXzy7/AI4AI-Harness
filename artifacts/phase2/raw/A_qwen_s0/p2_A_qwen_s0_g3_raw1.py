"""Generate an initial SQL query, execute it, and iteratively repair it using execution errors."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert Text-to-SQL system. Produce exactly one valid SQL query "
            "that answers the user's question for the given schema. Return only SQL."
        )

        attempts = []
        last_candidate = ""

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = (
                    "Schema:\n"
                    f"{schema}\n\n"
                    "Question:\n"
                    f"{question}\n\n"
                    "Write one SQL query that answers the question. Return only SQL."
                )
            else:
                attempt_lines = []
                for i, (sql, error) in enumerate(attempts, start=1):
                    attempt_lines.append(f"{i}. SQL:\n{sql}\n   Error:\n{error}")

                prompt = (
                    "Schema:\n"
                    f"{schema}\n\n"
                    "Question:\n"
                    f"{question}\n\n"
                    "Previous attempts failed:\n"
                    + "\n\n".join(attempt_lines)
                    + "\n\n"
                    "Write corrected SQL that fixes the error and still answers the question. "
                    "Return only SQL."
                )

            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

            if sql:
                candidate = sql.strip()
                last_candidate = candidate

                try:
                    result = self.execute(candidate)
                except Exception as exc:
                    attempts.append((candidate, f"Execution exception: {exc}"))
                    continue

                if isinstance(result, dict) and result.get("ok"):
                    return candidate

                if isinstance(result, dict):
                    error = str(result.get("error") or "Execution failed.")
                else:
                    error = str(result)

                attempts.append((candidate, error))
            else:
                candidate = str(raw or "").strip()
                last_candidate = candidate
                attempts.append((candidate, "No SQL could be extracted from the model response."))

        return last_candidate