import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    MIN_DISTINCT_SAMPLES = 3
    MAX_CANDIDATE_ATTEMPTS = 8

    def solve(self, question: str) -> str:
        schema = self.schema

        candidates, seen = self._generate_candidates(question, schema)
        candidates = self._ensure_enough_candidates(candidates, seen)

        exec_results = []
        for sql in candidates[: self.MIN_DISTINCT_SAMPLES]:
            result = self.execute(sql)
            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": str(result)}

            rows = result.get("rows", [])
            if rows is None:
                rows = []

            exec_results.append({
                "sql": sql,
                "ok": bool(result.get("ok", False)),
                "rows": rows,
                "error": str(result.get("error", "")) if result.get("error") is not None else "",
            })

        # Sorting makes the final prompt invariant to the order of generated candidates.
        sorted_results = sorted(exec_results, key=lambda r: self._normalize_sql(r["sql"]))

        has_ok = any(r["ok"] for r in sorted_results)
        has_nonempty = any(r["ok"] and len(r["rows"]) > 0 for r in sorted_results)

        if not has_ok:
            instruction = (
                "All candidate SQL queries failed to execute. "
                "Use the error messages below to write a corrected SQL query."
            )
        elif has_nonempty:
            instruction = (
                "Some candidate SQL queries executed successfully and returned rows. "
                "Select the best candidate or write an improved final SQL query based on the execution results."
            )
        else:
            instruction = (
                "Some candidate SQL queries executed successfully but returned zero rows. "
                "Write an adjusted SQL query that is likely to return relevant rows."
            )

        feedback = self._format_execution_feedback(sorted_results)

        final_prompt = f"""You are an expert SQL writer.

Schema:
{schema}

Question:
{question}

Candidate SQL queries and their execution results:
{feedback}

{instruction}

Return only the final SQL query for the question.
"""

        final_raw = self.llm(
            final_prompt,
            system="You are an expert SQL writer.",
            temperature=0.0,
            n=1,
        )

        final_sql = bridge.extract_sql(final_raw)
        if not final_sql:
            final_sql = self._force_final_sql(final_prompt, final_raw)

        return final_sql

    def _generate_candidates(self, question, schema):
        candidates = []
        seen = set()
        attempts = 0

        while len(candidates) < self.MIN_DISTINCT_SAMPLES and attempts < self.MAX_CANDIDATE_ATTEMPTS:
            attempts += 1

            if attempts == 1:
                prompt = self._multi_candidate_prompt(question, schema)
                raw = self.llm(
                    prompt,
                    system="You are an expert SQL writer.",
                    temperature=0.7,
                    n=1,
                )
                sqls = self._extract_multiple_sql(raw)
            else:
                prompt = self._single_distinct_prompt(question, schema, candidates)
                raw = self.llm(
                    prompt,
                    system="You are an expert SQL writer.",
                    temperature=0.7,
                    n=1,
                )
                sqls = self._extract_multiple_sql(raw)
                if not sqls:
                    sql = bridge.extract_sql(raw)
                    if sql:
                        sqls = [sql]

            for sql in sqls:
                self._add_candidate(candidates, seen, sql)
                if len(candidates) >= self.MIN_DISTINCT_SAMPLES:
                    break

        return candidates, seen

    def _multi_candidate_prompt(self, question, schema):
        return f"""You are given the following database schema:
{schema}

Question:
{question}

Generate exactly {self.MIN_DISTINCT_SAMPLES} different SQL query candidates that could answer the question.
Return each candidate inside a fenced SQL code block, for example: