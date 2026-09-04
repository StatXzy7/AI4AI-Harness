from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    """Generate multiple SQL candidates, execute them all, then use execution
    evidence to prompt a final generation step. If the final query does not
    execute cleanly, fall back to a proven successful candidate when possible.
    """

    def solve(self, question: str) -> str:
        # Step 1: sample several candidate SQL strings with different prompt
        # strategies. This intentionally uses multiple generation calls.
        candidate_queries = []
        candidate_results = []

        for i in range(3):
            prompt = self._candidate_prompt(question, i)
            raw = self._call_llm(prompt, system="You are an expert SQL writer. Output only SQL.")
            sql = self._extract_sql(raw)

            candidate_queries.append(sql)
            candidate_results.append(self._execute(sql))

        # Step 2: use execution outcome as control-flow input.
        successes = []
        failures = []
        for sql, res in zip(candidate_queries, candidate_results):
            if res.get("ok"):
                successes.append((sql, res))
            else:
                failures.append((sql, res))

        # Step 3: build a final prompt that carries forward SQL and execution
        # evidence. The prompt differs depending on whether any query executed.
        final_prompt = self._build_final_prompt(question, successes, failures)
        final_raw = self._call_llm(
            final_prompt,
            system="You are an expert SQL writer. Output only SQL.",
        )
        final_sql = self._extract_sql(final_raw)

        # If the final model generation is unusable, fall back to the best
        # available candidate before attempting final execution.
        if not final_sql:
            final_sql = self._fallback_sql(successes, candidate_queries)

        # Step 4: execute the final SQL so the returned answer can be checked.
        final_res = self._execute(final_sql)

        if final_res.get("ok"):
            return final_sql

        # If the final execution failed but an earlier candidate already
        # executed successfully, prefer the proven-successful SQL.
        if successes:
            return successes[0][0]

        return final_sql

    def _candidate_prompt(self, question: str, strategy: int) -> str:
        base = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output only the SQL query, with no explanation.\n"
        )

        hints = {
            0: "Use a direct SELECT statement.",
            1: "Use a subquery where it makes the query clearer.",
            2: "Use a CTE (WITH clause) where it makes the query clearer.",
        }

        return base + "\n" + hints.get(strategy, "")

    def _build_final_prompt(self, question: str, successes, failures) -> str:
        parts = [
            f"Database schema:\n{self.schema}",
            f"Question:\n{question}",
            "",
            "I generated and executed several SQL candidates.",
        ]

        if successes:
            parts.append("Candidates that executed successfully:")
            for i, (sql, res) in enumerate(successes, 1):
                rows = self._format_rows(res.get("rows", []))
                parts.append(
                    f"\n--- Success {i} ---\n"
                    f"SQL:\n{sql}\n"
                    f"Returned rows:\n{rows}"
                )

        if failures:
            if successes:
                parts.append("\nCandidates that failed:")
            else:
                parts.append("\nAll candidates failed:")
            for i, (sql, res) in enumerate(failures, 1):
                parts.append(
                    f"\n--- Failure {i} ---\n"
                    f"SQL:\n{sql}\n"
                    f"Error:\n{res.get('error', 'unknown')}"
                )

        if successes:
            parts.append(
                "\nUse the execution evidence above to write a final SQL query "
                "that best answers the question. Return only the SQL query."
            )
        else:
            parts.append(
                "\nWrite a corrected SQL query that executes successfully and "
                "answers the question. Return only the SQL query."
            )

        return "\n".join(parts)

    def _call_llm(self, prompt: str, system: str, n: int = 1) -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=n)
        if isinstance(out, list):
            if not out:
                return ""
            return str(out[0])
        return str(out)

    def _extract_sql(self, text: str) -> str:
        try:
            return bridge.extract_sql(text).strip()
        except Exception:
            return text.strip()

    def _execute(self, sql: str):
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _format_rows(self, rows, limit: int = 20) -> str:
        if not rows:
            return "(empty result set)"

        rows = list(rows)
        lines = [str(row) for row in rows[:limit]]
        if len(rows) > limit:
            lines.append(f"... {len(rows) - limit} more rows")
        return "\n".join(lines)

    def _fallback_sql(self, successes, candidate_queries) -> str:
        if successes:
            return successes[0][0]

        for sql in candidate_queries:
            if sql:
                return sql

        return "SELECT 1"