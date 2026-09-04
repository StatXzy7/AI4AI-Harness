"""P2P2AMinimaxS0G4: two-stage harness where an LLM proposes a query skeleton with JOIN/conditions, then the second pass finalizes the full SQL using execution hints from a dry-run attempt."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G4(SQLHarness):
    """Two-stage Text-to-SQL harness.

    Stage 1: LLM inspects the schema + question and emits a concise "query skeleton"
    listing the tables, JOIN graph, and WHERE conditions as a short bullet list.
    Stage 2: LLM is asked to write the full SQL using that skeleton, then we run a
    dry execution to surface columns and a sample row. We feed that back for a single
    refinement pass and return the final SQL.
    """

    def _stage1_skeleton(self, question: str) -> str:
        system = (
            "You analyze a database schema and a natural language question. "
            "Produce ONLY a short bullet-list query skeleton: which tables/aliases are "
            "needed, which JOIN keys connect them, and the WHERE conditions. No SQL, "
            "no commentary."
        )
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Query skeleton (bullets only):"
        )
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        return out.strip()

    def _stage2_sql(self, question: str, skeleton: str, hint: str = "") -> str:
        system = (
            "You write a single SQLite-compatible SQL query for the question using "
            "the provided skeleton and schema. Output ONLY the SQL."
        )
        hint_block = f"\nExecution hints:\n{hint}\n" if hint else ""
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Skeleton:\n{skeleton}\n"
            f"{hint_block}"
            "SQL:"
        )
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(out)

    def solve(self, question: str) -> str:
        # Stage 1: produce a structural plan from the schema.
        skeleton = self._stage1_skeleton(question)

        # Stage 2a: initial SQL from the skeleton.
        sql = self._stage2_sql(question, skeleton)
        if not sql:
            return ""

        # Dry-run: execute to harvest columns + one sample row (cheap signal).
        result = self.execute(sql)
        if not result.get("ok"):
            hint = f"The previous SQL failed: {result.get('error', '')}"
        else:
            rows = result.get("rows") or []
            if rows:
                cols = list(rows[0].keys()) if isinstance(rows[0], dict) else []
                sample = rows[0]
                hint = f"Returned columns: {cols}. First row: {sample}."
            else:
                hint = "Query returned zero rows."

        # Stage 2b: refinement pass informed by execution feedback.
        refined = self._stage2_sql(question, skeleton, hint=hint)
        if refined:
            # Trust the refined SQL only if it parses + executes OK; else fall back.
            check = self.execute(refined)
            if check.get("ok"):
                return refined

        return sql