"""Two-stage generation: first LLM produces a sketch of relevant tables/columns and intent, then second LLM generates SQL conditioned on the sketch, with execution-based repair fallback."""
# MECHANISM: twostage

import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a focused sketch (relevant tables, joins, conditions, intent)
        sketch_system = (
            "You are a SQL planning assistant. Given a database schema and a natural "
            "language question, output a concise plan describing which tables and columns "
            "are relevant, how they should be joined, what filters/aggregations apply, and "
            "the intent of the query. Be terse and factual. Do not write SQL."
        )
        sketch_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan (tables, joins, filters, aggregations, intent):"
        )
        sketch = self.llm(sketch_prompt, system=sketch_system, temperature=0.0, n=1).strip()

        # Stage 2: generate the final SQL conditioned on the sketch
        sql_system = (
            "You are a precise SQL generator. Use only the schema provided and follow the "
            "given plan exactly. Output a single SQL statement with no commentary."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{sketch}\n\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw) or raw.strip()

        # Optionally attempt a quick syntactic sanity check via execution; if it fails,
        # fall back to a direct (un-conditioned) generation so the two-stage path is the
        # *primary* route but execution is used as a fallback signal.
        # First, strip any obvious leakage from the candidate.
        sql = self._sanitize(sql)
        if not sql:
            return ""

        result = self.execute(sql)
        if not result.get("ok"):
            # Repair once via a repair-style regeneration guided by the error
            err = result.get("error", "")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{sketch}\n\n"
                f"The previous SQL failed with this error:\n{err}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                "Corrected SQL:"
            )
            raw2 = self.llm(repair_prompt, system=sql_system, temperature=0.0, n=1)
            sql2 = bridge.extract_sql(raw2) or raw2.strip()
            sql2 = self._sanitize(sql2)
            if sql2:
                result2 = self.execute(sql2)
                if result2.get("ok"):
                    return sql2
                # If repair still fails, try a plain regeneration as a last resort.
                plain_raw = self.llm(
                    f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:",
                    system=sql_system,
                    temperature=0.0,
                    n=1,
                )
                plain_sql = self._sanitize(bridge.extract_sql(plain_raw) or plain_raw.strip())
                if plain_sql:
                    return plain_sql
                return sql2 or sql
        return sql

    @staticmethod
    def _sanitize(text: str) -> str:
        """Strip markdown fences and stray text; keep the first plausible SQL statement."""
        if not text:
            return ""
        # Remove code fences
        text = re.sub(r"