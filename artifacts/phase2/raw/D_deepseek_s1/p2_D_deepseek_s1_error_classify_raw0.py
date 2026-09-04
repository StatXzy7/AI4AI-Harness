"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies targeted fixes for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1ErrorClassify(SQLHarness):
    DEFAULT_SYSTEM = "You are an expert SQL engineer. Output only a single SQL query."
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        current_sql = self._generate_initial_sql(question)
        result = self._execute(current_sql)
        if result.get("ok"):
            return current_sql

        for _ in range(self.MAX_REPAIR_ROUNDS):
            error = result.get("error", "")
            category = self._classify_error(error)
            current_sql = self._generate_fix_sql(question, current_sql, error, category)
            result = self._execute(current_sql)
            if result.get("ok"):
                return current_sql

        return current_sql

    def _generate_initial_sql(self, question: str) -> str:
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Write a single SQL query to answer the question. Output only the SQL query."""
        text = self._call_llm(prompt, self.DEFAULT_SYSTEM)
        return self._extract_sql(text)

    def _generate_fix_sql(self, question: str, previous_sql: str, error: str, category: str) -> str:
        if category == "syntax":
            instruction = "The SQL query produced a syntax error. Fix the SQL syntax only and keep the intended logic."
        elif category == "schema":
            instruction = "The SQL query produced a schema error. Make sure every table and column name exists in the schema and is referenced correctly. Fix the query."
        else:
            instruction = "The SQL query produced a semantic error. Analyze the question and fix logical issues such as incorrect filters, joins, aggregations, groupings, subqueries, data types, or conditions."

        prompt = f"""Database schema:
{self.schema}

Question:
{question}

{instruction}

Error:
{error or "unknown execution error"}

Original SQL:
{previous_sql}

Output only the corrected SQL query."""
        text = self._call_llm(prompt, self.DEFAULT_SYSTEM)
        return self._extract_sql(text)

    def _call_llm(self, prompt: str, system: str = "") -> str:
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._unwrap_llm_response(raw)

    def _unwrap_llm_response(self, raw) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            if not raw:
                return ""
            return self._unwrap_llm_response(raw[0])
        if isinstance(raw, dict):
            for key in ("text", "sql", "query", "content", "message"):
                value = raw.get(key)
                if value is not None:
                    if isinstance(value, str):
                        return value
                    if isinstance(value, dict):
                        for inner in ("content", "text", "sql", "query"):
                            if value.get(inner) is not None:
                                return str(value.get(inner))
                        return str(value)
                    return str(value)
            if "choices" in raw and isinstance(raw.get("choices"), list) and raw["choices"]:
                return self._unwrap_llm_response(raw["choices"][0])
        return str(raw)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""
        sql = bridge.extract_sql(text)
        if sql and sql.strip():
            return sql.strip()
        return text.strip()

    def _execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
            if isinstance(result, dict) and "ok" in result:
                return result
            if isinstance(result, bool):
                return {"ok": result, "rows": [], "error": ""}
            return {"ok": False, "rows": [], "error": str(result)}
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _classify_error(self, error: str) -> str:
        err = str(error or "").lower()

        syntax_markers = [
            "syntax error",
            "parse error",
            "near \"",
            "near '",
            "near ",
            "unexpected token",
            "unexpected keyword",
            "incorrect syntax",
            "syntaxerror",
            "could not parse",
            "invalid sql",
            "missing expression",
            "missing keyword",
            "missing right parenthesis",
            "missing left parenthesis",
            "missing select keyword",
            "missing comma",
            "ora-00900",
            "ora-00933",
            "ora-01756",
            "sqlstate: 42601",
            "sqlstate[42601",
        ]

        semantic_markers = [
            "division by zero",
            "divide by zero",
            "misuse of aggregate",
            "aggregate function",
            "not a group by expression",
            "must appear in the group by",
            "each group by",
            "group by",
            "having",
            "subquery returns more than one",
            "single-row subquery",
            "type mismatch",
            "datatype mismatch",
            "data type mismatch",
            "inconsistent datatype",
            "invalid number",
            "numeric overflow",
            "conversion",
            "date format",
            "cannot mix",
            "distinct",
            "order by",
            "cardinality",
            "too many rows",
            "constraint",
            "unique constraint",
            "foreign key",
            "check constraint",
            "not null",
            "duplicate",
            "out of range",
            "operator does not exist",
            "cannot cast",
            "cannot convert",
            "division",
            "value too long",
            "invalid date",
            "cannot parse date",
            "arithmetic exception",
            "invalid operation",
            "inconsistent types",
            "unsupported type",
            "cannot compare",
            "non-numeric",
            "invalid input syntax",
            "column count doesn't match",
            "value count doesn't match",
            "cannot insert null",
        ]

        schema_markers = [
            "no such table",
            "no such column",
            "unknown column",
            "unknown table",
            "relation",
            "does not exist",
            "invalid identifier",
            "ambiguous column",
            "column ambiguously defined",
            "unresolved column",
            "unresolved table",
            "missing table",
            "missing from-clause entry",
            "invalid object name",
            "no exists",
            "not exist",
            "sqlstate[42",
            "sqlstate: 42",
            "ora-00942",
            "ora-00904",
            "table or view does not exist",
            "column does not exist",
            "undefined table",
            "undefined column",
            "cannot find",
            "not found",
            "unknown",
            "no such function",
            "function does not exist",
            "unable to resolve",
            "binding",
            "bind variable",
            "unresolved",
            "column",
            "table",
        ]

        for marker in syntax_markers:
            if marker in err:
                return "syntax"
        for marker in semantic_markers:
            if marker in err:
                return "semantics"
        for marker in schema_markers:
            if marker in err:
                return "schema"
        return "semantics"