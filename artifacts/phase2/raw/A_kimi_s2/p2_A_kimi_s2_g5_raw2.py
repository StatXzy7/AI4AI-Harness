"""Execution-feedback repair harness: greedily generate SQL, execute it, and feed any database error back to the frozen solver for iterative correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G5(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Control flow:
      1. Greedily generate an initial SQL candidate from (schema, question).
      2. Execute the candidate against the real database.
      3. On success, return it immediately.
      4. On failure, record the (sql, error) pair and build a repair prompt
         containing the schema, the question, and the recent failure history;
         the frozen solver is asked for a corrected query. A small temperature
         ramp on successive repairs helps the frozen model escape repeated
         mistakes that greedy decoding would otherwise reproduce verbatim.
      5. Repeat until a query executes or the attempt budget is exhausted;
         return the best candidate seen (never an empty string).
    """

    MAX_ATTEMPTS = 4                       # 1 initial shot + up to 3 repairs
    REPAIR_TEMPERATURES = (0.0, 0.3, 0.6)  # ramp used on repair rounds

    # ------------------------------------------------------------------ #
    # main entry point                                                    #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL engine. "
            "You always answer with exactly one SQL query and nothing else."
        )

        base_prompt = (
            "Write a single SQLite SQL query that answers the question.\n\n"
            "Database schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "Rules:\n"
            "- Output ONLY the SQL query: no markdown fences, no explanation.\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Qualify column names with their table when they are ambiguous.\n"
            "- Make sure every JOIN uses matching key columns.\n"
        )

        # ---- stage 1: single greedy generation -------------------------
        sql = self._generate(base_prompt, system, temperature=0.0)
        best = sql
        failures = []  # [(sql, error), ...] fed back into repair prompts

        # ---- stage 2: execute -> feed error back -> regenerate ---------
        for attempt in range(self.MAX_ATTEMPTS):
            if not sql:
                # Parser recovered nothing: re-ask firmly (still in budget).
                sql = self._generate(
                    base_prompt + "\nREMINDER: raw SQL only, no prose, no code fences.\n",
                    system,
                    temperature=0.2,
                )
                if sql:
                    best = sql
                continue

            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: a crash counts as an error
                result = {"ok": False, "rows": [], "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                return sql  # executed successfully -> done

            error = (
                str(result.get("error", "unknown execution error"))
                if isinstance(result, dict)
                else "execute() returned an unreadable result"
            )
            failures.append((sql, error))

            if attempt + 1 >= self.MAX_ATTEMPTS:
                break  # no budget left for another regeneration

            repaired = self._generate(
                self._repair_prompt(question, failures),
                system,
                temperature=self.REPAIR_TEMPERATURES[
                    min(attempt, len(self.REPAIR_TEMPERATURES) - 1)
                ],
            )
            if not repaired:
                break  # solver gave us nothing usable; stop and keep best
            sql = repaired
            best = repaired

        # best-effort fallback: always return a non-empty SQL string
        return best if best else "SELECT 1"

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        """Call the frozen solver once and normalize its output to SQL text."""
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):  # tolerate list-returning backends
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        return (bridge.extract_sql(out) or "").strip()

    def _repair_prompt(self, question: str, failures) -> str:
        """Build a prompt that feeds execution errors back for regeneration."""
        history = []
        for idx, (bad_sql, err) in enumerate(failures[-3:], start=1):
            history.append(
                "Failed attempt {n} SQL:\n{sql}\n"
                "Database error for attempt {n}:\n{err}\n".format(
                    n=idx, sql=bad_sql, err=err
                )
            )
        return (
            "A SQL query written for this task failed to execute. Repair it.\n\n"
            "Database schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            + "\n".join(history) + "\n"
            "Diagnose the error and write ONE corrected SQLite query.\n"
            "Common fixes: reference only columns/tables that exist in the "
            "schema, qualify ambiguous columns with their table name, verify "
            "JOIN keys actually match, and check string literals and casing "
            "used in WHERE clauses. Do NOT repeat the failing query.\n"
            "Output ONLY the corrected SQL: no markdown, no explanation."
        )