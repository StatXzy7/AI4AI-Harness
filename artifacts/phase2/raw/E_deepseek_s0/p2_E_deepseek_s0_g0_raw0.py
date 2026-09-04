"""Two-phase planning and execution-guided repair harness that prunes schema before SQL generation and iteratively fixes runtime errors."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        question = question.strip()

        # Phase 1: ask the model to select relevant schema elements.
        planned_schema = self.schema
        plan = self._plan_schema(question)
        if plan:
            reduced = self._reduce_schema(plan)
            if reduced.strip():
                planned_schema = reduced

        # Phase 2: generate SQL from the (possibly reduced) schema.
        sql = self._generate_sql(question, planned_schema)
        if not sql:
            sql = self._generate_sql(question, self.schema)

        if not sql:
            return self._safe_select()

        # Phase 3: execute and, on failure, perform targeted repair.
        last_sql = sql
        result = self._execute_sql(last_sql)
        if result.get("ok"):
            return last_sql

        error = result.get("error", "Unknown error")
        for _ in range(2):
            repaired = self._generate_repair(question, last_sql, error)
            if not repaired:
                break
            last_sql = repaired
            result = self._execute_sql(last_sql)
            if result.get("ok"):
                return last_sql
            error = result.get("error", "Unknown error")

        return last_sql

    def _call_llm(self, prompt: str, system: str) -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(out, list):
            out = out[0] if out else ""
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or ""
        return str(out).strip() if out else ""

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                return sql.strip()
        except Exception:
            pass

        try:
            cleaned = re.sub(r"