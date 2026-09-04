"""Generate SQL, execute it, classify each failure as syntax / schema / semantics, and apply a class-specific repair for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1ErrorClassify(SQLHarness):
    """Error-classifying self-repair harness for Text-to-SQL.

    Control flow (the strategy lives here, not only in the prompts):
      1. Generate an initial SQL candidate from (schema, question).
      2. Execute the candidate.
         - ok + non-empty rows -> accept and return.
         - ok + empty rows     -> class = semantics (answers nothing), repair.
         - error               -> classify as syntax / schema / semantics with
                                  keyword rules (LLM fallback) and dispatch to
                                  the repair strategy of that class.
      3. Repeat for at most MAX_ROUNDS repairs; on budget exhaustion, return
         the last candidate.
    """

    MAX_ROUNDS = 2

    _GEN_SYSTEM = (
        "You are an expert Text-to-SQL generator. "
        "Output exactly one SQL query and nothing else."
    )

    _SCHEMA_MARKERS = (
        "no such table",
        "no such column",
        "no column named",
        "has no column",
        "ambiguous column",
        "unknown column",
        "unknown table",
        "does not exist",
        "no such index",
    )
    _SYNTAX_MARKERS = (
        "syntax error",
        "unrecognized token",
        "unexpected token",
        "parse error",
        "incomplete input",
        "unclosed",
        "misplaced",
        "near \"",
        "no such function",
        "sql logic error",
    )

    # ------------------------------------------------------------------ #
    # main control flow                                                    #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question) or "SELECT 1"

        for round_idx in range(self.MAX_ROUNDS + 1):
            result = self._safe_execute(sql)
            ok = bool(result.get("ok"))
            error = str(result.get("error") or "")
            rows = result.get("rows") or []

            # Executed and produced rows: accept.
            if ok and rows:
                return sql

            # Repair budget exhausted: return the last candidate.
            if round_idx >= self.MAX_ROUNDS:
                break

            # Executes cleanly but answers nothing -> semantics class.
            if ok:
                sql = self._fix_semantics(question, sql, error, empty_result=True) or sql
                continue

            # Hard failure: classify, then apply the class-specific fix.
            category = self._classify_error(error, question, sql)
            if category == "syntax":
                sql = self._fix_syntax(question, sql, error) or sql
            elif category == "schema":
                sql = self._fix_schema(question, sql, error) or sql
            else:
                sql = self._fix_semantics(question, sql, error, empty_result=False) or sql

        return sql

    # ------------------------------------------------------------------ #
    # failure classification                                               #
    # ------------------------------------------------------------------ #
    def _classify_error(self, error: str, question: str, sql: str) -> str:
        e = (error or "").lower()
        if e:
            for marker in self._SCHEMA_MARKERS:
                if marker in e:
                    return "schema"
            for marker in self._SYNTAX_MARKERS:
                if marker in e:
                    return "syntax"
        return self._llm_classify(error, question, sql)

    def _llm_classify(self, error: str, question: str, sql: str) -> str:
        system = (
            "You are a database error classifier. "
            "Answer with exactly one word: syntax, schema or semantics."
        )
        prompt = (
            "Classify the following database failure into exactly one class:\n"
            "- syntax    : malformed SQL that cannot be parsed/executed as written\n"
            "- schema    : references to missing or ambiguous tables/columns\n"
            "- semantics : well-formed SQL whose logic does not fit the question\n\n"
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question: " + question + "\n\n"
            "SQL:\n" + sql + "\n\n"
            "Error: " + (error or "<none>") + "\n\n"
            "Class (one word):"
        )
        out = self._ask(prompt, system=system).lower()
        if "syntax" in out:
            return "syntax"
        if "schema" in out:
            return "schema"
        return "semantics"

    # ------------------------------------------------------------------ #
    # generation + class-specific repair strategies                        #
    # ------------------------------------------------------------------ #
    def _generate_initial(self, question: str) -> str:
        prompt = (
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question: " + question + "\n\n"
            "Write a single SQL query (SQLite dialect) that answers the question.\n"
            "Output only the SQL query."
        )
        return self._extract_sql(self._ask(prompt, system=self._GEN_SYSTEM))

    def _fix_syntax(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "The following SQL query failed with a SYNTAX error.\n\n"
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question: " + question + "\n\n"
            "Faulty SQL:\n" + sql + "\n\n"
            "Database error:\n" + (error or "<unknown>") + "\n\n"
            "Repair strategy (syntax class):\n"
            "- Fix ONLY the syntax; keep the same tables, columns, joins, filters "
            "and aggregation.\n"
            "- Produce valid SQLite: balanced parentheses, properly quoted string "
            "literals, valid keywords, correct clause order, and standard SQLite "
            "functions only.\n"
            "Output only the corrected SQL query."
        )
        return self._extract_sql(self._ask(prompt, system=self._GEN_SYSTEM))

    def _fix_schema(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "The following SQL query failed with a SCHEMA error: it references "
            "tables or columns that do not exist (or are ambiguous).\n\n"
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question: " + question + "\n\n"
            "Faulty SQL:\n" + sql + "\n\n"
            "Database error:\n" + (error or "<unknown>") + "\n\n"
            "Repair strategy (schema class):\n"
            "- Use ONLY table and column names that appear verbatim in the schema above.\n"
            "- Map each intended name to the closest real name in the schema.\n"
            "- Qualify ambiguous columns with their table name.\n"
            "- Preserve the original intent of the query.\n"
            "Output only the corrected SQL query."
        )
        return self._extract_sql(self._ask(prompt, system=self._GEN_SYSTEM))

    def _fix_semantics(self, question: str, sql: str, error: str, empty_result: bool) -> str:
        if empty_result:
            symptom = ("The query executes but returns an EMPTY result, so it "
                       "probably does not actually answer the question.")
            extra = ("- The result was empty: relax or correct overly strict filter "
                     "values and verify literal values against the schema.\n")
        else:
            symptom = ("The query failed with a semantic/runtime error: "
                       + (error or "<unknown>"))
            extra = ""
        prompt = (
            "The following SQL query has a SEMANTIC problem.\n"
            + symptom + "\n\n"
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question: " + question + "\n\n"
            "Faulty SQL:\n" + sql + "\n\n"
            "Repair strategy (semantics class):\n"
            "- Re-read the question and align the query logic with its intent.\n"
            "- Check JOIN keys, WHERE filter values (match the stored format; use "
            "LIKE / LOWER for case-insensitive text), aggregation (COUNT vs SUM vs "
            "AVG, correct GROUP BY), DISTINCT when duplicates are possible, and "
            "ORDER BY / LIMIT for superlatives.\n"
            + extra +
            "Output only the corrected SQL query."
        )
        return self._extract_sql(self._ask(prompt, system=self._GEN_SYSTEM))

    # ------------------------------------------------------------------ #
    # plumbing                                                             #
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str, system: str = "") -> str:
        try:
            resp = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(resp, (list, tuple)):
            resp = resp[0] if resp else ""
        return resp or ""

    def _safe_execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "invalid execute() result"}
        return result

    def _extract_sql(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""
        if extracted and extracted.strip():
            return extracted.strip()
        # Fallback: strip markdown code fences ourselves.
        if "