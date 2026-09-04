"""Repairs generated SQL by executing it and feeding errors (or empty results) back for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G3(SQLHarness):
    """Generate SQL greedily, execute it, and repair it in a feedback loop.

    Improvement over a single greedy call: instead of trusting the first
    generation, the harness actually runs the SQL against the database.
    Execution errors -- and suspicious empty result sets -- are appended to
    the prompt as explicit feedback and the model is asked to produce a
    corrected query. Sampling temperature is escalated slightly on retries so
    the model escapes the failing mode. The best executable candidate is kept
    as a fallback so the loop never returns something worse than what already
    ran successfully.
    """

    MAX_ATTEMPTS = 5

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL system. Given a database "
            "schema and a natural-language question, output exactly one valid "
            "SQLite query that answers the question. Output only the SQL "
            "query, with no explanation or commentary."
        )
        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the single SQLite SQL query that answers the question."
        )

        history = []          # (sql_or_raw_text, problem_description)
        fallback_sql = None   # last SQL that executed without error
        last_sql = None       # last SQL we managed to extract
        temperature = 0.0

        for _ in range(self.MAX_ATTEMPTS):
            prompt = base_prompt
            if history:
                parts = ["Your previous attempt(s) did not work. Review them carefully:"]
                for i, (sql, note) in enumerate(history, 1):
                    parts.append(f"--- Attempt {i} ---\n{sql}\nProblem: {note}")
                parts.append(
                    "Produce a corrected SQLite query that fixes the problem above. "
                    "Return only the corrected SQL query."
                )
                prompt = base_prompt + "\n\n" + "\n\n".join(parts)

            response = self.llm(prompt, system=system, temperature=temperature, n=1)
            text = response[0] if isinstance(response, (list, tuple)) else response

            sql = bridge.extract_sql(text)
            if not sql:
                history.append((
                    (text or "").strip() or "<empty output>",
                    "No SQL statement could be extracted from your output. "
                    "Return a single SQL query, optionally inside a