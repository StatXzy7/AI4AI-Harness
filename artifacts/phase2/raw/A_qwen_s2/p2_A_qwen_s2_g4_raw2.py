"""Generate SQL, execute it, and iteratively repair failed attempts using execution errors."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G4(SQLHarness):
    MAX_ATTEMPTS = 4
    ERROR_SNIPPET_LEN = 600

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert SQL assistant. "
            "Return only one SQL statement. "
            "Do not include explanations, markdown fences, or comments."
        )

        last_sql = ""
        last_error = ""

        for attempt in range(self.MAX_ATTEMPTS):
            if attempt == 0:
                prompt = self._initial_prompt(question, schema)
            else:
                prompt = self._repair_prompt(question, schema, last_sql, last_error)

            raw = self._llm_text(prompt, system)
            sql = self._extract_sql(raw)

            if not sql and isinstance(raw, str) and raw.strip():
                sql = self._clean_sql(raw)

            if sql:
                last_sql = sql
            else:
                last_error = "No SQL statement was produced."
                continue

            result = self._execute_sql(last_sql)
            if result.get("ok"):
                return last_sql

            last_error = self._error_text(result)

        return last_sql

    def _initial_prompt(self, question: str, schema: str) -> str:
        return (
            "Write one SQL statement that answers the question using only the provided schema.\n"
            "Output only SQL, no explanation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:\n"
        )

    def _repair_prompt(self, question: str, schema: str, sql: str, error: str) -> str:
        previous = sql if sql else "(no SQL was produced)"
        return (
            "The previous SQL attempt failed. Revise it so it executes correctly and answers the question.\n"
            "Output only the corrected SQL statement, no explanation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Previous SQL:\n{previous}\n\n"
            f"Execution error:\n{error}\n\n"
            "Corrected SQL:\n"
        )

    def _llm_text(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if response is None:
            return ""

        if isinstance(response, list):
            if not response:
                return ""
            return self._llm_payload_to_text(response[0])

        return self._llm_payload_to_text(response)

    def _llm_payload_to_text(self, payload) -> str:
        if payload is None:
            return ""

        if isinstance(payload, str):
            return payload

        if isinstance(payload, bytes):
            return payload.decode("utf-8", "ignore")

        if isinstance(payload, list):
            parts = [self._llm_payload_to_text(item) for item in payload]
            return "\n".join(part for part in parts if part)

        if isinstance(payload, dict):
            for key in ("text", "completion", "content", "output", "sql"):
                if key in payload:
                    return self._llm_payload_to_text(payload[key])

            if "choices" in payload:
                choices = payload["choices"]
                if isinstance(choices, list) and choices:
                    return self._llm_payload_to_text(choices[0])

            if "message" in payload:
                return self._llm_payload_to_text(payload["message"])

            if "error" in payload:
                return ""

        return str(payload)

    def _extract_sql(self, text) -> str:
        if not isinstance(text, str):
            text = str(text or "")

        extracted = ""
        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if isinstance(extracted, list):
            extracted = extracted[0] if extracted else ""

        if isinstance(extracted, str) and extracted.strip():
            return self._clean_sql(extracted)

        return self._clean_sql(self._fallback_extract(text))

    def _fallback_extract(self, text: str) -> str:
        txt = text.strip()
        if not txt:
            return ""

        if "