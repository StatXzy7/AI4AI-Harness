"""Repair-with-execution-feedback harness that regenerates SQL on failure."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


REPAIR_SYSTEM = """You are a SQL repair assistant. A previous attempt to write a SQL query failed.
You will be given:
1. The original natural language question.
2. The database schema.
3. The faulty SQL that was produced.
4. The execution error reported by the database engine.

Your job: produce a corrected SQL query that is valid for the given dialect/schema and
faithfully answers the question. Return ONLY the SQL — no prose, no markdown fences.
Common fixes: missing/wrong table, missing FROM, wrong JOIN keys, unquoted identifiers,
aggregate without GROUP BY, trailing commas, mismatched parentheses, function name typos."""


class P2P2BMinimaxS1G6(SQLHarness):
    """Single-attempt generation, then a bounded repair loop using execution feedback."""

    MAX_REPAIRS = 2  # total attempts = 1 + MAX_REPAIRS

    def solve(self, question: str) -> str:
        # Stage 1: initial greedy generation using the schema.
        initial_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Return only the SQL."
        )
        raw = self.llm(initial_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw).strip()
        if not sql:
            return ""

        # If the first attempt works, we're done (cheap path).
        result = self.execute(sql)
        if result.get("ok"):
            return self._clean(sql, result)

        # Repair loop: feed execution error back to the model.
        last_sql = sql
        last_error = result.get("error", "unknown error")

        for _ in range(self.MAX_REPAIRS):
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Faulty SQL:\n{last_sql}\n\n"
                f"Execution error:\n{last_error}\n\n"
                "Produce a corrected SQL query."
            )
            raw_repair = self.llm(
                repair_prompt, system=REPAIR_SYSTEM, temperature=0.0, n=1
            )
            candidate = bridge.extract_sql(raw_repair).strip()
            if not candidate or candidate == last_sql:
                # Nothing changed -> stop iterating to avoid infinite loops.
                break

            last_sql = candidate
            result = self.execute(last_sql)
            if result.get("ok"):
                return self._clean(last_sql, result)
            last_error = result.get("error", "unknown error")

        # Could not obtain a working query; return the best candidate we have.
        return last_sql

    @staticmethod
    def _clean(sql: str, result: dict) -> str:
        """Light post-processing: trim trailing semicolons/whitespace."""
        s = sql.strip().rstrip(";").strip()
        return s