"""Self-repair: execute candidate SQL and retry with execution errors fed back to the LLM up to a fixed budget."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        prompt = (
            "You are an expert SQLite writer. Given the schema below and a natural "
            "language question, write ONE SQL query that answers it. Output ONLY the "
            "SQL, no prose, no markdown fences.\n\n"
            f"### SCHEMA\n{schema}\n\n"
            f"### QUESTION\n{question}\n\n"
            "### SQL\n"
        )

        current_sql = self._first_pass(prompt)
        if not current_sql:
            return ""

        attempts = 0
        max_attempts = 4
        last_good_sql = current_sql

        exec_result = self.execute(current_sql)
        while not exec_result.get("ok", False) and attempts < max_attempts:
            attempts += 1
            err_msg = exec_result.get("error", "unknown execution error")
            repair_prompt = self._build_repair_prompt(
                schema, question, current_sql, err_msg
            )
            repaired = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            candidate = bridge.extract_sql(repaired)
            if not candidate:
                break
            current_sql = candidate
            last_good_sql = candidate
            exec_result = self.execute(current_sql)

        # Even if execution succeeded, do one validation pass against an empty-row
        # sanity check using the LLM to catch semantic errors (empty result rows
        # when an answer was expected is fed back as a soft signal).
        if exec_result.get("ok", False):
            rows = exec_result.get("rows") or []
            if len(rows) == 0:
                # try one more repair iteration targeting the empty-result issue
                fix_prompt = self._build_repair_prompt(
                    schema,
                    question,
                    current_sql,
                    "The query executed successfully but returned 0 rows. "
                    "Re-examine the question and schema; the query likely misses "
                    "join or filter conditions. Rewrite the SQL.",
                )
                attempt_out = self.llm(fix_prompt, system="", temperature=0.0, n=1)
                candidate2 = bridge.extract_sql(attempt_out)
                if candidate2:
                    check = self.execute(candidate2)
                    if check.get("ok", False):
                        last_good_sql = candidate2

        return last_good_sql

    def _first_pass(self, prompt: str) -> str:
        out = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(out)
        return sql or ""

    def _build_repair_prompt(
        self, schema: str, question: str, sql: str, error: str
    ) -> str:
        return (
            "You are an expert SQLite debugger. The previous SQL query failed to "
            "execute against the database. Read the schema, the original question, "
            "the attempted SQL, and the database error, then produce a corrected "
            "SQL query. Output ONLY the corrected SQL, no prose, no markdown fences.\n\n"
            f"### SCHEMA\n{schema}\n\n"
            f"### QUESTION\n{question}\n\n"
            f"### ATTEMPTED SQL\n{sql}\n\n"
            f"### DATABASE ERROR\n{error}\n\n"
            "### CORRECTED SQL\n"
        )