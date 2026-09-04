"""Voting harness: draw multiple SQL samples, execute each, and return the query producing the most non-null result rows."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        if not hasattr(self, "_system_prompt"):
            self._system_prompt = (
                "You are an expert SQL generator. Given the schema and a natural "
                "language question, produce a single executable SQL query. "
                "Return ONLY the SQL statement, no prose, no markdown fences."
            )

        schema = getattr(self, "schema", "")

        prompt = (
            f"### Schema\n{schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### SQL\n"
        )

        n_samples = 6
        temperature = 0.7

        raw_responses = self.llm(
            prompt,
            system=self._system_prompt,
            temperature=temperature,
            n=n_samples,
        )

        if isinstance(raw_responses, str):
            raw_responses = [raw_responses]

        candidates = []
        for text in raw_responses:
            sql = bridge.extract_sql(text)
            if not sql:
                continue
            sql = sql.strip()
            if sql.endswith(";"):
                sql = sql[:-1].strip()
            if sql and sql not in candidates:
                candidates.append(sql)

        if not candidates:
            fallback = bridge.extract_sql(raw_responses[0])
            if fallback:
                if fallback.endswith(";"):
                    fallback = fallback[:-1]
                return fallback.strip()
            return "SELECT 1"

        best_sql = None
        best_score = -1

        for sql in candidates:
            res = self.execute(sql)
            if not res.get("ok"):
                continue
            rows = res.get("rows") or []
            non_null_rows = 0
            for row in rows:
                if any(v is not None for v in row):
                    non_null_rows += 1
            score = non_null_rows
            if score > best_score:
                best_score = score
                best_sql = sql

        if best_sql is None:
            for sql in candidates:
                res = self.execute(sql)
                if res.get("ok"):
                    best_sql = sql
                    break

        if best_sql is None:
            best_sql = candidates[0]

        return best_sql