"""Execution-guided repair harness: generate SQL, run it against the database, and feed any execution error back to the LLM for bounded correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G3(SQLHarness):
    """Wraps the frozen solver with an execution-feedback repair loop.

    Control flow:
      1. Greedy-generate an initial SQL query from schema + question.
      2. Execute it via self.execute.
      3. If execution fails, build a repair prompt containing the failed SQL
         and the database error, and regenerate.
      4. Repeat until a query executes successfully or MAX_ATTEMPTS is hit.
      5. Fall back to the best candidate seen if no query ever executes.
    """

    MAX_ATTEMPTS = 4
    SYSTEM = "You are a careful Text-to-SQL engine. Answer with SQL only."

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are an expert SQLite query writer.\n"
            "Given the database schema and a natural-language question, write ONE "
            "correct SQL query.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            "Rules:\n"
            "- Output only the SQL query: no explanations, no markdown fences.\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Use valid SQLite syntax, and add table qualifiers when joining.\n"
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str, failed_attempt: int) -> str:
        return (
            "Your previous SQL query FAILED to execute on the database. Fix it.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### Failed SQL (attempt {failed_attempt})\n{bad_sql}\n\n"
            f"### Database error\n{error[:600]}\n\n"
            "Diagnose the cause of the error (e.g., nonexistent table/column, bad "
            "JOIN condition, invalid syntax, wrong aggregation) and produce ONE "
            "corrected SQLite query that will run successfully.\n"
            "Output only the corrected SQL: no explanations, no markdown fences.\n"
        )

    def solve(self, question: str) -> str:
        candidate = ""        # last SQL extracted from the model
        last_raw = ""         # last raw model output (fallback if extraction always fails)
        last_error = "No SQL could be extracted from the model output."
        prev_failed_sql = None
        prev_error = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if attempt == 1:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(question, candidate or last_raw,
                                             last_error, attempt - 1)

            text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
            last_raw = (text or "").strip()
            sql = bridge.extract_sql(text)

            if sql:
                candidate = sql
                result = self.execute(sql)
                if result.get("ok"):
                    return sql
                last_error = result.get("error", "") or "Unknown execution error."

                # If the model repeats the identical failing query, further
                # deterministic repair calls are very unlikely to help; stop early.
                if sql == prev_failed_sql and last_error == prev_error:
                    break
                prev_failed_sql = sql
                prev_error = last_error
            else:
                # Nothing extractable: treat it as a failure and let the repair
                # prompt show the raw output so the model can correct itself.
                last_error = "No SQL could be extracted from the model output."

        # Fallback: return the most recent extracted SQL (best effort), else raw text.
        return candidate if candidate else last_raw