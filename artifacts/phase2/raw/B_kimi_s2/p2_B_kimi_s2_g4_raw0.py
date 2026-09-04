"""Execution-feedback repair loop: generate SQL, run it, and feed SQLite errors (or zero-row results) back for regeneration up to 4 attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G4(SQLHarness):
    """Weak-solver wrapper that repairs its own SQL using live execution feedback.

    Round 1 is a greedy (temperature=0.0) generation. Each subsequent round
    re-prompts the frozen model with the previous SQL plus concrete feedback
    from actually executing it: the SQLite error message on failure, or a
    zero-row warning on suspicious success. Later rounds use a small
    temperature so the repair is not stuck repeating the same mistake.
    """

    MAX_ATTEMPTS = 4

    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        sql = bridge.extract_sql(out)
        return sql if sql else out.strip()

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL engine. "
            "You output exactly one valid SQLite query and nothing else."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Use only tables and columns present in the schema. "
            "Return only the SQL."
        )

        prompt = base_prompt
        candidate = ""
        best_ok_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            temperature = 0.0 if attempt == 0 else 0.3
            candidate = self._generate(prompt, system, temperature)

            try:
                result = self.execute(candidate)
            except Exception as exc:  # defensive: execution layer itself raised
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                if result.get("rows"):
                    return candidate
                if not best_ok_sql:
                    best_ok_sql = candidate
                feedback = (
                    "Your query executed but returned ZERO rows, which is usually "
                    "wrong. Check literal spellings and case in WHERE clauses, "
                    "JOIN key choices, and whether a filter should be relaxed. "
                    "Produce a corrected query."
                )
            else:
                feedback = (
                    "Your query failed to execute. SQLite error:\n"
                    f"{result.get('error', 'unknown error')}\n"
                    "Fix the syntax and the table/column names, then produce a "
                    "corrected query."
                )

            prompt = (
                f"{base_prompt}\n\n"
                f"Previous attempt:\n{candidate}\n\n"
                f"{feedback}\n\n"
                "Output only the corrected SQL."
            )

        # Prefer a syntactically valid, executable query over the last broken one.
        return best_ok_sql or candidate