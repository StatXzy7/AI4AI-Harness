from typing import Any, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    """Samples candidate SQL queries, executes them, and uses execution
    outcomes to select or correct the final SQL."""

    def solve(self, question: str) -> str:
        schema = self.schema
        base_prompt = self._build_base_prompt(question, schema)

        # 1. Sample at least two candidate SQL queries.
        raw_candidates = self.llm(
            base_prompt,
            system="You are an expert SQL generator. Return only SQL.",
            temperature=0.0,
            n=2,
        )
        candidate_texts = self._as_list(raw_candidates)

        sqls: List[str] = []
        for text in candidate_texts:
            sql = bridge.extract_sql(str(text)).strip()
            if sql and sql not in sqls:
                sqls.append(sql)

        # Make sure we have at least two distinct candidates.
        extra_attempts = 0
        while len(sqls) < 2 and extra_attempts < 3:
            extra_attempts += 1
            existing_block = "\n".join(f"- {s}" for s in sqls)
            extra_prompt = (
                base_prompt
                + "\n\nAlready generated SQL queries:\n"
                + existing_block
                + "\n\nGenerate a SQL query that is different from the above and "
                "answers the question. Return only SQL."
            )
            raw = self.llm(
                extra_prompt,
                system="Generate a different SQL query. Return only SQL.",
                temperature=0.0,
                n=1,
            )
            sql = bridge.extract_sql(self._as_str(raw)).strip()
            if sql and sql not in sqls:
                sqls.append(sql)

        # 2. Execute every candidate and record the outcome.
        executed = []
        for sql in sqls:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}
            executed.append({"sql": sql, "result": result})

        successful = [item for item in executed if item["result"].get("ok")]
        failed = [item for item in executed if not item["result"].get("ok")]

        # 3. Branch on whether any candidate executed cleanly.
        if successful:
            summary = self._build_summary(successful, failed)
            final_system = "You are an expert SQL reviewer. Return only the best SQL query."
            final_prompt = self._build_selection_prompt(question, schema, summary)
        else:
            summary = self._build_summary([], failed)
            final_system = "You are an expert SQL debugger. Return only a corrected SQL query."
            final_prompt = self._build_correction_prompt(question, schema, summary)

        raw_final = self.llm(
            final_prompt,
            system=final_system,
            temperature=0.0,
            n=1,
        )
        final_sql = bridge.extract_sql(self._as_str(raw_final)).strip()
        return final_sql

    def _build_base_prompt(self, question: str, schema: str) -> str:
        return (
            "Write a SQL query to answer the following question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}"
        )

    def _build_selection_prompt(self, question: str, schema: str, summary: str) -> str:
        return (
            "You generated candidate SQL queries and executed them. "
            "Here are the execution outcomes:\n\n"
            f"{summary}\n\n"
            "Original question:\n"
            f"{question}\n\n"
            "Schema:\n"
            f"{schema}\n\n"
            "Return only the SQL query that best answers the question. "
            "You may output one of the successful queries or a corrected version, "
            "but it must be a single SQL statement."
        )

    def _build_correction_prompt(self, question: str, schema: str, summary: str) -> str:
        return (
            "You generated candidate SQL queries, but none executed successfully. "
            "Here are their execution outcomes:\n\n"
            f"{summary}\n\n"
            "Original question:\n"
            f"{question}\n\n"
            "Schema:\n"
            f"{schema}\n\n"
            "Return only a corrected SQL query that answers the question and "
            "will execute successfully."
        )

    def _build_summary(self, successful: List[Any], failed: List[Any]) -> str:
        lines = []

        # Sorting makes the final prompt invariant to the order in which
        # candidate answers were sampled.
        if successful:
            successes = sorted(successful, key=lambda x: (len(x["sql"]), x["sql"]))
            for idx, item in enumerate(successes, 1):
                lines.append(f"--- Successful candidate {idx} ---")
                lines.append(self._format_execution(item))

        if failed:
            failures = sorted(failed, key=lambda x: (len(x["sql"]), x["sql"]))
            for idx, item in enumerate(failures, 1):
                lines.append(f"--- Failed candidate {idx} ---")
                lines.append(self._format_execution(item))

        if not lines:
            return "No execution results available."
        return "\n".join(lines)

    def _format_execution(self, item: Any) -> str:
        sql = item["sql"]
        result = item["result"]

        if result.get("ok"):
            rows = result.get("rows") or []
            return (
                f"SQL: {sql}\n"
                f"Status: OK\n"
                f"Rows returned: {len(rows)}\n"
                f"Sample rows: {rows[:3]}"
            )

        error = result.get("error") or "Unknown error"
        return f"SQL: {sql}\nStatus: ERROR\nError: {error}"

    @staticmethod
    def _as_list(response: Any) -> List[str]:
        if isinstance(response, list):
            return [str(x) for x in response]
        if response is None:
            return []
        return [str(response)]

    @staticmethod
    def _as_str(response: Any) -> str:
        if isinstance(response, list):
            if not response:
                return ""
            return str(response[0])
        return str(response)