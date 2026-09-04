"""Implements an execution-guided self-correction Text-to-SQL harness that plans, generates multiple SQL candidates, executes them, and refines based on error feedback."""
from ..harness_base import SQLHarness
from .. import bridge
import re
from typing import List, Optional, Dict, Any


class P2P2EDeepseekS0G0(SQLHarness):
    """Execution-guided Text-to-SQL solver with plan generation, candidate sampling, and error-based refinement."""

    def solve(self, question: str) -> str:
        # Step 1: Generate a textual plan to ground SQL generation
        plan = self._generate_plan(question)

        # Step 2: Generate multiple SQL candidates (n=3) using the plan
        raw_candidates = self._generate_sql_candidates(question, plan)
        first_sql = ""
        last_sql = ""
        last_error = ""
        ok_empty_sql = None

        for raw in raw_candidates:
            sql = self._extract_sql(raw)
            if not sql:
                continue
            if not first_sql:
                first_sql = sql
            last_sql = sql

            exec_result = self._safe_execute(sql)
            if exec_result.get("ok"):
                if exec_result.get("rows"):
                    # Prefer a successful result with data
                    return sql
                else:
                    # Valid query returning no rows is a fallback
                    if ok_empty_sql is None:
                        ok_empty_sql = sql
            else:
                last_error = exec_result.get("error", "Unknown error")

        # If any candidate executed successfully (even with empty rows), return it
        if ok_empty_sql is not None:
            return ok_empty_sql

        # Step 3: If no candidate succeeded, try a direct generation without plan
        if not last_sql:
            direct_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Write the SQL query."
            )
            direct_raw = self._call_llm(
                direct_prompt,
                system="You are an expert SQL generator. Output only the SQL query.",
                n=1,
            )
            if direct_raw:
                direct_sql = self._extract_sql(direct_raw[0])
                if direct_sql:
                    first_sql = direct_sql if not first_sql else first_sql
                    last_sql = direct_sql
                    exec_result = self._safe_execute(direct_sql)
                    if exec_result.get("ok"):
                        return direct_sql
                    last_error = exec_result.get("error", "Unknown error")

        # Step 4: Refinement loop using execution error feedback
        for _ in range(2):
            if not last_sql:
                break
            refine_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{last_sql}\n\n"
                f"Error message:\n{last_error}\n\n"
                "Write a corrected SQL query."
            )
            refine_raw = self._call_llm(
                refine_prompt,
                system="You are an expert SQL query fixer. Output only the corrected SQL query.",
                n=1,
            )
            if not refine_raw:
                continue
            refined_sql = self._extract_sql(refine_raw[0])
            if not refined_sql:
                continue
            exec_result = self._safe_execute(refined_sql)
            if exec_result.get("ok"):
                return refined_sql
            last_error = exec_result.get("error", "Unknown error")
            last_sql = refined_sql

        # Step 5: Fallback to the best SQL seen (or empty string)
        return last_sql or first_sql or ""

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _generate_plan(self, question: str) -> str:
        """Ask the LLM for a step-by-step SQL plan."""
        plan_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Outline a step-by-step plan to answer this question using SQL. "
            "Identify relevant tables, columns, joins, filters, and aggregations. "
            "Do not write SQL yet."
        )
        try:
            plan_result = self._call_llm(
                plan_prompt,
                system="You are an expert SQL query planner.",
                n=1,
            )
            if plan_result and plan_result[0].strip():
                return plan_result[0].strip()
        except Exception:
            pass
        return ""

    def _generate_sql_candidates(self, question: str, plan: str) -> List[str]:
        """Generate multiple SQL candidates using the plan (or without if missing)."""
        if plan:
            gen_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{plan}\n\n"
                "Write the SQL query."
            )
        else:
            gen_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Write the SQL query."
            )
        try:
            return self._call_llm(
                gen_prompt,
                system="You are an expert SQL generator. Output only the SQL query.",
                n=3,
            )
        except Exception:
            return []

    def _call_llm(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> List[str]:
        """Call self.llm and normalize the result to a list of strings."""
        result = self.llm(prompt, system=system, temperature=temperature, n=n)
        if isinstance(result, list):
            return result
        return [result]

    def _safe_execute(self, sql: str) -> Dict[str, Any]:
        """Execute SQL and always return a dict with 'ok', 'rows', 'error'."""
        try:
            result = self.execute(sql)
            if isinstance(result, dict):
                return result
            return {"ok": False, "rows": [], "error": "Invalid execution result format"}
        except Exception as e:
            return {"ok": False, "rows": [], "error": str(e)}

    def _extract_sql(self, text: str) -> str:
        """Extract SQL from LLM output using bridge and fallback heuristics."""
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                return sql.strip()
        except Exception:
            pass

        # Fallback: try code blocks
        m = re.search(r"