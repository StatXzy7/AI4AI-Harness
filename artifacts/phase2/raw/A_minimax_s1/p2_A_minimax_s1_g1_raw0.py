"""Repair mechanism: execute SQL and feed errors back for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS1G1(SQLHarness):
    """Attempt to generate SQL; if execution fails, repair by providing error feedback."""

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are a SQL expert. Given a schema and a question, output exactly one "
            "executable SQL statement. Output ONLY the SQL, no prose, no markdown fences."
        )

        # First attempt: direct generation.
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        text = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(text)
        if sql:
            exec_result = self.execute(sql)
            if exec_result.get("ok"):
                return sql

        last_err = ""
        # Subsequent attempts: feed execution errors back to repair.
        for attempt in range(1, self.MAX_ATTEMPTS):
            err = last_err or "unknown error"
            sql_preview = sql if sql else "(no prior SQL)"
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{sql_preview}\n\n"
                f"Execution error:\n{err}\n\n"
                "Corrected SQL (ONLY the SQL, no prose):"
            )
            # alternate slightly higher temperature for diversity in repair hints
            temperature = 0.0 if attempt == 1 else 0.2
            n_samples = 1 if attempt < 3 else 2
            text = self.llm(repair_prompt, system=system,
                            temperature=temperature, n=n_samples)
            best_sql = ""
            best_ok = False
            best_err = ""
            # If we get multiple samples on the last attempt, keep the first that runs.
            for sample in (text if isinstance(text, list) else [text]):
                candidate = bridge.extract_sql(sample)
                if not candidate:
                    continue
                res = self.execute(candidate)
                if res.get("ok"):
                    return candidate
                best_sql = candidate
                best_ok = False
                best_err = res.get("error", "")
            sql = best_sql
            last_err = best_err

        # Fallback: return last attempted SQL even if it didn't execute.
        return sql if sql else text if isinstance(text, str) else ""