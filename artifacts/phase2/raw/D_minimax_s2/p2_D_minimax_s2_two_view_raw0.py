"""Harness that generates SQL via two independent formulations (prompt A and prompt B), executes both, and prefers the one yielding a non-empty result set."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2TwoView(SQLHarness):
    PROMPT_A_TEMPLATE = (
        "Given the following database schema:\n"
        "{schema}\n"
        "Write a single, valid SQL query that answers the question using explicit JOINs "
        "between the relevant tables wherever possible.\n"
        "Question: {question}\n"
        "Return ONLY the SQL statement, with no prose, no code fences, and no trailing commentary."
    )

    PROMPT_B_TEMPLATE = (
        "Given the following database schema:\n"
        "{schema}\n"
        "Write a single, valid SQL query that answers the question. Prefer a formulation that uses "
        "subqueries (e.g. IN / EXISTS / scalar SELECTs) rather than broad JOINs when both approaches "
        "are viable.\n"
        "Question: {question}\n"
        "Return ONLY the SQL statement, with no prose, no code fences, and no trailing commentary."
    )

    SYSTEM = (
        "You are a precise Text-to-SQL generator. Output exactly one syntactically valid "
        "SQL statement and nothing else."
    )

    def _make_sql_candidates(self, question: str) -> list[str]:
        """Generate two candidate SQL strings from independent prompts."""
        prompt_a = self.PROMPT_A_TEMPLATE.format(schema=self.schema, question=question)
        prompt_b = self.PROMPT_B_TEMPLATE.format(schema=self.schema, question=question)

        raw_a = self.llm(prompt_a, system=self.SYSTEM, temperature=0.0, n=1)
        raw_b = self.llm(prompt_b, system=self.SYSTEM, temperature=0.0, n=1)

        candidates: list[str] = []
        sql_a = bridge.extract_sql(raw_a)
        sql_b = bridge.extract_sql(raw_b)
        if sql_a:
            candidates.append(sql_a)
        if sql_b:
            candidates.append(sql_b)
        return candidates

    def solve(self, question: str) -> str:
        candidates = self._make_sql_candidates(question)

        if not candidates:
            return ""

        first_sql = candidates[0]
        first_result = self.execute(first_sql)

        if len(candidates) >= 2:
            second_sql = candidates[1]
            second_result = self.execute(second_sql)

            ok_first = bool(first_result.get("ok"))
            ok_second = bool(second_result.get("ok"))

            # Prefer the result that executed successfully and is non-empty.
            if ok_first and first_result.get("rows"):
                if ok_second and second_result.get("rows"):
                    # Both succeeded and produced rows: keep the first per strategy.
                    return first_sql
                # First wins if second failed or was empty.
                return first_sql

            if ok_second and second_result.get("rows"):
                # Second is non-empty; first was not usable -> fall through to second.
                return second_sql

            # Neither produced usable rows: if the first executed ok, keep it,
            # otherwise fall back to the second if it executed ok.
            if ok_first:
                return first_sql
            if ok_second:
                return second_sql

            # Both failed: return the first (preferred) so the caller can debug.
            return first_sql

        # Only one candidate was extracted.
        return first_sql