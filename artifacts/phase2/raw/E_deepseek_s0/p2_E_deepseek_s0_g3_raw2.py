"""Two-stage Text-to-SQL harness that uses execution-guided repair and a planner fallback to improve SQL generation."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        base_system = "You are an expert Text-to-SQL assistant. Write only SQLite SQL without explanations."

        def _call_llm(prompt, system=base_system):
            resp = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(resp, list):
                resp = resp[0] if resp else ""
            return str(resp)

        def _extract_sql(text):
            sql = bridge.extract_sql(text)
            if sql:
                return sql.strip().rstrip(';')

            if not text:
                return ""

            # Fallback extraction for models that don't use standard fences.
            matches = re.findall(r"(?i)\b(?:SELECT|WITH)\b[\s\S]*?(?:;|$)", text)
            if matches:
                return matches[-1].strip().rstrip(';')

            # Look for explicit SQL: prefix.
            m = re.search(r'(?i)(?:^|\n)\s*SQL\s*:\s*(\S.*)$', text)
            if m:
                return m.group(1).strip().rstrip(';')
            return ""

        def _execute_safely(sql):
            try:
                return self.execute(sql)
            except Exception as e:
                return {"ok": False, "rows": [], "error": str(e)}

        # Stage 1: direct SQL generation.
        initial_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Return only the SQL query."
        )
        sql = _extract_sql(_call_llm(initial_prompt))

        # If no SQL was extracted, ask once more with a stronger constraint.
        if not sql:
            retry_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                "Return only a single SQL query. Do not include any other text, commentary, or code fences."
            )
            sql = _extract_sql(_call_llm(retry_prompt))

        best_sql = sql or ""

        if best_sql:
            result = _execute_safely(best_sql)
            if result.get("ok"):
                return best_sql

            # Execution-guided repair loop.
            current_sql = best_sql
            for _ in range(3):
                error = result.get("error") or "Unknown SQL execution error"
                repair_prompt = (
                    f"Database schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"The following SQL query was generated but failed to execute:\n{current_sql}\n\n"
                    f"Execution error:\n{error}\n\n"
                    "Write a corrected SQL query that answers the question. Return only the SQL query."
                )
                new_sql = _extract_sql(_call_llm(repair_prompt))
                if not new_sql or new_sql.lower() == current_sql.lower():
                    break
                current_sql = new_sql
                result = _execute_safely(current_sql)
                if result.get("ok"):
                    return current_sql
            best_sql = current_sql or best_sql

        # Stage 2: planner fallback with explicit reasoning before SQL.
        plan_system = (
            "You are an expert Text-to-SQL planner. First think through the required tables, columns, "
            "filters, and joins. Then write the final SQL query on its own line prefixed with 'SQL:'."
        )
        plan_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Reason briefly about how to answer the question. Then output one SQL query. "
            "Put the final SQL on a separate line prefixed with exactly 'SQL:'."
        )
        plan_text = _call_llm(plan_prompt, plan_system)
        plan_sql = _extract_sql(plan_text)

        if plan_sql:
            result = _execute_safely(plan_sql)
            if result.get("ok"):
                return plan_sql

            error = result.get("error") or "Unknown SQL execution error"
            repair_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"The following planned SQL query failed to execute:\n{plan_sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Write a corrected SQL query that answers the question. Return only the SQL query."
            )
            repaired_sql = _extract_sql(_call_llm(repair_prompt))
            if repaired_sql:
                result = _execute_safely(repaired_sql)
                if result.get("ok"):
                    return repaired_sql
                best_sql = repaired_sql or best_sql
            else:
                best_sql = plan_sql or best_sql

        # Final fallback: return the most promising SQL we saw, or a harmless dummy.
        return best_sql or "SELECT 1"