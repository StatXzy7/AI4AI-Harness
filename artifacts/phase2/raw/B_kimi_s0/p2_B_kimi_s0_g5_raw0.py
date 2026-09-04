"""Repair-loop harness that generates SQL, executes it, and feeds execution errors back into the prompt so the LLM can iteratively fix the query."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G5(SQLHarness):
    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQL query writer. Given a database schema and a "
            "natural-language question, output ONLY one SQL query that answers "
            "the question. No explanations, no markdown fences, no commentary."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output only the SQL."
        )

        prompt = base_prompt
        history = []          # accumulated error feedback for the next regeneration
        best_sql = ""         # most recent syntactically extracted SQL (fallback)
        raw_fallback = ""     # last raw LLM output, in case extraction never works

        for attempt in range(self.MAX_ATTEMPTS):
            # First try is greedy; later tries get a little temperature so the
            # model does not deterministically repeat the same broken query.
            temperature = 0.0 if attempt == 0 else 0.3
            text = self.llm(prompt, system=system, temperature=temperature)
            raw_fallback = text
            sql = bridge.extract_sql(text)

            if not sql:
                history.append(
                    f"Attempt {attempt + 1}: your reply contained no SQL query. "
                    "Respond with ONLY the SQL text."
                )
            else:
                best_sql = sql
                result = self.execute(sql)

                if result.get("ok"):
                    # Query runs cleanly -> done.
                    return sql

                error = result.get("error") or "unknown execution error"
                history.append(
                    f"Attempt {attempt + 1} produced this SQL:\n{sql}\n"
                    f"It failed to execute with this error:\n{error}\n"
                    "Diagnose the cause (check table/column names against the "
                    "schema, quoting, and SQL dialect) and output ONLY the "
                    "corrected SQL query."
                )

            prompt = (
                base_prompt
                + "\n\nPrevious attempts and their execution errors:\n"
                + "\n\n".join(history)
            )

        # All attempts exhausted: return the best SQL we managed to extract,
        # falling back to stripped raw text if extraction never succeeded.
        return best_sql if best_sql else raw_fallback.strip()