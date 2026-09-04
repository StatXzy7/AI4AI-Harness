"""Repair-loop Text-to-SQL harness: a greedy SQL draft is executed against the database, and any execution error is fed back to the frozen solver for up to two corrective regenerations."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G4(SQLHarness):
    """Execute-verified repair loop around the frozen text-to-SQL solver.

    Control flow of ``solve``:

    1. A greedy first draft is generated from (schema, question).
    2. The draft is executed against the database via ``self.execute``.
    3. If execution fails, the offending SQL together with the database error
       message is recorded, and the solver is re-prompted with the full failure
       history so it can emit a corrected statement (up to ``MAX_ATTEMPTS``
       LLM calls in total). Later repair prompts therefore consume the error
       artifacts produced by earlier executions.
    4. The first statement that executes cleanly is returned immediately. If
       every attempt fails, the most recent (i.e. most-repaired) candidate is
       returned.
    """

    MAX_ATTEMPTS = 3          # 1 initial draft + up to 2 repair rounds
    REPAIR_TEMPERATURE = 0.4  # nudge the solver off a stuck, failing answer
    MAX_ERROR_CHARS = 400     # truncation budget for error text in prompts

    # ---------------------------------------------------------------- prompts

    def _system_prompt(self) -> str:
        return (
            "You are an expert text-to-SQL engine. Given a database schema and a "
            "natural-language question, you output exactly one SQLite SELECT "
            "statement and nothing else."
        )

    def _schema_text(self) -> str:
        schema = getattr(self, "schema", None)
        if schema is None:
            return "(no schema provided)"
        return str(schema).strip() or "(empty schema)"

    def _draft_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self._schema_text()}\n\n"
            "Task: write one SQLite SELECT statement that answers the question.\n"
            "Constraints:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- The statement is executed as-is, so it must be directly runnable.\n"
            "- Output the SQL alone: no prose, no markdown fences, no comments.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, failures) -> str:
        lines = [
            "Database schema:",
            "----------------",
            self._schema_text(),
            "",
            f"Question: {question}",
            "",
            "Your previous SQL statements were executed against the database and "
            "each one failed. The full failure history follows:",
            "",
        ]
        for idx, (sql, error) in enumerate(failures, start=1):
            error = (error or "unknown execution error").strip()
            if len(error) > self.MAX_ERROR_CHARS:
                error = error[: self.MAX_ERROR_CHARS] + " [...truncated]"
            lines.append(f"--- attempt {idx} ---")
            lines.append(f"SQL: {sql}")
            lines.append(f"DATABASE ERROR: {error}")
            lines.append("")
        lines.append(
            "Write ONE corrected SQLite SELECT statement that avoids every error "
            "listed above. Re-check table names, column names, join keys and "
            "quoting against the schema, and prefer simpler SQL that you are "
            "certain executes. Output the SQL alone."
        )
        lines.append("SQL:")
        return "\n".join(lines)

    # -------------------------------------------------------------- internals

    def _generate(self, prompt: str, temperature: float) -> str:
        out = self.llm(
            prompt,
            system=self._system_prompt(),
            temperature=temperature,
            n=1,
        )
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        return out.strip()

    def _run(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: the repair loop must never crash
            return {"ok": False, "rows": [], "error": f"executor raised: {exc}"}
        if not isinstance(result, dict):
            return {
                "ok": False,
                "rows": [],
                "error": f"unexpected executor result: {result!r}",
            }
        return result

    # ------------------------------------------------------------------ entry

    def solve(self, question: str) -> str:
        question = (question or "").strip()

        failures = []      # [(sql, error)] -- grows, shown to every repair prompt
        seen_failed = set()  # SQL strings already proven to fail execution
        candidates = []    # every extracted SQL statement, in generation order

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if attempt == 1:
                prompt = self._draft_prompt(question)
                temperature = 0.0
            else:
                prompt = self._repair_prompt(question, failures)
                temperature = self.REPAIR_TEMPERATURE

            raw = self._generate(prompt, temperature)
            sql = bridge.extract_sql(raw).strip()

            if not sql:
                snippet = raw[: self.MAX_ERROR_CHARS] or "<empty model response>"
                failures.append(
                    (snippet, "no SQL statement could be extracted from the model output")
                )
                continue

            if sql in seen_failed:
                # The solver is stuck repeating an already-failing statement;
                # further rounds would add no new information.
                break

            candidates.append(sql)
            result = self._run(sql)

            if result.get("ok"):
                return sql

            error = (result.get("error") or "execution failed").strip()
            failures.append((sql, error))
            seen_failed.add(sql)

        # Nothing executed cleanly: return the most recent (most-repaired)
        # candidate, or the last raw output if extraction never succeeded.
        if candidates:
            return candidates[-1]
        if failures:
            return failures[-1][0]
        return ""