"""A Text-to-SQL harness that uses a plan-to-execute control flow with multi-candidate generation and error-driven repair."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    """Plan-to-Predict-to-Execute harness for Text-to-SQL.

    The harness first asks the model to produce a reasoning plan (which tables,
    columns, joins, filters, etc. are relevant), then generates multiple SQL
    candidates from that plan. It executes each candidate and returns the first
    one that succeeds. If none succeed, it enters an iterative repair loop where
    execution errors are fed back to the model until a query succeeds or the
    maximum number of repair attempts is exhausted.
    """

    def solve(self, question: str) -> str:
        plan = self._generate_plan(question)
        candidates = self._generate_candidates(question, plan)
        return self._execute_and_repair(question, plan, candidates)

    def _generate_plan(self, question: str) -> str:
        prompt = (
            "You are an expert SQL planner. Given the database schema below and a natural language question, "
            "produce a concise, step-by-step plan for writing a SQL query that answers the question. "
            "Identify the relevant tables, columns, join conditions, filters, and aggregations. "
            "Do NOT write any SQL code; output only the plan.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        raw = self.llm(
            prompt,
            system="You are a meticulous SQL planning assistant.",
            temperature=0.0,
            n=1,
        )
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        return raw.strip()

    def _generate_candidates(self, question: str, plan: str) -> list:
        prompt = (
            "You are an expert SQL query writer. Given the database schema, a natural language question, "
            "and a reasoning plan, write a single SQL query that correctly answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "Write only the SQL query, no explanation. SQL:"
        )
        # Generate multiple candidates for execution-based selection.
        raw = self.llm(
            prompt,
            system="You are a pragmatic SQL writing assistant.",
            temperature=0.2,
            n=3,
        )
        if isinstance(raw, list):
            texts = raw
        else:
            texts = [raw]

        candidates = []
        seen = set()
        for text in texts:
            sql = bridge.extract_sql(text)
            if sql and sql not in seen:
                seen.add(sql)
                candidates.append(sql)
        return candidates

    def _execute_and_repair(self, question: str, plan: str, candidates: list) -> str:
        if not candidates:
            # Fallback: direct generation without plan if plan/candidate generation failed.
            fallback_prompt = (
                "Given the database schema below and a natural language question, "
                "write a single SQL query that correctly answers the question.\n\n"
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "SQL:"
            )
            raw = self.llm(
                fallback_prompt,
                system="You are a helpful SQL assistant.",
                temperature=0.0,
                n=1,
            )
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            sql = bridge.extract_sql(raw)
            if sql:
                candidates = [sql]
            else:
                return ""

        first_error = None
        # Try all candidates; return the first that executes successfully.
        for cand in candidates:
            result = self.execute(cand)
            if result["ok"]:
                return cand
            if first_error is None:
                first_error = result["error"]

        # Repair loop: use the first candidate as the starting point.
        current_sql = candidates[0]
        last_error = first_error or "Unknown execution error."

        for _ in range(3):
            repair_prompt = (
                "You are an expert SQL query writer. The SQL query below produced an error when executed. "
                "Fix the SQL query so that it correctly answers the original question.\n\n"
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{plan}\n\n"
                f"Previous SQL:\n{current_sql}\n\n"
                f"Error message:\n{last_error}\n\n"
                "Write only the corrected SQL query, no explanation. SQL:"
            )
            raw = self.llm(
                repair_prompt,
                system="You are a meticulous SQL repair assistant.",
                temperature=0.0,
                n=1,
            )
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            repaired = bridge.extract_sql(raw)
            if not repaired or repaired == current_sql:
                # No useful repair; stop trying.
                break
            current_sql = repaired
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            last_error = result["error"]

        return current_sql