"""Iteratively generates, executes, and repairs SQL using execution feedback, returning the first valid query."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2EDeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL assistant. Return only the SQL query "
            "that answers the question using the provided schema."
        )
        initial_prompt = self._build_initial_prompt(question)

        # Generate multiple candidates in the first attempt to increase success probability.
        raw_candidates = self.llm(initial_prompt, system=system, temperature=0.2, n=3)
        if not isinstance(raw_candidates, list):
            raw_candidates = [raw_candidates]

        candidate_sqls = []
        errors = {}

        for raw in raw_candidates:
            if raw is None:
                continue
            sql = bridge.extract_sql(str(raw))
            if not sql:
                continue
            candidate_sqls.append(sql)
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            errors[sql] = result.get("error", "Execution failed")

        # Repair loop using the last failed candidate and its execution error.
        for _ in range(2):
            if not candidate_sqls:
                break
            last_sql = candidate_sqls[-1]
            last_error = errors.get(last_sql, "No SQL could be extracted or executed")
            repair_prompt = self._build_repair_prompt(question, last_sql, last_error)

            raw = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            if raw is None:
                continue

            sql = bridge.extract_sql(str(raw))
            if not sql:
                continue

            candidate_sqls.append(sql)
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            errors[sql] = result.get("error", "Execution failed")

        # Fallback: return the last candidate even if it failed, preserving visible output.
        return candidate_sqls[-1] if candidate_sqls else "SELECT 1"

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "Use the following database schema to answer the question by generating a single SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, without explanation."
        )

    def _build_repair_prompt(self, question: str, previous_sql: str, error: str) -> str:
        return (
            "The following SQL query failed to execute.\n\n"
            f"Question: {question}\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Please return a corrected SQL query that answers the question. "
            "Return only the SQL query, without explanation."
        )