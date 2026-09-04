"""Two-view prompt-to-prompt harness: generates two SQL formulations (join-based and subquery-based), executes both, and returns the result with non-empty rows preferring the join-based view."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1TwoView(SQLHarness):
    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------
    @staticmethod
    def _prompt_view_a(question: str, schema: str) -> str:
        return f"""You are an expert SQL writer.

Database schema:
{schema}

Write a single SQL query that answers the question using explicit JOIN
clauses between tables (no correlated subqueries in the SELECT or WHERE).

Rules:
- Use explicit JOIN ... ON syntax for every cross-table relationship.
- Do not use subqueries in SELECT or WHERE; rewrite as joins.
- Return ONLY the SQL statement, with no explanation, no markdown fences.

Question: {question}
SQL:"""

    @staticmethod
    def _prompt_view_b(question: str, schema: str) -> str:
        return f"""You are an expert SQL writer.

Database schema:
{schema}

Write a single SQL query that answers the question using nested
subqueries (no JOIN clauses between tables).

Rules:
- Use WHERE ... IN (SELECT ...) or WHERE EXISTS (SELECT ...) or
  scalar subqueries in SELECT to relate tables.
- Do not use any JOIN keyword.
- Return ONLY the SQL statement, with no explanation, no markdown fences.

Question: {question}
SQL:"""

    # ------------------------------------------------------------------
    # One "view": prompt, generate, extract, execute.  Returns a dict
    # so the caller can pick the winner.
    # ------------------------------------------------------------------
    def _run_view(self, prompt: str, system: str = "") -> dict:
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        if not sql:
            return {"sql": "", "ok": False, "rows": [], "error": "no_sql_extracted",
                    "raw": raw}
        result = self.execute(sql)
        result.setdefault("error", "")
        result.setdefault("rows", [])
        result["sql"] = sql
        result["raw"] = raw
        return result

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        # ---- View A: join-based --------------------------------------
        res_a = self._run_view(self._prompt_view_a(question, schema))

        # ---- View B: subquery-based ----------------------------------
        res_b = self._run_view(self._prompt_view_b(question, schema))

        # ---- Selection logic ----------------------------------------
        # Prefer the formulation whose execution returned rows.
        # If both return rows, View A (join-based) wins -- it is listed first.
        a_rows = res_a.get("rows") or []
        b_rows = res_b.get("rows") or []
        a_ok = bool(res_a.get("ok")) and bool(a_rows)
        b_ok = bool(res_b.get("ok")) and bool(b_rows)

        if a_ok:
            winner = "A"
        elif b_ok:
            winner = "B"
        else:
            # Both empty/errored: fall back to View A's SQL if it produced
            # anything parseable, otherwise View B's SQL, otherwise "".
            winner = "A" if res_a.get("sql") else ("B" if res_b.get("sql") else "A")

        chosen = res_a if winner == "A" else res_b
        return chosen.get("sql") or ""