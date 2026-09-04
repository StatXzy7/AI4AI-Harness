"""Generate SQL, execute it, classify any failure as syntax/schema/semantics via error heuristics with an LLM fallback, and apply a class-specific repair for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2ErrorClassify(SQLHarness):
    """Error-classification-repair harness.

    Control flow:
      1. Generate an initial SQL query from the question and schema.
      2. Execute it; success requires ok=True and at least one row.
      3. On failure, classify the failure as one of
         {syntax, schema, semantics}:
           - engine error mentioning unknown tables/columns -> schema
           - engine error mentioning syntax/parse problems   -> syntax
           - ok execution with zero rows                     -> semantics
           - otherwise, an LLM classifier decides.
      4. Apply a strategy-specific repair prompt for that class.
      5. Repeat for at most MAX_ROUNDS repairs; return the final SQL.
    """

    MAX_ROUNDS = 2

    # ------------------------------------------------------------------
    # main control flow
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)

        for round_idx in range(self.MAX_ROUNDS + 1):
            result = self.execute(sql)
            if self._success(result):
                return sql
            if round_idx >= self.MAX_ROUNDS:
                break
            category = self._classify(question, sql, result)
            sql = self._repair(category, question, sql, result)

        return sql

    # ------------------------------------------------------------------
    # initial generation
    # ------------------------------------------------------------------
    def _generate_initial(self, question: str) -> str:
        system = (
            "You are an expert SQLite developer. Write a single, correct "
            "SQL query answering the user's question. Output only SQL."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question."
        )
        raw = self.llm(prompt, system=system, temperature=0.0)
        return bridge.extract_sql(raw)

    # ------------------------------------------------------------------
    # outcome helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _success(result: dict) -> bool:
        # Treat an empty result set as a (semantic) failure signal so the
        # repair loop gets a chance to reconsider the query logic.
        return bool(result.get("ok")) and bool(result.get("rows"))

    # ------------------------------------------------------------------
    # failure classification
    # ------------------------------------------------------------------
    _SCHEMA_KEYS = (
        "no such column",
        "no such table",
        "no column named",
        "unknown column",
        "unknown table",
        "ambiguous column",
        "has no column",
    )
    _SYNTAX_KEYS = (
        "syntax error",
        "unrecognized token",
        "near ",
        "parse error",
        "unexpected token",
        "incomplete input",
    )

    def _classify(self, question: str, sql: str, result: dict) -> str:
        # Executed cleanly but produced nothing -> wrong logic.
        if result.get("ok"):
            return "semantics"

        error = (result.get("error") or "").lower()
        if any(key in error for key in self._SCHEMA_KEYS):
            return "schema"
        if any(key in error for key in self._SYNTAX_KEYS):
            return "syntax"

        # LLM fallback for ambiguous engine errors.
        system = (
            "You classify SQL failures into exactly one of: syntax, schema, "
            "semantics. Reply with that single word only."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Execution error: {result.get('error')}\n\n"
            "Classify the root cause: syntax (malformed SQL), schema "
            "(wrong or unknown table/column names), or semantics (valid SQL "
            "whose logic does not answer the question)."
        )
        raw = (self.llm(prompt, system=system, temperature=0.0) or "").lower()
        for category in ("syntax", "schema", "semantics"):
            if category in raw:
                return category
        return "semantics"

    # ------------------------------------------------------------------
    # strategy-specific repairs
    # ------------------------------------------------------------------
    def _repair(self, category: str, question: str, sql: str, result: dict) -> str:
        fixers = {
            "syntax": self._repair_syntax,
            "schema": self._repair_schema,
            "semantics": self._repair_semantics,
        }
        fixer = fixers.get(category, self._repair_semantics)
        raw = fixer(question, sql, result)
        fixed = bridge.extract_sql(raw)
        return fixed or sql  # keep previous SQL if extraction fails

    def _repair_syntax(self, question: str, sql: str, result: dict) -> str:
        system = (
            "You are a SQLite syntax repair tool. Fix ONLY the syntax error; "
            "preserve the original logic, tables, and columns. Output only "
            "the corrected SQL."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Faulty SQL:\n{sql}\n\n"
            f"Database error: {result.get('error')}\n\n"
            "Repair the syntax error with the smallest possible edit."
        )
        return self.llm(prompt, system=system, temperature=0.0)

    def _repair_schema(self, question: str, sql: str, result: dict) -> str:
        system = (
            "You are a SQLite schema-alignment tool. The query references "
            "tables or columns that do not exist. Rewrite it using ONLY "
            "names present in the given schema. Output only SQL."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Faulty SQL:\n{sql}\n\n"
            f"Database error: {result.get('error')}\n\n"
            "Identify the unknown table/column named in the error, find the "
            "correct name(s) in the schema above, and rewrite the query. "
            "Do not invent identifiers."
        )
        return self.llm(prompt, system=system, temperature=0.0)

    def _repair_semantics(self, question: str, sql: str, result: dict) -> str:
        if result.get("ok"):
            outcome = (
                "The query executed without error but returned ZERO rows, "
                "so its logic likely does not match the question."
            )
        else:
            outcome = (
                "The query failed with a logic-level error: "
                f"{result.get('error')}"
            )
        system = (
            "You are a SQLite reasoning expert. Re-derive the query logic "
            "from the question; fix wrong filters, joins, aggregations, or "
            "value formats. Output only SQL."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{sql}\n\n"
            f"Outcome: {outcome}\n\n"
            "Re-read the question carefully. Check: (1) WHERE/LIKE values "
            "against real data formats, (2) join keys, (3) aggregation and "
            "GROUP BY, (4) ORDER BY / LIMIT direction. Then write a "
            "corrected query."
        )
        return self.llm(prompt, system=system, temperature=0.0)