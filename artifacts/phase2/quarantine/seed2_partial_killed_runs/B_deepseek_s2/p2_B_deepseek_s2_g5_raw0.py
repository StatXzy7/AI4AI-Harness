"""Generate a SQL query, execute it, and repair failures by feeding execution errors back to the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G5(SQLHarness):
    """Text-to-SQL harness that repairs failing SQL using execution feedback."""

    @staticmethod
    def _coerce_response_text(response):
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            if not response:
                return ""
            return P2P2BDeepseekS2G5._coerce_response_text(response[0])
        if isinstance(response, dict):
            if "choices" in response:
                return P2P2BDeepseekS2G5._coerce_response_text(response["choices"])
            for key in ("text", "content", "message", "output", "completion"):
                if key in response:
                    return P2P2BDeepseekS2G5._coerce_response_text(response[key])
            return str(response)
        if hasattr(response, "text"):
            return P2P2BDeepseekS2G5._coerce_response_text(response.text)
        if hasattr(response, "content"):
            return P2P2BDeepseekS2G5._coerce_response_text(response.content)
        if hasattr(response, "message"):
            return P2P2BDeepseekS2G5._coerce_response_text(response.message)
        return str(response)

    def solve(self, question: str) -> str:
        schema = self.schema
        system = "You are an expert SQL engineer. Output only SQL."

        initial_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. Output only the SQL."
        )

        raw = self.llm(initial_prompt, system=system, temperature=0.0, n=1)
        raw_text = self._coerce_response_text(raw)
        sql = bridge.extract_sql(raw_text) or raw_text.strip()

        for _ in range(3):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error_msg = result.get("error") or "Unknown execution error"
            repair_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL query produced an execution error:\n"
                f"SQL:\n{sql}\n\n"
                f"Error:\n{error_msg}\n\n"
                "Fix the SQL query so it executes successfully and answers the question. "
                "Output only the corrected SQL."
            )

            raw = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            raw_text = self._coerce_response_text(raw)
            new_sql = bridge.extract_sql(raw_text) or raw_text.strip()
            if new_sql:
                sql = new_sql.strip()

        return sql