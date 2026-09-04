"""Harness that generates SQL, executes it, classifies any failure as syntax/schema/semantics, and applies a class-specific repair prompt for up to 2 rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1ErrorClassify(SQLHarness):
    """Error-classification repair harness.

    Control flow:
      1. Generate an initial SQL query from (schema, question).
      2. Execute it against the database.
      3. On failure, classify the failure:
           - "syntax"    : the SQL could not be parsed / uses invalid tokens.
           - "schema"    : the SQL references tables/columns absent from the schema.
           - "semantics" : the SQL runs but its logic is wrong (e.g. 0 rows).
      4. Apply a repair prompt specialized to that failure class.
      5. Repeat for at most MAX_ROUNDS repair rounds; return the best SQL.
    """

    MAX_ROUNDS = 2

    # ------------------------------------------------------------------ main
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)

        last_error = ""
        last_class = "syntax"
        for round_idx in range(self.MAX_ROUNDS + 1):
            result = self.execute(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                # Executed cleanly but produced an empty result set -> semantics.
                last_class = "semantics"
                last_error = "Query executed successfully but returned 0 rows."
            else:
                last_error = (result.get("error") or "").strip() or "Unknown execution error."
                last_class = self._classify_error(sql, last_error)

            if round_idx >= self.MAX_ROUNDS:
                break
            sql = self._repair(question, sql, last_class, last_error)

        return sql

    # ----------------------------------------------------------- generation
    def _generate_initial(self, question: str) -> str:
        system = (
            "You are an expert SQLite developer. Write a single correct SQL query "
            "that answers the user's question using only the tables and columns "
            "present in the given schema. Output only the SQL query."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question."
        )
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(response)

    # ------------------------------------------------------- classification
    def _classify_error(self, sql: str, error: str) -> str:
        e = error.lower()

        schema_signals = (
            "no such table",
            "no such column",
            "no column named",
            "ambiguous column",
            "unknown column",
            "unknown table",
            "does not exist",
            "undefined table",
            "invalid column",
        )
        if any(sig in e for sig in schema_signals):
            return "schema"

        syntax_signals = (
            "syntax error",
            "unrecognized token",
            "incomplete input",
            "unterminated",
            "parse error",
            "no such function",
            "wrong number of arguments",
            "misuse of aggregate",
            "near ",
        )
        if any(sig in e for sig in syntax_signals):
            return "syntax"

        # Error text is ambiguous: let the LLM assign the failure class.
        system = (
            "You are a SQL debugging assistant. Classify the cause of a failed "
            "SQL query into exactly one category: syntax, schema, or semantics. "
            "Answer with a single word."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Failed SQL:\n{sql}\n\n"
            f"Error message:\n{error}\n\n"
            "Categories:\n"
            "- syntax: malformed SQL, invalid tokens, unsupported functions.\n"
            "- schema: references to tables/columns that do not exist or are ambiguous.\n"
            "- semantics: valid SQL whose logic does not answer the question.\n\n"
            "Category:"
        )
        verdict = (self.llm(prompt, system=system, temperature=0.0, n=1) or "").strip().lower()
        for label in ("syntax", "schema", "semantics"):
            if label in verdict:
                return label
        return "syntax"

    # -------------------------------------------------------------- repairs
    def _repair(self, question: str, sql: str, failure_class: str, error: str) -> str:
        if failure_class == "syntax":
            system, prompt = self._syntax_fix_prompt(question, sql, error)
        elif failure_class == "schema":
            system, prompt = self._schema_fix_prompt(question, sql, error)
        else:
            system, prompt = self._semantic_fix_prompt(question, sql, error)

        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        fixed = bridge.extract_sql(response)
        return fixed or sql

    def _syntax_fix_prompt(self, question: str, sql: str, error: str):
        system = (
            "You are an expert SQLite developer repairing a SQL syntax error. "
            "Produce a syntactically valid SQLite query. Output only the SQL."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL failed with a SYNTAX error:\n{sql}\n\n"
            f"Database error message:\n{error}\n\n"
            "Fix only the syntax (parentheses, keywords, quoting, valid SQLite "
            "functions, clause ordering) while preserving the intended logic. "
            "Output only the corrected SQL."
        )
        return system, prompt

    def _schema_fix_prompt(self, question: str, sql: str, error: str):
        system = (
            "You are an expert SQLite developer repairing a SQL schema-reference "
            "error. Use only tables and columns that exist in the given schema. "
            "Output only the SQL."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL failed with a SCHEMA error (it references a table "
            f"or column that does not exist, or is ambiguous):\n{sql}\n\n"
            f"Database error message:\n{error}\n\n"
            "Rewrite the query so every table and column name matches the schema "
            "exactly: check spelling, use the correct table for each column, add "
            "proper table aliases for ambiguous columns, and verify join keys. "
            "Output only the corrected SQL."
        )
        return system, prompt

    def _semantic_fix_prompt(self, question: str, sql: str, error: str):
        system = (
            "You are an expert SQLite developer repairing a SQL query whose logic "
            "is wrong: it executes without errors but does not correctly answer "
            "the question (for example it returns an empty result). "
            "Output only the SQL."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL is syntactically valid and uses valid schema "
            f"names, but its SEMANTICS are wrong:\n{sql}\n\n"
            f"Observed problem:\n{error}\n\n"
            "Rethink the logic: verify that literal filter values plausibly match "
            "stored data (prefer LIKE or looser matching for text), check join "
            "conditions, aggregation and GROUP BY keys, and ORDER BY/LIMIT "
            "direction. Output only the corrected SQL."
        )
        return system, prompt