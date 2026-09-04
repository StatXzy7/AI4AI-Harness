"""Generate SQL, execute it, classify any failure as syntax / schema / semantics in code, and apply a class-specific repair for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1ErrorClassify(SQLHarness):
    """Error-classification self-repair harness for Text-to-SQL.

    Control flow (implemented here, not delegated to the prompt):
      1. Generate one initial SQL query from (schema, question).
      2. Execute it against the database.
      3. Diagnose the outcome in code:
           * success with rows   -> accept the query;
           * success with 0 rows -> SEMANTICS failure (heuristic);
           * execution error     -> SYNTAX / SCHEMA / SEMANTICS, decided by
             signal matching against the DB error, with an LLM tie-breaker.
      4. Apply the repair strategy specialised for that failure class.
      5. Loop for at most MAX_REPAIR_ROUNDS repair rounds.

    The last successfully-executing query is remembered, so the harness never
    returns a non-executable query when an executable candidate exists.
    """

    SYNTAX = "syntax"
    SCHEMA = "schema"
    SEMANTICS = "semantics"

    MAX_REPAIR_ROUNDS = 2

    # Failure-class signals, matched against the lower-cased database error.
    _SCHEMA_SIGNALS = (
        "no such table",
        "no such column",
        "no such function",
        "ambiguous column",
        "unknown column",
        "unknown table",
        "unknown database",
        "does not exist",
        "invalid column",
        "invalid table",
        "undefined table",
        "undefined column",
        "missing from-clause",
    )
    _SYNTAX_SIGNALS = (
        "syntax error",
        "unrecognized token",
        "incomplete input",
        "unterminated",
        "parse error",
        "unexpected token",
        "unexpected end",
        "mismatched input",
        "invalid syntax",
    )
    _SEMANTIC_SIGNALS = (
        "misuse of aggregate",
        "datatype mismatch",
        "type mismatch",
        "must appear in the group by",
        "aggregate function",
    )

    _REPAIR_SYSTEMS = {
        SYNTAX: (
            "You are a SQL syntax repair tool. You correct malformed SQL while "
            "preserving its exact logic. You output only SQL."
        ),
        SCHEMA: (
            "You are a SQL schema-alignment tool. You rewrite queries so that "
            "every table and column reference exactly matches the database "
            "schema. You output only SQL."
        ),
        SEMANTICS: (
            "You are a Text-to-SQL logic reviewer. You re-derive queries from "
            "the question so their logic is correct. You output only SQL."
        ),
    }

    _REPAIR_INSTRUCTIONS = {
        SYNTAX: (
            "Fix ONLY the syntax: keyword spelling, clause order, commas, "
            "parentheses, string quoting, and aliasing. Do NOT change any "
            "table, column, join, filter, aggregation, ordering, or limit - "
            "the repaired query must express exactly the same logic."
        ),
        SCHEMA: (
            "Fix ONLY the schema references: the query uses table or column "
            "names that do not exist or are ambiguous. Map every identifier "
            "to the EXACT names in the schema above (check spelling, table "
            "prefixes, and which table actually owns each column) and repair "
            "the join path if it relied on non-existent columns. Preserve the "
            "query's intent."
        ),
        SEMANTICS: (
            "The query's LOGIC does not answer the question. Re-derive it "
            "from scratch: re-check which tables/columns are needed, the join "
            "keys, every filter predicate, literal value formats (case and "
            "whitespace - use LIKE when matching text loosely), aggregation "
            "functions, GROUP BY keys, HAVING vs WHERE, ORDER BY direction, "
            "and LIMIT. If, after careful checking, you are confident the "
            "query is already logically correct (for example an empty result "
            "is genuinely the right answer), return the query unchanged."
        ),
    }

    # ------------------------------------------------------------------ #
    # main pipeline
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)

        last_executable_sql = None

        for attempt in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(sql)

            if result["ok"]:
                last_executable_sql = sql
                if result["rows"]:
                    # Executed and returned data: accept.
                    return sql
                # Executed but empty: classify as a SEMANTICS failure.
                failure_class = self.SEMANTICS
                failure_info = (
                    "The query executed successfully but returned 0 rows. "
                    "This usually indicates a semantic problem: overly "
                    "restrictive predicates, wrong join keys, wrong literal "
                    "value formats (case/whitespace), or wrong column choices."
                )
            else:
                failure_info = result["error"]
                failure_class = self._classify_error(failure_info, question, sql)

            if attempt >= self.MAX_REPAIR_ROUNDS:
                break  # repair budget exhausted

            repaired = self._repair(
                question=question,
                sql=sql,
                failure_class=failure_class,
                failure_info=failure_info,
                attempt=attempt,
            )
            if not repaired or self._normalize(repaired) == self._normalize(sql):
                # Nothing new to try (or the reviewer confirmed the query):
                # stop and fall back to the best candidate we have.
                break
            sql = repaired

        # Prefer a query that at least executes over one that errors out.
        return last_executable_sql if last_executable_sql is not None else sql

    # ------------------------------------------------------------------ #
    # step 1: initial generation
    # ------------------------------------------------------------------ #
    def _generate_initial(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine. You write exactly one SQL "
            "query that answers the given question over the given schema. "
            "You output only SQL - never markdown fences or explanations."
        )
        prompt = (
            "[DATABASE SCHEMA]\n"
            f"{self.schema}\n\n"
            "[QUESTION]\n"
            f"{question}\n\n"
            "Write ONE syntactically valid SQL query that answers the question.\n"
            "Use only tables and columns that appear in the schema.\n"
            "Output ONLY the SQL query."
        )
        out = self._call_llm(prompt, system=system, temperature=0.0)
        return self._extract_sql(out) or "SELECT 1"

    # ------------------------------------------------------------------ #
    # step 3a: failure classification (control-flow branching)
    # ------------------------------------------------------------------ #
    def _classify_error(self, error_text: str, question: str, sql: str) -> str:
        low = (error_text or "").lower()
        if any(sig in low for sig in self._SCHEMA_SIGNALS):
            return self.SCHEMA
        if any(sig in low for sig in self._SYNTAX_SIGNALS):
            return self.SYNTAX
        if any(sig in low for sig in self._SEMANTIC_SIGNALS):
            return self.SEMANTICS
        # Ambiguous error: ask the frozen solver to label it, branch in code.
        return self._llm_classify(question, sql, error_text)

    def _llm_classify(self, question: str, sql: str, error_text: str) -> str:
        system = (
            "You are a SQL error classifier. Answer with exactly one word: "
            "syntax, schema, or semantics."
        )
        prompt = (
            "Classify the following database error into exactly one category:\n"
            "- syntax: the SQL text is malformed and cannot be parsed.\n"
            "- schema: the SQL references tables/columns/functions that do not "
            "exist or are ambiguous.\n"
            "- semantics: the SQL is valid but implements the wrong logic for "
            "the question.\n\n"
            f"[QUESTION]\n{question}\n\n"
            f"[SQL]\n{sql}\n\n"
            f"[ERROR]\n{error_text}\n\n"
            "Answer with one word only: syntax, schema, or semantics."
        )
        out = self._call_llm(prompt, system=system, temperature=0.0).lower()
        if "schema" in out:
            return self.SCHEMA
        if "syntax" in out:
            return self.SYNTAX
        return self.SEMANTICS  # safest default: general logic re-derivation

    # ------------------------------------------------------------------ #
    # step 4: class-specific repair strategies
    # ------------------------------------------------------------------ #
    def _repair(self, question: str, sql: str, failure_class: str,
                failure_info: str, attempt: int) -> str:
        round_note = ""
        if attempt > 0:
            round_note = (
                "\nNOTE: a previous repair attempt did NOT resolve this "
                "failure, so make a more substantial correction rather than a "
                "cosmetic edit.\n"
            )
        prompt = (
            "[DATABASE SCHEMA]\n"
            f"{self.schema}\n\n"
            "[QUESTION]\n"
            f"{question}\n\n"
            "[CURRENT SQL]\n"
            f"{sql}\n\n"
            "[FAILURE CLASS]\n"
            f"{failure_class}\n\n"
            "[DATABASE ERROR / SYMPTOM]\n"
            f"{failure_info}\n\n"
            "[WHAT TO FIX]\n"
            f"{self._REPAIR_INSTRUCTIONS[failure_class]}\n"
            f"{round_note}\n"
            "Return ONLY the corrected SQL query - no markdown fences, no "
            "explanation."
        )
        # Second repair round uses mild temperature to escape a failed first fix.
        temperature = 0.0 if attempt == 0 else 0.3
        out = self._call_llm(
            prompt,
            system=self._REPAIR_SYSTEMS[failure_class],
            temperature=temperature,
        )
        return self._extract_sql(out)

    # ------------------------------------------------------------------ #
    # utilities
    # ------------------------------------------------------------------ #
    def _call_llm(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            return self.llm(prompt, system=system, temperature=temperature) or ""
        except Exception:
            return ""

    def _extract_sql(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        if not sql:
            sql = (text or "").strip()
        return (sql or "").strip()

    def _safe_execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql) or {}
        except Exception as exc:  # defensive: executor crash counts as error
            return {"ok": False, "rows": [], "error": f"executor exception: {exc}"}
        return {
            "ok": bool(result.get("ok")),
            "rows": result.get("rows") or [],
            "error": (result.get("error") or "Unknown database error.").strip(),
        }

    @staticmethod
    def _normalize(sql: str) -> str:
        return " ".join((sql or "").split()).rstrip(";").lower()