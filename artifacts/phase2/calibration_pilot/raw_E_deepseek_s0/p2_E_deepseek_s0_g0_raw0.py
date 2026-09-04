from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        candidates = []

        for _ in range(3):
            response_text = self._llm_text(
                self._candidate_prompt(question), temperature=0.3
            )
            sql = self._as_sql(response_text)

            try:
                result = self.execute(sql)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "rows": [], "error": str(exc)}

            candidates.append(self._record(sql, result))

        successful = sorted(
            [c for c in candidates if c["ok"]], key=lambda c: c["sql"]
        )
        failed = sorted(
            [c for c in candidates if not c["ok"]], key=lambda c: c["sql"]
        )

        if successful:
            final_prompt = self._prompt_with_successes(question, successful, failed)
        else:
            final_prompt = self._prompt_with_failures(question, failed)

        final_response = self._llm_text(final_prompt, temperature=0.2)
        return self._as_sql(final_response)

    def _candidate_prompt(self, question: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. "
            "Return only the SQL query."
        )

    def _prompt_with_successes(self, question, successful, failed):
        lines = [
            "Given the following database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "The following SQL candidates executed successfully:",
            "",
        ]

        for i, candidate in enumerate(successful, 1):
            lines.append(
                f"{i}. {candidate['sql']} "
                f"(rows returned: {candidate['row_count']})"
            )

        if failed:
            lines.append("")
            lines.append("The following candidates failed:")
            lines.append("")
            for i, candidate in enumerate(failed, 1):
                lines.append(
                    f"{i}. {candidate['sql']} "
                    f"(error: {candidate['error']})"
                )

        lines.append("")
        lines.append(
            "Using the execution results above, write the best SQL query "
            "to answer the question. Return only SQL."
        )

        return "\n".join(lines)

    def _prompt_with_failures(self, question, failed):
        lines = [
            "Given the following database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "The following SQL candidates all failed:",
            "",
        ]

        for i, candidate in enumerate(failed, 1):
            lines.append(
                f"{i}. {candidate['sql']} "
                f"(error: {candidate['error']})"
            )

        lines.append("")
        lines.append(
            "Write a corrected SQL query for the question. Return only SQL."
        )

        return "\n".join(lines)

    def _llm_text(self, prompt: str, temperature: float) -> str:
        response = self.llm(prompt, system="", temperature=temperature, n=1)

        if isinstance(response, list):
            return response[0] if response else ""

        return response

    @staticmethod
    def _as_sql(text: str) -> str:
        sql = bridge.extract_sql(text)
        if not sql:
            sql = text.strip()
        return sql

    @staticmethod
    def _record(sql: str, result) -> dict:
        if not isinstance(result, dict):
            result = {}

        rows = result.get("rows", []) or []

        return {
            "sql": sql,
            "ok": bool(result.get("ok")),
            "error": str(result.get("error") or ""),
            "row_count": len(rows),
        }