from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        candidates = []
        while len(candidates) < 3:
            raw = self._llm_call(self._candidate_prompt(question, schema))
            sql = bridge.extract_sql(raw).strip()
            if sql and sql not in candidates:
                candidates.append(sql)

        exec_results = []
        for sql in candidates:
            result = self.execute(sql)
            ok = bool(result.get("ok"))
            if ok:
                rows = result.get("rows", [])
                status = f"OK, {len(rows)} rows returned"
            else:
                error = result.get("error", "unknown error")
                status = f"ERROR: {error}"
            exec_results.append({"sql": sql, "status": status})

        # Deterministic, order-invariant presentation of sampled candidates.
        exec_results.sort(key=lambda item: (item["sql"].lower(), item["sql"]))

        raw_final = self._llm_call(self._final_prompt(question, schema, exec_results))
        final_sql = bridge.extract_sql(raw_final).strip()
        if not final_sql:
            final_sql = raw_final.strip()

        return final_sql

    def _llm_call(self, prompt: str, system: str = "") -> str:
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(raw, list):
            return raw[0] if raw else ""
        return raw

    def _candidate_prompt(self, question: str, schema: str) -> str:
        return f"""You are a text-to-SQL engine. Given the database schema, write a single SQL query that answers the question.

Schema:
{schema}

Question:
{question}

Return only the SQL query in a single fenced code block."""

    def _final_prompt(self, question: str, schema: str, exec_results: list[dict]) -> str:
        candidate_block = "\n".join(
            f"{i}. SQL: {item['sql']}\n   Execution result: {item['status']}"
            for i, item in enumerate(exec_results, 1)
        )

        return f"""You are a text-to-SQL engine. Several candidate SQL queries were generated for the same question and executed.

Question:
{question}

Schema:
{schema}

Candidate results:
{candidate_block}

Use the execution results to select the best candidate or produce a corrected SQL query. Prefer a candidate that executed successfully. If no candidate executed successfully, repair the most promising one using the error messages.
Return only the final SQL query in a single fenced code block."""