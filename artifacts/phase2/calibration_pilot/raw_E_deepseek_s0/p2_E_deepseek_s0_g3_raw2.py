from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        initial_candidates = self._generate_initial_candidates(question)

        # Sort candidates so later decisions do not depend on sample order.
        candidates_sorted = sorted(initial_candidates)

        execution_results = []
        for sql in candidates_sorted:
            execution_results.append((sql, self.execute(sql)))

        refined_sql = self._generate_refined_sql(question, execution_results)

        if refined_sql:
            refined_execution = self.execute(refined_sql)
            if refined_execution.get("ok"):
                return refined_sql

        # Fall back to the first successful initial candidate.
        for sql, execution in execution_results:
            if execution.get("ok"):
                return sql

        if refined_sql:
            return refined_sql
        if execution_results:
            return execution_results[0][0]
        return "SELECT 1"

    def _generate_initial_candidates(self, question):
        hints = [
            "Write a single SQL query that answers the question.",
            "Write a correct SQLite query for the question. Use JOINs where appropriate.",
            "Write a SQL query for the question. You may use subqueries or CTEs if needed.",
        ]
        system_messages = [
            "You are a SQL expert. Output only SQL.",
            "You are a database developer. Output only SQL.",
            "You are a query optimizer. Output only SQL.",
        ]

        candidates = []
        for i in range(3):
            prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"{hints[i]}\n\n"
                "Output only SQL."
            )

            raw = self.llm(
                prompt,
                system=system_messages[i],
                temperature=0.3,
                n=1,
            )

            sql = (bridge.extract_sql(raw) or "").strip()
            if not sql:
                sql = "SELECT 1"

            candidates.append(sql)

        return candidates

    def _generate_refined_sql(self, question, execution_results):
        prompt = self._build_refinement_prompt(question, execution_results)

        raw = self.llm(
            prompt,
            system="You are a SQL debugging expert. Output only the corrected SQL statement.",
            temperature=0.0,
            n=1,
        )

        return (bridge.extract_sql(raw) or "").strip()

    def _build_refinement_prompt(self, question, execution_results):
        lines = [
            "Database schema:",
            self.schema,
            "",
            "Question:",
            question,
            "",
            "Candidate SQL queries and execution feedback:",
            "",
        ]

        for sql, execution in execution_results:
            if execution.get("ok"):
                status = "OK"
                detail = f"Rows: {execution.get('rows', [])}"
            else:
                status = "ERROR"
                detail = execution.get("error", "unknown error")

            lines.extend([
                f"SQL: {sql}",
                f"Status: {status}",
                f"Detail: {detail}",
                "",
            ])

        lines.append(
            "Using the feedback above, write a corrected SQL query that solves the question. "
            "Output only SQL."
        )

        return "\n".join(lines)