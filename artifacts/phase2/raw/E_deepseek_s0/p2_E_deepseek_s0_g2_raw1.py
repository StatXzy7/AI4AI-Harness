"""Iteratively generates SQL candidates and repairs them using database execution feedback."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        def call_llm(prompt, temperature=0.0):
            raw = self.llm(prompt, system="", temperature=temperature, n=1)
            if isinstance(raw, list):
                return raw[0] if raw else ""
            return raw

        def build_prompt(error=None, bad_sql=None):
            if error and bad_sql:
                return f"""Given the following database schema:
{schema}

Question:
{question}

The previous SQL query:
{bad_sql}

caused this error:
{error}

Please generate a corrected SQL query for the question. Return only the SQL query."""
            return f"""Given the following database schema:
{schema}

Question:
{question}

Generate a SQL query that answers the question. Return only the SQL query."""

        # Generate initial candidates, trying both greedy and slightly varied decoding.
        candidates = []
        seen = set()
        results = {}

        for i in range(2):
            temp = 0.0 if i == 0 else 0.3
            raw = call_llm(build_prompt(), temperature=temp)
            sql = bridge.extract_sql(raw)
            if not sql or sql in seen:
                continue

            seen.add(sql)
            execution = self.execute(sql)
            if execution.get("ok"):
                return sql

            candidates.append(sql)
            results[sql] = execution

        # Repair each failed candidate using its execution error.
        max_repairs = 3
        for sql in list(candidates):
            current_sql = sql
            current_result = results[sql]
            current_error = current_result.get("error", "Unknown error")

            for _ in range(max_repairs):
                prompt = build_prompt(error=current_error, bad_sql=current_sql)
                raw = call_llm(prompt)
                new_sql = bridge.extract_sql(raw)

                if not new_sql or new_sql in seen:
                    break

                seen.add(new_sql)
                execution = self.execute(new_sql)
                if execution.get("ok"):
                    return new_sql

                current_sql = new_sql
                current_error = execution.get("error", "Unknown error")

        # Final fallback: use all observed errors as context for a last repair attempt.
        if candidates:
            error_summary = "\n".join(
                f"- {sql}: {results[sql].get('error', 'Unknown error')}"
                for sql in candidates
            )
            final_prompt = f"""Given the following database schema:
{schema}

Question:
{question}

Several SQL attempts failed:
{error_summary}

Please generate a new SQL query for the question. Return only the SQL query."""
            raw = call_llm(final_prompt)
            final_sql = bridge.extract_sql(raw)
            if final_sql:
                return final_sql

        # If nothing succeeds, return the first candidate or an empty string.
        return candidates[0] if candidates else ""