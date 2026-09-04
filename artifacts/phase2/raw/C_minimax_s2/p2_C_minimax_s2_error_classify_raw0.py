"""Wrapper that classifies SQL execution errors (syntax/schema/semantics) and applies targeted fixes for up to two repair rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2ErrorClassify(SQLHarness):

    # ---- prompt templates -------------------------------------------------

    _GEN_SYSTEM = "You translate natural language questions into a single SQLite SQL query."
    _GEN_PROMPT = (
        "Given the schema below, write ONE SQLite query that answers the question.\n"
        "Return ONLY the SQL, no prose, no markdown fences.\n\n"
        "Schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "SQL:"
    )

    _FIX_SYSTEM = "You are a SQL repair assistant. Return ONLY the corrected SQL, no prose."

    _FIX_TEMPLATES = {
        "syntax": (
            "The following SQL failed to execute with a syntax error. "
            "Fix the syntax. Return ONLY the corrected SQL.\n\n"
            "Original question: {question}\n"
            "Schema:\n{schema}\n\n"
            "Original SQL:\n{sql}\n\n"
            "Database error:\n{error}\n\n"
            "Corrected SQL:"
        ),
        "schema": (
            "The following SQL referenced objects that do not exist in the schema "
            "(wrong table or column name, or wrong JOIN). Fix the references so they "
            "match the schema below. Return ONLY the corrected SQL.\n\n"
            "Original question: {question}\n"
            "Schema:\n{schema}\n\n"
            "Original SQL:\n{sql}\n\n"
            "Database error:\n{error}\n\n"
            "Corrected SQL:"
        ),
        "semantics": (
            "The following SQL executed without error but likely does not answer the "
            "question correctly (semantic / logical mistake: wrong filter, wrong "
            "aggregation, missing GROUP BY, wrong join direction, etc.). Rewrite it so "
            "it correctly answers the question. Return ONLY the corrected SQL.\n\n"
            "Original question: {question}\n"
            "Schema:\n{schema}\n\n"
            "Original SQL:\n{sql}\n\n"
            "Database error (may be empty):\n{error}\n\n"
            "Corrected SQL:"
        ),
    }

    # ---- error classification --------------------------------------------

    @staticmethod
    def _classify_error(error: str) -> str:
        """Classify a SQLite-style error string into syntax/schema/semantics.

        - 'syntax'   : the parser rejected the statement
        - 'schema'   : the statement parsed but references missing objects
        - 'semantics': fallback; treated as a logical problem on the next round
        """
        e = (error or "").lower()

        syntax_markers = (
            "syntax error",
            "near \"", "near '",
            "incomplete input",
            "unrecognized token",
            "unterminated",
            "parse error",
            "you have an error in your sql syntax",
        )
        schema_markers = (
            "no such table",
            "no such column",
            "no such function",
            "no such index",
            "ambiguous column",
            "unknown column",
            "unknown table",
            "does not exist",
            "not found",
            "misuse of aggregate",
        )

        if any(m in e for m in syntax_markers):
            return "syntax"
        if any(m in e for m in schema_markers):
            return "schema"
        return "semantics"

    # ---- generation / repair calls ---------------------------------------

    def _generate_initial(self, question: str) -> str:
        prompt = self._GEN_PROMPT.format(schema=self.schema, question=question)
        text = self.llm(prompt, system=self._GEN_SYSTEM, temperature=0.0, n=1)
        return bridge.extract_sql(text)

    def _repair(self, question: str, sql: str, error: str, kind: str) -> str:
        template = self._FIX_TEMPLATES[kind]
        prompt = template.format(
            schema=self.schema,
            question=question,
            sql=sql,
            error=error or "(none)",
        )
        text = self.llm(prompt, system=self._FIX_SYSTEM, temperature=0.0, n=1)
        return bridge.extract_sql(text)

    # ---- main control flow ------------------------------------------------

    def solve(self, question: str) -> str:
        # Round 0: initial generation
        sql = self._generate_initial(question)
        if not sql:
            return ""

        result = self.execute(sql)
        if result.get("ok"):
            return sql

        # Repair loop: up to 2 rounds (rounds 1 and 2)
        for _ in range(2):
            error = result.get("error", "")
            kind = self._classify_error(error)

            candidate = self._repair(question, sql, error, kind)
            if not candidate:
                # Could not extract a fix; keep current best and stop.
                break

            sql = candidate
            result = self.execute(sql)
            if result.get("ok"):
                return sql

        # Return the last candidate even if it still errors;
        # the harness contract is to return *a* SQL string.
        return sql