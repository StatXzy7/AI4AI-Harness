"""Multi-stage Text-to-SQL harness that generates diverse SQL candidates, executes them, repairs failures with error feedback, and selects the best executable SQL."""
import re
from typing import Any, Dict, List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    """A harness that wraps a weak solver with candidate generation, execution validation, iterative repair, and LLM-based selection."""

    MAX_REPAIR_ROUNDS = 2
    CANDIDATE_PROMPTS = [
        "Write a single SQL statement that answers the question.",
        "Think step by step about the required tables and columns, then output only SQL.",
        "Produce a SQL query. Consider joins, filters, aggregations, and edge cases.",
        "Generate a valid SQL query for the question. Use only the schema provided.",
    ]

    def solve(self, question: str) -> str:
        # Generate multiple candidate SQL queries using intentionally varied prompts.
        original_candidates = self._generate_candidates(question)

        if not original_candidates:
            # Direct fallback if the extraction-based generation produced nothing.
            try:
                direct = self._extract_sql(self._ask_llm(self._base_prompt(question)))
            except Exception:
                direct = ""
            original_candidates = [direct] if direct else ["SELECT 1"]

        # Evaluate all original candidates by actually executing them.
        ok_candidates, fail_candidates = self._evaluate_candidates(original_candidates)

        if ok_candidates:
            return self._select_best(question, ok_candidates)

        # Repair loop: use database error messages to guide the weak solver.
        current_failures = fail_candidates
        for _ in range(self.MAX_REPAIR_ROUNDS):
            repaired_sqls = []
            for sql, result in current_failures:
                fixed_sql = self._repair_sql(question, sql, result)
                if fixed_sql:
                    repaired_sqls.append(fixed_sql)

            if not repaired_sqls:
                break

            ok_candidates, current_failures = self._evaluate_candidates(repaired_sqls)
            if ok_candidates:
                return self._select_best(question, ok_candidates)

        # If no SQL executes successfully after repairs, return the best available fallback.
        # This is intentionally permissive: external evaluation can still inspect the SQL.
        return original_candidates[0]

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------
    def _generate_candidates(self, question: str) -> List[str]:
        """Generate candidate SQL strings using multiple prompt styles."""
        candidates: List[str] = []
        base = self._base_prompt(question)
        for instruction in self.CANDIDATE_PROMPTS:
            try:
                response = self._ask_llm(f"{base}\n\n{instruction}")
            except Exception:
                continue
            sql = self._extract_sql(response)
            if sql and sql not in candidates:
                candidates.append(sql)
        return candidates

    def _base_prompt(self, question: str) -> str:
        return (
            "You are an expert SQL generator.\n"
            "Given the following database schema and question, produce a single SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query, without markdown fences or explanations."
        )

    # ------------------------------------------------------------------
    # Repair and selection
    # ------------------------------------------------------------------
    def _repair_sql(self, question: str, sql: str, result: Dict[str, Any]) -> str:
        error = result.get("error") or "unknown execution error"
        prompt = (
            "You are an expert SQL debugger.\n"
            "A previously generated SQL query failed to execute.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Failed SQL:\n{sql}\n\n"
            f"Database error:\n{error}\n\n"
            "Fix the SQL and return only the corrected SQL query, without markdown fences or explanations."
        )
        try:
            response = self._ask_llm(prompt)
        except Exception:
            return ""
        return self._extract_sql(response)

    def _select_best(self, question: str, ok_candidates: List[Tuple[str, Dict[str, Any]]]) -> str:
        """Use a second LLM pass to choose the most semantically correct executable SQL."""
        if len(ok_candidates) == 1:
            return ok_candidates[0][0]

        lines = []
        for i, (sql, result) in enumerate(ok_candidates, 1):
            preview = self._rows_preview(result.get("rows", []))
            lines.append(
                f"{i}. SQL: {sql}\n   Execution succeeded. Result preview: {preview}"
            )

        prompt = (
            "You are a Text-to-SQL evaluator.\n"
            "Choose the SQL query that best answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            + "\n\n".join(lines)
            + "\n\nReply with only the number of the best SQL. Do not include SQL or explanation."
        )

        try:
            response = self._ask_llm(prompt).strip()
        except Exception:
            response = "1"

        match = re.search(r"\b[1-9]\d*\b", response)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(ok_candidates):
                return ok_candidates[idx][0]

        return ok_candidates[0][0]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _evaluate_candidates(
        self, sqls: List[str]
    ) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[Tuple[str, Dict[str, Any]]]]:
        ok: List[Tuple[str, Dict[str, Any]]] = []
        fail: List[Tuple[str, Dict[str, Any]]] = []
        for sql in sqls:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                ok.append((sql, result))
            else:
                fail.append((sql, result))
        return ok, fail

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ask_llm(self, prompt: str) -> str:
        """Call self.llm defensively, normalizing possible list or dict responses."""
        out = self.llm(prompt, temperature=0.0, n=1)

        if isinstance(out, list):
            if not out:
                return ""
            out = out[0]

        if isinstance(out, dict):
            choices = out.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                return content.strip()
            return ""

        return str(out).strip()

    def _extract_sql(self, text: str) -> str:
        """Extract SQL using the provided bridge and fall back to simple cleanup."""
        try:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                return sql.strip()
        except Exception:
            pass

        cleaned = text.strip()

        # Remove common code fences if bridge failed.
        if "