"""Generate SQL, execute it, classify each failure as syntax / schema / semantics, and apply a class-specific repair strategy for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0ErrorClassify(SQLHarness):
    """Error-classification Text-to-SQL harness.

    Control flow (the classification lives here, not only in the prompt):
      1. Generate an initial SQL query from (schema, question).
      2. Execute it.
      3. If it runs and returns rows -> done.
      4. Otherwise classify the failure into exactly one class:
           - syntax    : the SQL text is malformed (parser rejects it);
           - schema    : the query references non-existent / ambiguous
                         tables or columns;
           - semantics : the query parses/runs but is logically wrong
                         (runtime logic errors or an empty result set).
      5. Re-prompt the frozen solver with a repair strategy specific to
         the diagnosed class and try again -- at most MAX_REPAIR_ROUNDS
         repairs, then return the best-effort SQL.
    """

    MAX_REPAIR_ROUNDS = 2

    SYNTAX = "syntax"
    SCHEMA = "schema"
    SEMANTICS = "semantics"

    # ------------------------------------------------------------------ #
    # class-specific repair strategies (one per failure class)
    # ------------------------------------------------------------------ #
    _REPAIR_STRATEGIES = {
        SYNTAX: (
            "This is a SYNTAX failure: the SQL text itself is malformed and "
            "the parser rejected it. Do NOT change the query's logic -- keep "
            "the same tables, columns, joins, filters, grouping and "
            "aggregation. Only repair the malformed text: balance parentheses "
            "and quotes, fix keyword spelling and clause order "
            "(SELECT ... FROM ... WHERE ... GROUP BY ... HAVING ... "
            "ORDER BY ... LIMIT), add missing commas/keywords, remove stray "
            "tokens, and make sure the statement is valid SQLite."
        ),
        SCHEMA: (
            "This is a SCHEMA failure: the query mentions tables or columns "
            "that do not exist (or are ambiguous). Re-read the SCHEMA above "
            "carefully: (1) keep only table names that literally appear in "
            "the schema; (2) keep only column names that belong to the table "
            "they are used with -- copy their exact spelling and case; "
            "(3) replace every hallucinated name with the closest real name "
            "from the schema; (4) if a needed value lives in another table, "
            "add the proper JOIN using the key relationships shown in the "
            "schema. Preserve the intended logic of the question."
        ),
        SEMANTICS: (
            "This is a SEMANTICS failure: the query runs, but its logic does "
            "not answer the question (wrong or empty result). Re-derive the "
            "logic from the QUESTION: (1) re-check filter literals -- values "
            "stored in the database may differ in case or format, so match "
            "robustly (e.g. LOWER(col) = LOWER('value') or LIKE) instead of "
            "assuming exact spellings; (2) verify the join keys really relate "
            "the entities the question connects; (3) check aggregation, "
            "GROUP BY / HAVING, DISTINCT, and the direction of ORDER BY "
            "(ASC vs DESC) together with LIMIT; (4) make sure the SELECT "
            "list contains exactly what the question asks for. Rewrite the "
            "query with the corrected logic."
        ),
    }

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)

        history = []  # [{"sql": ..., "cls": ..., "error": ...}, ...]

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            outcome = self.execute(sql)

            if outcome.get("ok"):
                if outcome.get("rows"):
                    return sql  # executed and produced a result -> done
                # Executed cleanly but returned nothing: classify this as a
                # SEMANTICS failure (filters/logic do not match reality).
                cls = self.SEMANTICS
                error = (
                    "Query executed successfully but returned 0 rows; its "
                    "logic probably does not match the question or the data."
                )
            else:
                error = (outcome.get("error") or "unknown execution error").strip()
                cls = self._classify_error(error)

            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break  # repair budget exhausted -> return best-effort SQL

            history.append({"sql": sql, "cls": cls, "error": error})
            sql = self._repair(question, sql, cls, error, history)

        return sql

    # ------------------------------------------------------------------ #
    # step 1: initial generation
    # ------------------------------------------------------------------ #
    def _generate_initial(self, question: str) -> str:
        prompt = (
            "You are given a SQLite database schema and a natural-language "
            "question.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "Write ONE SQLite query that answers the question exactly. "
            "Return only the SQL query, no explanations."
        )
        text = self.llm(
            prompt,
            system="You are an expert Text-to-SQL engine. Output only SQL.",
            temperature=0.0,
        )
        sql = bridge.extract_sql(text)
        return sql if sql else "SELECT 1"

    # ------------------------------------------------------------------ #
    # step 2: programmatic failure classification
    # ------------------------------------------------------------------ #
    @classmethod
    def _classify_error(cls, error: str) -> str:
        e = (error or "").lower()

        # Schema-class signals first (most specific, e.g. SQLite's
        # "no such column: x" / "no such table: y", ambiguous names, ...).
        schema_signals = (
            "no such table", "no such column", "no column named",
            "unknown table", "unknown column", "unknown identifier",
            "invalid column", "ambiguous column", "no such database",
            "does not exist",
        )
        for sig in schema_signals:
            if sig in e:
                return cls.SCHEMA

        # Syntax-class signals (parser / dialect rejections).
        syntax_signals = (
            "syntax error", "unrecognized token", "incomplete input",
            "unterminated", "unexpected token", "expected token",
            "parse error", "parser error", "no such function",
            "unknown function", 'near "', "near '", "syntax",
        )
        for sig in syntax_signals:
            if sig in e:
                return cls.SYNTAX

        # Everything else (misuse of aggregate, datatype mismatch, illegal
        # GROUP BY/HAVING, ...) is a runtime logic problem -> semantics.
        return cls.SEMANTICS

    # ------------------------------------------------------------------ #
    # step 3: class-specific repair
    # ------------------------------------------------------------------ #
    def _repair(self, question: str, bad_sql: str, cls: str,
                error: str, history: list) -> str:
        strategy = self._REPAIR_STRATEGIES[cls]

        earlier = history[:-1]  # attempts before the current one
        previous = ""
        if earlier:
            lines = ["Earlier failed attempts (do NOT repeat them):"]
            for h in earlier:
                lines.append(f"- [{h['cls']}] {h['sql']}  -->  {h['error']}")
            previous = "\n".join(lines) + "\n\n"

        prompt = (
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "The following SQL query FAILED to answer the question.\n\n"
            f"FAILED SQL:\n{bad_sql}\n\n"
            f"DIAGNOSED FAILURE CLASS: {cls.upper()}\n"
            f"ERROR MESSAGE / SYMPTOM:\n{error}\n\n"
            f"{previous}"
            f"REPAIR STRATEGY for a {cls.upper()} failure:\n{strategy}\n\n"
            "Rewrite the query accordingly. Return only the corrected SQL, "
            "no explanations."
        )
        system = (
            "You are an expert SQL debugger. Strictly follow the repair "
            "strategy for the diagnosed failure class. Output only SQL."
        )

        fixed = bridge.extract_sql(
            self.llm(prompt, system=system, temperature=0.0)
        )

        # Guard against the frozen solver echoing the same broken query:
        # retry once with sampling so a genuinely different fix can emerge.
        if not fixed or fixed.strip() == bad_sql.strip():
            fixed = bridge.extract_sql(
                self.llm(prompt, system=system, temperature=0.7)
            )

        return fixed if fixed else bad_sql