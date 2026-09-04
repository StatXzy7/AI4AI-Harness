"""Generate SQL, execute it, and repair up to two times using the exact SQLite error."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS0Repair(SQLHarness):
    """Generate SQL, execute it, and repair up to two times using SQLite errors."""

    def solve(self, question: str) -> str:
        max_repairs = 2
        last_sql = ""
        last_error = ""
        system = (
            "You are an expert SQLite Text-to-SQL system. "
            "Return only one valid SQL statement."
        )

        def _llm_text(response):
            if response is None:
                return ""

            if isinstance(response, list):
                if not response:
                    return ""
                response = response[0]

            if isinstance(response, dict):
                if "text" in response:
                    return str(response.get("text") or "")
                if "content" in response:
                    return str(response.get("content") or "")

                choices = response.get("choices")
                if isinstance(choices, list) and choices:
                    choice = choices[0]
                    if isinstance(choice, dict):
                        message = choice.get("message")
                        if isinstance(message, dict):
                            return str(message.get("content") or "")
                        return str(choice.get("text") or choice.get("content") or "")

                return ""

            choices = getattr(response, "choices", None)
            if choices:
                choice = choices[0]
                message = getattr(choice, "message", None)
                if message is not None:
                    return str(getattr(message, "content", "") or "")
                return str(getattr(choice, "text", "") or "")

            text = getattr(response, "text", None)
            if text is not None:
                return str(text)

            content = getattr(response, "content", None)
            if content is not None:
                return str(content)

            return str(response)

        def _extract_sql(text: str) -> str:
            try:
                extracted = bridge.extract_sql(text)
            except Exception:
                extracted = None

            if isinstance(extracted, list):
                extracted = extracted[0] if extracted else None

            if extracted is None:
                extracted = ""

            extracted = str(extracted).strip()
            return extracted or text.strip()

        def _initial_prompt() -> str:
            return (
                "Generate a single valid SQLite SQL statement that answers the question.\n"
                "Output SQL only, with no explanation and no markdown.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n"
            )

        def _repair_prompt(sql: str, error: str) -> str:
            return (
                "The previous SQL failed. Fix it so that it executes correctly.\n"
                "Output SQL only, with no explanation and no markdown.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Exact SQLite error:\n{error}\n"
            )

        for attempt in range(max_repairs + 1):
            if attempt == 0:
                prompt = _initial_prompt()
            else:
                prompt = _repair_prompt(last_sql, last_error)

            response_text = _llm_text(
                self.llm(
                    prompt,
                    system=system,
                    temperature=0.0,
                    n=1,
                )
            )

            sql = _extract_sql(response_text)
            last_sql = sql or response_text.strip()

            if not last_sql:
                last_error = "No SQL was produced."
                continue

            try:
                result = self.execute(last_sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                return last_sql

            if isinstance(result, dict):
                last_error = str(result.get("error") or "unknown SQLite error")
            else:
                last_error = "unknown SQLite error"

        return last_sql or "SELECT NULL;"