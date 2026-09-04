# Two-stage Text-to-SQL: first pass generates skeleton, second pass validates and refines against schema.
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G1(SQLHarness):
    # MECHANISM: twostage -- stage 1 produces a candidate SQL; stage 2 critiques/repairs it using schema and execution feedback.
    def solve(self, question: str) -> str:
        schema = self.schema or ""
        schema_brief = schema[:2500] if schema else ""

        # ---------- Stage 1: initial candidate SQL ----------
        stage1_system = (
            "You are a precise Text-to-SQL generator. "
            "Output ONLY a single SQL statement (no prose, no markdown fences)."
        )
        stage1_prompt = (
            f"Given the database schema below, write a SQL query that answers the question.\n\n"
            f"Schema:\n{schema_brief}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        raw1 = self.llm(stage1_prompt, system=stage1_system, temperature=0.0, n=1)
        sql1 = self._clean_sql(bridge.extract_sql(raw1) or raw1)

        if not sql1:
            # Fallback: ask once more with explicit formatting guidance.
            retry_prompt = (
                f"Schema:\n{schema_brief}\n\nQuestion: {question}\n\n"
                f"Reply with exactly one SQL statement wrapped in