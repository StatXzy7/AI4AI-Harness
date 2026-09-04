"""Execution-guided repair harness: generate SQL, run it, and feed database errors (or empty results) back for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G0(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Control flow:
      1. Greedy-generate an initial SQL query from the schema + question.
      2. Execute the candidate against the database.
      3. On a database error (or when the model emits no SQL), build a
         repair prompt containing the failing SQL, the exact error message,
         and the full failure history, then regenerate.
      4. Accept the first query that executes and returns rows. A query
         that executes cleanly but returns zero rows triggers one skeptical
         repair round (over-restrictive predicates are a common failure
         mode) while being kept as a safe fallback.
      5. Bounded to MAX_ATTEMPTS total generations; never returns SQL that
         was observed to crash if a cleaner alternative exists.
    """

    MAX_ATTEMPTS = 5

    SYSTEM = (
        "You are an expert SQLite text-to-SQL engine. "
        "You output exactly one valid SQLite query and nothing else."
    )

    # ------------------------------------------------------------------
    # Defensive plumbing around the frozen solver's API
    # ------------------------------------------------------------------

    def _generate(self, prompt, temperature=0.0):
        """Call the frozen LLM and normalize its return type to str."""
        try:
            out = self.llm(
                prompt, system=self.SYSTEM, temperature=temperature, n=1
            )
        except TypeError:
            out = self.llm(prompt)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _extract(self, raw_text):
        """Extract SQL from raw model text, tolerating extractor failures."""
        try:
            sql = bridge.extract_sql(raw_text)
        except Exception:
            sql = ""
        if not sql:
            sql = (raw_text or "").strip()
        return (sql or "").strip()

    def _run(self, sql):
        """Execute SQL, converting exceptions into a uniform result dict."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: executor itself blew up
            return {"ok": False, "rows": [], "error": "executor exception: %s" % exc}
        return result if isinstance(result, dict) else {"ok": False, "rows": [], "error": "bad executor result"}

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _initial_prompt(self, question):
        return (
            "Write a single SQLite query that answers the question.\n"
            "Rules: use only tables and columns that appear in the schema; "
            "output ONLY the SQL (no prose, no markdown fences).\n\n"
            "### Database schema\n"
            f"{self.schema}\n\n"
            "### Question\n"
            f"{question}\n\n"
            "### SQL"
        )

    def _repair_prompt(self, question, failures, note=None):
        lines = [
            "A previously generated SQLite query for this question did not "
            "work. Produce one corrected SQLite query.",
            "",
            "### Database schema",
            self.schema,
            "",
            "### Question",
            question,
            "",
            "### Failed attempt(s)",
        ]
        for i, (bad_sql, err) in enumerate(failures, 1):
            lines.append(f"-- Attempt {i} SQL:")
            lines.append(bad_sql.strip() or "<empty output>")
            lines.append(f"-- Attempt {i} outcome: {err}")
            lines.append("")
        if note:
            lines.append("### Additional note")
            lines.append(note)
            lines.append("")
        lines += [
            "### Instructions",
            "Diagnose the root cause of the failure(s) above and fix it. "
            "Do not repeat any previous failing query verbatim. "
            "Output ONLY the corrected SQL.",
            "",
            "### SQL",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def solve(self, question: str) -> str:
        failures = []        # [(sql, outcome_description), ...]
        fallback_sql = None  # executes OK but returned zero rows
        last_sql = ""

        prompt = self._initial_prompt(question)
        for attempt in range(self.MAX_ATTEMPTS):
            # First shot is greedy; repairs get a little sampling diversity.
            temperature = 0.0 if attempt == 0 else 0.2
            sql = self._extract(self._generate(prompt, temperature=temperature))

            if not sql:
                failures.append(("<none>", "model produced no SQL"))
                prompt = self._repair_prompt(question, failures)
                continue

            last_sql = sql
            result = self._run(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql  # executed with a non-empty result: accept
                if fallback_sql is None:
                    # Zero rows: possibly correct, possibly over-filtered.
                    fallback_sql = sql
                    note = (
                        "The query executed successfully but returned ZERO "
                        "rows. This may be legitimate, but check for overly "
                        "restrictive JOIN/WHERE conditions, wrong literal "
                        "values, case-sensitivity mismatches, or filtering "
                        "on the wrong column. If the logic is sound, return "
                        "the same query again."
                    )
                    failures.append((sql, "executed OK but returned 0 rows"))
                    prompt = self._repair_prompt(question, failures, note=note)
                    continue
                # We already hold an empty-result fallback; another clean
                # empty execution confirms it, so stop here.
                return sql

            # Hard database error -> classic repair round.
            error = result.get("error") or "unknown execution error"
            failures.append((sql, error))
            prompt = self._repair_prompt(question, failures)

        # Prefer a query that at least executed over one that crashed.
        if fallback_sql is not None:
            return fallback_sql
        return last_sql or "SELECT 1"