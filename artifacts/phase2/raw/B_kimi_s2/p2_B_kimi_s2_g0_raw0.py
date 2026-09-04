"""Repair-loop harness: generate SQL, execute it, and feed execution errors back to the LLM for bounded regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G0(SQLHarness):
    """Generate -> execute -> on failure, feed the database error back and
    regenerate, in a bounded repair loop.

    Improvement over a single greedy call: the first SQL candidate is actually
    executed against the database. If execution fails, the exact error message
    and the faulty SQL are appended to the prompt and the model is asked to
    produce a corrected query. Repairs use a small non-zero temperature so the
    model can escape the failure mode instead of deterministically repeating
    it. The loop is bounded and always returns the best available SQL string.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine. Given a database schema and "
            "a question, output exactly one valid SQL query and nothing else: "
            "no explanations, no markdown code fences."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Use only tables "
            "and columns that appear in the schema above."
        )

        prompt = base_prompt
        candidate_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # Greedy on the first try; slight diversity on repair attempts so
            # the model does not deterministically repeat the same mistake.
            temperature = 0.0 if attempt == 0 else 0.3
            response = self.llm(prompt, system=system, temperature=temperature)
            sql = bridge.extract_sql(response)

            if not sql:
                # Model failed to emit SQL at all: treat as a repairable fault.
                prompt = (
                    f"{base_prompt}\n\n"
                    "Your previous response contained no SQL query. Reply with "
                    "the SQL query only."
                )
                continue

            candidate_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            # Core repair step: feed the real execution error back.
            error = result.get("error") or "unknown execution error"
            prompt = (
                f"{base_prompt}\n\n"
                "Your previous SQL query failed to execute.\n"
                f"Faulty SQL:\n{sql}\n\n"
                f"The database returned this error:\n{error}\n\n"
                "Correct the query so that it executes successfully and "
                "answers the question. Reply with the corrected SQL query "
                "only."
            )

        if candidate_sql:
            # Bounded loop exhausted: return the last syntactically extracted
            # candidate rather than nothing.
            return candidate_sql

        # No candidate was ever extracted; one final plain attempt.
        fallback = self.llm(base_prompt, system=system, temperature=0.0)
        return bridge.extract_sql(fallback)