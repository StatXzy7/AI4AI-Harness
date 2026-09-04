"""Generate multiple SQL candidates, validate them by execution, and repair the best failing candidate using error feedback."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        sql_candidates = self._generate_candidates(prompt, n=4, temperature=0.2)

        failing_results = []
        for sql in sql_candidates:
            result = self._safe_execute(sql)
            if result.get("ok"):
                return sql
            failing_results.append((sql, result))

        if not failing_results:
            # No candidates at all; make one final deterministic call.
            sql = self._call_llm_single(prompt, temperature=0.0)
            if sql:
                return sql
            return "SELECT 1"

        # Choose the shortest failing SQL as a repair starting point.
        current_sql, current_result = min(failing_results, key=lambda item: len(item[0]))
        current_error = current_result.get("error", "")

        for _ in range(3):
            repair_prompt = self._build_repair_prompt(question, current_sql, current_error)
            repaired_text = self._call_llm_single(repair_prompt, temperature=0.0)
            repaired_sql = bridge.extract_sql(repaired_text) if repaired_text else ""
            if not repaired_sql:
                continue
            result = self._safe_execute(repaired_sql)
            if result.get("ok"):
                return repaired_sql
            current_sql = repaired_sql
            current_error = result.get("error", "")

        return current_sql or (failing_results[0][0] if failing_results else "SELECT 1")

    def _build_prompt(self, question: str) -> str:
        return f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:"

    def _build_repair_prompt(self, question: str, sql: str, error: str) -> str:
        return (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Write corrected SQL only."
        )

    def _generate_candidates(self, prompt: str, n: int, temperature: float):
        try:
            output = self.llm(prompt, temperature=temperature, n=n)
        except Exception:
            return []
        texts = output if isinstance(output, list) else [output]
        sqls = []
        for text in texts:
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = ""
            if sql:
                sqls.append(sql)
        return sqls

    def _call_llm_single(self, prompt: str, temperature: float) -> str:
        try:
            output = self.llm(prompt, temperature=temperature, n=1)
        except Exception:
            return ""
        if isinstance(output, list):
            return output[0] if output else ""
        return output

    def _safe_execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
            if not isinstance(result, dict):
                return {"ok": False, "rows": [], "error": "Unexpected execute return type"}
            return result
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}