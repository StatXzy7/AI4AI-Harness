from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    SYSTEM_PROMPT = (
        "You are a careful SQL engineer. Always return exactly one SQL query "
        "without markdown fences or extra explanation."
    )

    def solve(self, question: str) -> str:
        # Generate multiple candidate SQL queries.
        candidates = []
        hints = [
            "Write a straightforward SELECT query that answers the question.",
            "Write a different query structure, such as using a JOIN, subquery, or aggregation.",
            "Write a robust alternative query that answers the question.",
        ]

        for i in range(3):
            hint = hints[i] if i < len(hints) else ""
            prompt = self._candidate_prompt(question, hint)
            raw = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=0.3,
                n=1,
            )
            extracted = bridge.extract_sql(raw)
            sql = extracted if extracted else raw.strip()
            candidates.append(sql)

        # Sort candidates so the final result does not depend on generation order.
        candidates = sorted(candidates)

        # Execute every candidate query and collect outcomes.
        exec_results = []
        for sql in candidates:
            result = self.execute(sql)
            exec_results.append({"sql": sql, "result": result})

        # Branch based on whether at least one query executed cleanly.
        if any(item["result"].get("ok", False) for item in exec_results):
            prompt = self._selection_prompt(question, exec_results)
        else:
            prompt = self._repair_prompt(question, exec_results)

        final_raw = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=0.0,
            n=1,
        )

        final_sql = bridge.extract_sql(final_raw)
        return final_sql

    def _candidate_prompt(self, question: str, hint: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"{hint}\n"
            "Return only the SQL query without code fences or explanation."
        )

    def _selection_prompt(self, question: str, exec_results: list) -> str:
        lines = [
            "You are given candidate SQL queries and their execution results.",
            "Choose the candidate that best answers the question and is correct.",
            "If none is completely correct, write a corrected SQL query.",
            "",
            f"Database schema:\n{self.schema}",
            "",
            f"Question:\n{question}",
            "",
            "Candidates:",
        ]

        for idx, item in enumerate(exec_results, 1):
            sql = item["sql"]
            result = item["result"]

            if result.get("ok", False):
                status = "OK"
                rows = result.get("rows", [])
                detail = "Rows: " + repr(rows[:10])
            else:
                status = "ERROR"
                detail = result.get("error", "Unknown error")

            lines.append(
                f"{idx}. SQL: {sql}\n"
                f"   Status: {status}\n"
                f"   {detail}"
            )

        lines.append("Return only the SQL query without code fences or explanation.")
        return "\n\n".join(lines)

    def _repair_prompt(self, question: str, exec_results: list) -> str:
        lines = [
            "All candidate SQL queries failed to execute.",
            "Use the schema, question, and error messages to write a corrected SQL query.",
            "",
            f"Database schema:\n{self.schema}",
            "",
            f"Question:\n{question}",
            "",
            "Failed candidates:",
        ]

        for idx, item in enumerate(exec_results, 1):
            sql = item["sql"]
            result = item["result"]
            error = result.get("error", "Unknown error")
            lines.append(f"{idx}. SQL: {sql}\n   Error: {error}")

        lines.append("Return only the SQL query without code fences or explanation.")
        return "\n\n".join(lines)