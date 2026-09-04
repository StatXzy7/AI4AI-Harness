"""Two-view Text-to-SQL harness: draft the question as a join-based and a subquery-based SQL, execute both, and return the first formulation whose execution yields a non-empty result set."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1TwoView(SQLHarness):
    """Wraps the frozen weak solver with a two-view generation / execution filter.

    Control flow:
      1. Ask the frozen solver for a JOIN-based formulation of the query.
      2. Independently ask it for a subquery-based formulation.
      3. Execute both candidate SQL strings against the database.
      4. Return the first candidate whose execution succeeds and yields a
         non-empty result set; if both are non-empty, the first (join-based)
         one wins. Degrade gracefully to "executes at all", then to "any
         non-empty draft".
    """

    JOIN_SYSTEM = (
        "You are an expert SQLite engineer. Translate the user's question into a "
        "single SQL query. Formulate it explicitly with JOIN ... ON clauses between "
        "the relevant tables whenever more than one table is involved. Use only "
        "tables and columns that appear in the provided schema. Output only the SQL."
    )

    SUBQUERY_SYSTEM = (
        "You are an expert SQLite engineer. Translate the user's question into a "
        "single SQL query. Formulate it with nested subqueries (e.g. WHERE col IN "
        "(SELECT ...)) instead of explicit JOIN clauses whenever more than one "
        "table is involved. Use only tables and columns that appear in the "
        "provided schema. Output only the SQL."
    )

    def solve(self, question: str) -> str:
        # View 1: join-based formulation.
        join_sql = self._draft(
            question,
            system=self.JOIN_SYSTEM,
            style_hint="join-based (use explicit JOIN ... ON clauses)",
        )
        # View 2: independent subquery-based formulation.
        sub_sql = self._draft(
            question,
            system=self.SUBQUERY_SYSTEM,
            style_hint="subquery-based (use nested SELECTs instead of JOINs)",
        )

        # Execute both formulations (reusing the result if both views coincide).
        join_result = self._run(join_sql)
        if sub_sql and sub_sql == join_sql:
            sub_result = join_result
        else:
            sub_result = self._run(sub_sql)

        # Primary rule: return the first formulation with a non-empty result.
        if self._non_empty(join_result):
            return join_sql
        if self._non_empty(sub_result):
            return sub_sql

        # Secondary rule: both empty (or failed) -- prefer one that at least runs.
        if join_result.get("ok") and join_sql:
            return join_sql
        if sub_result.get("ok") and sub_sql:
            return sub_sql

        # Last resort: hand back whichever draft exists.
        return join_sql or sub_sql or ""

    # ------------------------------------------------------------------ helpers

    def _draft(self, question: str, system: str, style_hint: str) -> str:
        """Ask the frozen solver for one formulation and extract clean SQL."""
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a single {style_hint} SQL query that answers the question. "
            f"Do not explain anything; output only the SQL query."
        )
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system=system)
            except Exception:
                return ""
        except Exception:
            return ""

        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        try:
            return bridge.extract_sql(str(response))
        except Exception:
            return ""

    def _run(self, sql: str) -> dict:
        """Execute a candidate, normalizing failures into the result dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "empty draft"}
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: executor itself blew up
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "malformed executor result"}
        return result

    @staticmethod
    def _non_empty(result: dict) -> bool:
        """True iff execution succeeded and returned at least one row."""
        return bool(result.get("ok")) and bool(result.get("rows"))