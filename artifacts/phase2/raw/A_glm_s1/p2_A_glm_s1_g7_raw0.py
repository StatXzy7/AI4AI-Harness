"""Repair loop: greedily generate SQL, execute it against the database, and feed SQLite errors (or empty result sets) back into the prompt for up to three corrective regenerations."""

# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G7(SQLHarness):
    """Execution-guided self-repair wrapped around a frozen weak solver.

    Control flow per question:
      1. ask the solver for one SELECT statement (greedy, temperature 0),
      2. run it on the real database via ``self.execute``,
      3. if SQLite raises an error -- or the query runs but returns zero rows --
         append that execution feedback to the prompt and ask the solver to
         regenerate, while remembering the best query seen so far,
      4. stop on the first query that executes and returns rows, on a repeated
         "stuck" answer, or after ``MAX_ROUNDS`` repair rounds.

    A query that executed cleanly is never traded for a worse one: the best
    candidate is ranked (rows > empty > error) and returned at the end.
    """

    name = "P2P2AGlmS1G7"

    MAX_ROUNDS = 3    # corrective regenerations after the first attempt
    MAX_FEEDBACK = 3  # execution-feedback notes kept in the prompt

    RANK_ROWS = 2     # executed and returned at least one row
    RANK_EMPTY = 1    # executed fine but returned zero rows
    RANK_ERROR = 0    # SQLite refused to run it

    SYSTEM = (
        "You are an expert SQLite analyst. Translate the question into exactly one "
        "SQLite SELECT statement that uses only tables and columns from the given "
        "schema. Reply with the SQL alone: no prose, no markdown fences."
    )

    # ------------------------------------------------------------------ api

    def solve(self, question: str) -> str:
        feedback = []                  # execution-feedback notes, newest last
        best_sql, best_rank = "", -1   # best query found so far
        prev_key = None                # (normalised sql, rank) of previous attempt

        for _round in range(self.MAX_ROUNDS + 1):
            prompt = self._build_prompt(question, feedback)

            text = self._call_llm(prompt)
            sql = self._clean(bridge.extract_sql(text))

            if not sql:
                feedback.append(
                    "Attempt %d: no SQL statement could be extracted from your reply. "
                    "Answer with a single SELECT statement and nothing else."
                    % (len(feedback) + 1)
                )
                continue

            result = self._run(sql)

            if result.get("ok") and (result.get("rows") or []):
                # Executable and non-empty: ship it immediately.
                return sql

            if result.get("ok"):
                rank = self.RANK_EMPTY
                note = (
                    "Attempt %d: the query ran without error but returned 0 rows:\n%s\n"
                    "If the empty answer is genuinely correct, restate this exact query "
                    "unchanged; otherwise fix values, comparison operators, joins or "
                    "spurious conditions that filter out every row."
                    % (len(feedback) + 1, sql)
                )
            else:
                rank = self.RANK_ERROR
                note = (
                    "Attempt %d: SQLite refused to run the query:\n%s\nError: %s"
                    % (
                        len(feedback) + 1,
                        sql,
                        (result.get("error") or "unknown execution error").strip(),
                    )
                )

            # Never trade a working query for a worse one.
            if rank > best_rank:
                best_sql, best_rank = sql, rank

            # Stuck detection: identical answer at identical quality -> stop
            # burning LLM calls on it.
            key = (self._norm(sql), rank)
            if key == prev_key:
                break
            prev_key = key

            feedback.append(note)

        return best_sql or "SELECT 1;"

    # ------------------------------------------------------------- helpers

    def _build_prompt(self, question: str, feedback) -> str:
        """Assemble schema + question (+ accumulated execution feedback)."""
        lines = [
            "Database schema:",
            (self.schema or "").strip(),
            "",
            "Question: %s" % question.strip(),
        ]
        if feedback:
            lines.append("")
            lines.append(
                "Execution feedback on your earlier attempts "
                "(do not repeat these mistakes):"
            )
            lines.extend(feedback[-self.MAX_FEEDBACK:])
            lines.append("")
            lines.append(
                "Write one corrected SQLite SELECT query. Output only the SQL."
            )
        else:
            lines.append("")
            lines.append(
                "Write one SQLite SELECT query that answers the question. "
                "Output only the SQL."
            )
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> str:
        """Call the frozen solver defensively; always return a string."""
        try:
            text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(text, list):        # tolerate list-returning bridges
            text = text[0] if text else ""
        return text if isinstance(text, str) else ""

    def _run(self, sql: str) -> dict:
        """Execute ``sql`` and normalise the executor's answer."""
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if isinstance(result, dict):
            return result
        return {"ok": False, "rows": [], "error": "executor returned %r" % (result,)}

    @staticmethod
    def _clean(sql: str) -> str:
        """Keep the first statement, drop fences/whitespace/trailing ';'."""
        if not sql:
            return ""
        s = sql.strip()
        if ";" in s:
            head = s.split(";", 1)[0].strip()
            if head:
                s = head
        return s

    @staticmethod
    def _norm(sql: str) -> str:
        """Whitespace/case-insensitive form for stuck detection."""
        return " ".join((sql or "").split()).lower()