"""Execute-then-classify repair harness: generate SQL, run it, label each failure as syntax, schema, or semantics, and apply a class-specific fix for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2ErrorClassify(SQLHarness):
    """Wrap the frozen weak solver in an execute -> classify -> targeted-repair loop.

    The failure taxonomy is implemented in the control flow, not just the prompt:
      * syntax    -> parser/grammar error: re-prompt quoting the engine error and
                     fix only the SQL grammar, preserving intent.
      * schema    -> unknown/ambiguous table, column, or function: re-prompt with
                     the full schema and remap every identifier to it.
      * semantics -> engine-ambiguous errors, or a query that executes but returns
                     zero rows: re-prompt to re-check the logic (joins, filters,
                     aggregation, GROUP BY, ORDER BY/LIMIT).
    At most MAX_REPAIR_ROUNDS repairs are performed; repeated identical candidates
    trigger one forced-alternative retry and then an early stop.
    """

    MAX_REPAIR_ROUNDS = 2

    # Engine-error keyword hints for deterministic classification (checked
    # schema-first because name-resolution messages are unambiguous).
    _SCHEMA_HINTS = (
        "no such table",
        "no such column",
        "no column named",
        "unknown column",
        "unknown table",
        "ambiguous column",
        "does not exist",
        "no such function",
        "unknown function",
        "invalid column",
        "not found",
    )
    _SYNTAX_HINTS = (
        "syntax error",
        "unrecognized token",
        "unexpected token",
        "near \"",
        "near '",
        "unterminated",
        "incomplete input",
        "parse error",
        "malformed",
    )

    # ------------------------------------------------------------------ solve --
    def solve(self, question: str) -> str:
        sql = self._initial_sql(question)
        if not sql:
            return "SELECT 1"  # degenerate fallback: always executable

        best_empty_sql = None  # last candidate that ran but returned 0 rows
        tried = set()

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._run(sql)

            if result.get("ok"):
                if result.get("rows"):
                    return sql  # executed and produced data: success
                # Executed cleanly but empty -> treat as a semantic failure.
                best_empty_sql = sql
                category = "semantics"
                detail = (
                    "The query executed successfully but returned 0 rows, which "
                    "suggests its filters/joins may not match the question."
                )
            else:
                detail = result.get("error") or "unknown execution error"
                category = self._classify(detail, sql, question)

            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break  # repair budget exhausted

            tried.add(sql.strip())
            fixed = self._repair(question, sql, category, detail)
            if not fixed or fixed.strip() in tried:
                # The frozen model repeated itself: demand a different candidate.
                fixed = self._repair(question, sql, category, detail,
                                     force_different=True)
            if not fixed or fixed.strip() in tried:
                break  # no new candidate available; stop early
            sql = fixed

        # Best-effort return: prefer a candidate that at least executed.
        if self._run(sql).get("ok"):
            return sql
        return best_empty_sql if best_empty_sql is not None else sql

    # ------------------------------------------------------------- generation --
    def _initial_sql(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL generator for SQLite. "
            "Return exactly one SQL query and nothing else."
        )
        prompt = (
            "Database schema:\n" + self.schema +
            "\n\nQuestion: " + question +
            "\n\nWrite one SQLite query that answers the question."
        )
        sql = self._sql_from(self._ask(prompt, system=system))
        if not sql:
            # One plain retry if the model produced nothing SQL-like.
            sql = self._sql_from(self._ask(
                "Schema:\n" + self.schema + "\n\nQuestion: " + question +
                "\n\nRespond with only the SQL query.",
                system="You output SQL only.",
            ))
        return sql

    # ---------------------------------------------------------- classification --
    def _classify(self, error: str, sql: str, question: str) -> str:
        e = (error or "").lower()
        if any(h in e for h in self._SCHEMA_HINTS):
            return "schema"
        if any(h in e for h in self._SYNTAX_HINTS):
            return "syntax"
        # Engine-ambiguous error: let the frozen model label it.
        system = (
            "You classify SQL execution failures into exactly one of three "
            "categories: syntax, schema, semantics. Answer with a single word."
        )
        prompt = (
            "Database schema:\n" + self.schema +
            "\n\nFailed SQL:\n" + sql +
            "\n\nEngine error:\n" + (error or "(none)") +
            "\n\nsyntax = malformed SQL / grammar violation; "
            "schema = unknown or ambiguous table, column, or function name; "
            "semantics = valid SQL whose logic does not answer the question."
            "\nCategory:"
        )
        label = self._ask(prompt, system=system).strip().lower()
        if "schema" in label:
            return "schema"
        if "syntax" in label:
            return "syntax"
        return "semantics"

    # ------------------------------------------------------------------ repair --
    def _repair(self, question: str, sql: str, category: str, detail: str,
                force_different: bool = False) -> str:
        if category == "syntax":
            system = "You repair SQL syntax errors in SQLite queries."
            instruction = (
                "The query has a SYNTAX error. Preserve its intent and structure, "
                "and correct only the grammar so it parses as valid SQLite: check "
                "keywords, parentheses, quotes, commas, and clause ordering."
            )
        elif category == "schema":
            system = "You repair schema-reference errors in SQLite queries."
            instruction = (
                "The query references tables/columns/functions that do not exist "
                "or are ambiguous. Map every identifier to the schema above: use "
                "exact table and column names, add table qualifiers to ambiguous "
                "columns, and remove or replace unknown names."
            )
        else:
            system = "You repair logically wrong SQL queries."
            instruction = (
                "The query is syntactically valid but SEMANTICALLY wrong (it does "
                "not answer the question, e.g. an empty or incorrect result). "
                "Re-read the question and fix the logic: join conditions, WHERE "
                "filters, aggregation and GROUP BY, DISTINCT, ORDER BY/LIMIT, and "
                "the choice of tables and columns."
            )
        if force_different:
            instruction += (
                " Your previous repair returned the identical query, so produce a "
                "genuinely different corrected query."
            )
        prompt = (
            "Database schema:\n" + self.schema +
            "\n\nQuestion: " + question +
            "\n\nPrevious SQL:\n" + sql +
            "\n\nObserved problem (" + category + "):\n" + (detail or "unknown") +
            "\n\n" + instruction +
            "\n\nReturn only the corrected SQL query."
        )
        return self._sql_from(self._ask(prompt, system=system))

    # ----------------------------------------------------------------- helpers --
    def _ask(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            return (out[0] if out else "") or ""
        return out or ""

    def _sql_from(self, text: str) -> str:
        sql = (bridge.extract_sql(text) or "").strip()
        if sql:
            return sql
        # Fallback: accept raw output only if it clearly looks like SQL.
        raw = (text or "").strip()
        if raw.startswith("