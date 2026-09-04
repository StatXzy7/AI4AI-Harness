"""Repair-style harness: generate SQL, execute it, and iteratively feed execution errors (and empty results) back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G5(SQLHarness):
    """Generate SQL, execute it, and repair it in a closed feedback loop.

    Control flow:
      1. Greedy generation of an initial SQL query from schema + question.
      2. Execute the candidate against the real database.
      3. On success with non-empty rows: return immediately.
      4. On execution error (or suspicious empty result): append the failing
         SQL plus the database's error message to a feedback transcript and
         re-prompt the LLM to produce a corrected query.
      5. Repeat until success or the attempt budget is exhausted; always
         return the most recent candidate so the harness never fails hard.
    """

    MAX_ATTEMPTS = 5
    MAX_ERROR_CHARS = 600

    def _generate(self, prompt: str, system: str) -> str:
        """Call the frozen LLM and normalize its return type to a string."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _to_sql(self, raw_text: str) -> str:
        """Extract a clean SQL string from raw model output."""
        sql = bridge.extract_sql(raw_text)
        if not sql:
            sql = raw_text.strip()
        return sql.strip().rstrip(";") + ";" if sql and not sql.strip().endswith(";") else sql

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQL developer. Given a database schema and a "
            "natural-language question, write one correct SQL query. "
            "When shown a previous failing query and the database error, fix "
            "the specific problem (table/column names, joins, grouping, syntax) "
            "instead of rewriting blindly. Output only the SQL query."
        )

        base = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )

        feedback = []  # list of (failing_sql, diagnostic) pairs
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            if not feedback:
                prompt = base
            else:
                transcript_parts = []
                for i, (bad_sql, diagnostic) in enumerate(feedback, start=1):
                    transcript_parts.append(
                        f"--- Attempt {i} ---\n"
                        f"SQL:\n{bad_sql}\n"
                        f"Database feedback:\n{diagnostic}\n"
                    )
                transcript = "\n".join(transcript_parts)
                prompt = (
                    f"{base}\n\n"
                    "Your previous attempts failed when executed against the "
                    "database. Here is the execution feedback:\n\n"
                    f"{transcript}\n"
                    "Rewrite the query so it executes correctly and answers the "
                    "question. Output only the corrected SQL query."
                )

            raw = self._generate(prompt, system)
            candidate = self._to_sql(raw)
            if not candidate:
                feedback.append((raw[:200] or "(empty output)", "Model produced no SQL."))
                continue

            # Avoid burning attempts on an identical repeat of a failed query.
            if feedback and candidate == feedback[-1][0]:
                candidate = candidate  # still execute once; DB is source of truth

            last_sql = candidate
            result = self.execute(candidate)

            if result.get("ok"):
                rows = result.get("rows")
                if rows:
                    return candidate
                # Executable but empty: treat as a soft failure worth one repair,
                # unless we are out of budget.
                if attempt < self.MAX_ATTEMPTS - 1:
                    feedback.append(
                        (
                            candidate,
                            "Query executed successfully but returned ZERO rows. "
                            "Re-check filter values (exact string matches), join "
                            "conditions, and WHERE clauses; relax overly strict "
                            "predicates if appropriate.",
                        )
                    )
                    continue
                return candidate

            # Hard failure: feed the real database error back for repair.
            error = str(result.get("error", "unknown execution error"))
            if len(error) > self.MAX_ERROR_CHARS:
                error = error[: self.MAX_ERROR_CHARS] + "..."
            feedback.append((candidate, error))

        return last_sql