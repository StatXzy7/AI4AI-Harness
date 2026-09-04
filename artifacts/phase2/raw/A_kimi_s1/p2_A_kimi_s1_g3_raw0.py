"""Iterative SQL repair loop: generate a candidate, execute it, and feed database errors (or empty results) back into the prompt for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G3(SQLHarness):
    """Execution-feedback repair harness for the frozen weak solver.

    Instead of trusting a single greedy generation, the harness executes
    every candidate query against the database. Hard failures (database
    errors) are appended to the prompt together with the offending SQL, and
    the LLM is asked to produce a corrected query; this repeats for a
    bounded number of rounds with slowly escalating temperature so a weak
    model can escape repeated mistakes. A query that executes but returns
    zero rows is treated as a soft failure and gets exactly one
    reconsideration attempt, while the executable original is kept as the
    fallback unless the retry is strictly better.
    """

    MAX_ROUNDS = 4  # executions of a candidate before giving up

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL assistant. Given a database schema "
        "and a natural-language question, produce one valid SQL query that "
        "answers the question. Output only the SQL, with no explanations."
    )

    # ------------------------------------------------------------------ #
    # main control flow
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        prompt = (
            "Database schema:\n" + self.schema +
            "\n\nQuestion: " + question +
            "\n\nWrite a single SQL query that answers the question."
        )

        candidate = self._gen(prompt, temperature=0.0)
        if not candidate:
            return ""

        failed = set()  # queries already proven broken by the database
        for attempt in range(1, self.MAX_ROUNDS + 1):
            outcome = self._run(candidate)

            if outcome["ok"]:
                if outcome["rows"]:
                    return candidate
                # ---- soft failure: valid SQL, zero rows ----
                reconsider = (
                    "\n\nThe query:\n" + candidate +
                    "\nexecuted successfully but returned zero rows. This "
                    "often means a filter value does not match the data "
                    "(wrong literal, casing, or an over-restrictive JOIN/"
                    "WHERE). Re-check the predicates against the schema and "
                    "the question, then output only the corrected SQL "
                    "query. If you are certain it is correct, output it "
                    "unchanged."
                )
                retry = self._gen(prompt + reconsider, temperature=0.3)
                if retry and retry != candidate and retry not in failed:
                    r2 = self._run(retry)
                    if r2["ok"] and r2["rows"]:
                        return retry
                return candidate  # executable original stays the fallback

            # ---- hard failure: feed the database error back ----
            failed.add(candidate)
            prompt += (
                "\n\nThe SQL query:\n" + candidate +
                "\nfailed to execute with this database error:\n" +
                outcome["error"] +
                "\nFix the query so it is valid for the schema above. "
                "Output only the corrected SQL query."
            )
            temperature = min(0.2 * attempt, 0.6)
            candidate = self._gen(prompt, temperature)
            if not candidate:
                break
            # The weak solver sometimes repeats the exact broken query;
            # force one hotter redraw when that happens.
            if candidate in failed:
                redraw = self._gen(prompt, min(temperature + 0.3, 1.0))
                if redraw and redraw not in failed:
                    candidate = redraw

        return candidate  # best remaining guess after exhausting repairs

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _gen(self, prompt: str, temperature: float) -> str:
        """Call the frozen LLM and extract a clean SQL string."""
        try:
            raw = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=temperature,
                n=1,
            )
        except Exception:
            return ""
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        raw = raw or ""
        sql = (bridge.extract_sql(raw) or "").strip()
        return sql or raw.strip()

    def _run(self, sql: str) -> dict:
        """Execute SQL defensively, normalizing the result dict."""
        try:
            out = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "execute() raised: " + str(exc)}
        return {
            "ok": bool(out.get("ok")),
            "rows": out.get("rows") or [],
            "error": str(out.get("error", "unknown error")).strip(),
        }