"""Repair-loop harness that generates SQL, executes it, and feeds execution errors back to the LLM for iterative correction."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G2(SQLHarness):
    """Text-to-SQL harness with an execute-and-repair control loop.

    Round 0 greedily generates a candidate query. If executing it against
    the database fails, the failing SQL and the database's error message
    are appended to the prompt and the model is asked for a corrected
    query. Later rounds use a slowly rising temperature so the model can
    escape repeatedly repeating the same mistake. The first query that
    executes successfully is returned; if every attempt fails, the most
    recent candidate is returned as a best effort.
    """

    MAX_REPAIRS = 3
    TEMPERATURES = (0.0, 0.3, 0.5, 0.7)

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL engine. "
            "You output exactly one valid SQLite query and nothing else: "
            "no explanations, no comments, no markdown fences."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Use only tables and columns that appear in the schema. "
            "Output only the SQL."
        )

        failures = []
        last_sql = ""
        prompt = base_prompt

        for round_idx in range(self.MAX_REPAIRS + 1):
            temperature = self.TEMPERATURES[
                min(round_idx, len(self.TEMPERATURES) - 1)
            ]
            text = self.llm(prompt, system=system, temperature=temperature)
            sql = bridge.extract_sql(text).strip() or text.strip()
            if not sql:
                # Nothing usable came back; retry with the same prompt.
                continue
            last_sql = sql

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error") or "unknown execution error")[:500]
            failures.append((sql, error))

            history = "\n\n".join(
                f"Failed attempt {i}:\n{bad_sql}\nDatabase error: {err}"
                for i, (bad_sql, err) in enumerate(failures, start=1)
            )
            prompt = (
                f"{base_prompt}\n\n"
                "Your previous SQL failed to run. Diagnose the error, check "
                "the table and column names against the schema, fix the "
                "SQLite syntax, and produce a corrected query. Do not repeat "
                "any earlier failing query.\n\n"
                f"{history}\n\n"
                "Output only the corrected SQL."
            )

        return last_sql