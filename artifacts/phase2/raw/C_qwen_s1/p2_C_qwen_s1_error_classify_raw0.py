"""Generates SQL, executes it, classifies failures as syntax, schema, or semantics, and applies targeted repairs for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2CQwenS1ErrorClassify(SQLHarness):
    """Repair harness that routes execution failures to class-specific fix prompts."""

    MAX_REPAIR_ROUNDS = 2
    SYSTEM = (
        "You are an expert Text-to-SQL assistant. "
        "Output only one executable SQL statement. "
        "No explanations, no Markdown."
    )

    _SCHEMA_PATTERNS = (
        "no such table",
        "no such column",
        "unknown column",
        "unknown table",
        "table not found",
        "column not found",
        "relation does not exist",
        "column does not exist",
        "ambiguous column",
        "ambiguous reference",
        "invalid column",
        "invalid table",
        "invalid object name",
        "invalid identifier",
        "cannot resolve",
        "unresolved",
        "has no column",
        "missing column",
        "missing table",
        "not a valid column",
        "not a valid table",
        "field not found",
        "field does not exist",
        "object not found",
        "identifier not found",
    )

    _SYNTAX_PATTERNS = (
        "syntax",
        "near",
        "incomplete input",
        "unrecognized token",
        "unexpected",
        "malformed",
        "invalid sql",
        "bad sql",
        "parser",
        "parse",
        "expected",
        "token",
        "unterminated",
        "mismatched parenthesis",
        "missing keyword",
        "illegal",
        "sqlite3.operationalerror",
        "operationalerror",
    )

    _SEMANTIC_PATTERNS = (
        "constraint",
        "unique",
        "foreign key",
        "not null",
        "check constraint",
        "datatype",
        "data type",
        "type mismatch",
        "overflow",
        "division by zero",
        "divide by zero",
        "subquery returns more than 1 row",
        "more than 1 row",
        "multiple rows",
        "aggregate",
        "group by",
        "misuse",
        "window function",
        "cartesian",
    )

    def solve(self, question: str) -> str:
        schema = str(getattr(self, "schema", "") or "")

        sql = self._extract_sql(
            self._llm(self._initial_prompt(question, schema), self.SYSTEM)
        )
        best_sql = sql
        best_ok_sql = None

        result = self._execute(sql)
        if result.get("ok"):
            best_ok_sql = sql

        for _ in range(self.MAX_REPAIR_ROUNDS):
            category, detail = self._diagnose(question, schema, sql, result)
            if category == "none":
                return sql

            fixed = self._repair(category, question, schema, sql, result, detail)
            if not fixed:
                fixed = self._fallback_sql(question, schema)

            if self._same_sql(fixed, sql):
                alt_detail = (
                    "Previous repair did not change the SQL. "
                    "Produce a materially different corrected SQL."
                )
                alt = self._repair("semantics", question, schema, sql, result, alt_detail)
                if alt and not self._same_sql(alt, sql):
                    fixed = alt

            if fixed:
                sql = fixed

            best_sql = sql or best_sql
            result = self._execute(sql)

            if result.get("ok"):
                best_ok_sql = sql

        if result.get("ok"):
            return sql
        if best_ok_sql:
            return best_ok_sql
        if best_sql:
            return best_sql
        return "SELECT 1"

    def _initial_prompt(self, question: str, schema: str) -> str:
        return f"""Generate one SQL query that answers the question.
Question:
{question}

Schema:
{schema}

Return only one executable SQL statement.
"""

    def _diagnose(self, question: str, schema: str, sql: str, result: dict):
        if result.get("ok"):
            issue = self._semantic_issue(question, schema, sql, result)
            if issue:
                return "semantics", issue
            return "none", ""

        if not sql or not sql.strip():
            return "syntax", result.get("error") or "No SQL statement was produced."

        category = self._classify_error(question, schema, sql, result)
        return category, result.get("error") or "Execution failed."

    def _classify_error(self, question: str, schema: str, sql: str, result: dict) -> str:
        error = str(result.get("error") or "").lower()

        if not error:
            return "semantics"

        if any(pattern in error for pattern in self._SCHEMA_PATTERNS):
            return "schema"

        if any(pattern in error for pattern in self._SYNTAX_PATTERNS):
            return "syntax"

        if any(pattern in error for pattern in self._SEMANTIC_PATTERNS):
            return "semantics"

        if any(word in error for word in ("column", "table", "relation", "field")):
            return "schema"

        if any(word in error for word in ("syntax", "parse", "near", "token")):
            return "syntax"

        return self._llm_classify(question, schema, sql, error)

    def _llm_classify(self, question: str, schema: str, sql: str, error: str) -> str:
        prompt = f"""Classify the failure of this SQL attempt.
Question:
{question}

SQL:
{sql or '(no SQL was extracted)'}

Execution error:
{error}

Categories:
- syntax: malformed SQL statement or parse error
- schema: missing, unknown, or ambiguous table/column names
- semantics: logic, constraint, result-shape, or meaning problem

Return exactly one word: syntax, schema, or semantics.
"""
        response = self._llm(prompt, system="You are a precise failure classifier.").strip().lower()

        if "schema" in response:
            return "schema"
        if "syntax" in response:
            return "syntax"
        if "semantic" in response:
            return "semantics"
        return "semantics"

    def _semantic_issue(self, question: str, schema: str, sql: str, result: dict) -> str:
        if not sql or not sql.strip():
            return "SQL is empty."

        prompt = f"""Decide whether this executable SQL is obviously semantically wrong for the question.
Question:
{question}

Schema:
{schema}

SQL:
{sql}

Execution result preview:
{self._rows_preview(result.get("rows"))}

If the SQL could plausibly answer the question, return exactly:
VALID

Only if it clearly uses the wrong table, selects unrelated columns, omits required filters, or aggregates incorrectly, return exactly:
INVALID: <short reason>
"""
        response = self._llm(prompt, system="You are a careful SQL semantic validator.").strip()
        first_line = (response.splitlines() or [""])[0].strip().lower()

        if first_line.startswith("invalid"):
            return response[:500]
        return ""

    def _repair(self, category: str, question: str, schema: str, sql: str, result: dict, detail: str) -> str:
        category = (category or "semantics").lower()

        if category == "syntax":
            raw = self._fix_syntax(question, schema, sql, detail)
        elif category == "schema":
            raw = self._fix_schema(question, schema, sql, detail)
        else:
            raw = self._fix_semantics(question, schema, sql, result, detail)

        return self._extract_sql(raw)

    def _fix_syntax(self, question: str, schema: str, sql: str, detail: str) -> str:
        prompt = f"""Fix the syntax of this SQL while preserving its intended meaning.
Question:
{question}

Schema:
{schema}

Current SQL:
{sql or '(no SQL was extracted)'}

Syntax error:
{detail}

Rules:
- Return only one corrected SQL statement.
- Do not invent tables or columns.
- Fix punctuation, keywords, aliases, parentheses, and statement structure.
"""
        return self._llm(prompt, self.SYSTEM)

    def _fix_schema(self, question: str, schema: str, sql: str, detail: str) -> str:
        prompt = f"""Fix schema-related errors by using exact table and column names from the schema.
Question:
{question}

Schema:
{schema}

Current SQL:
{sql or '(no SQL was extracted)'}

Execution error:
{detail}

Rules:
- Use only tables and columns present in the schema.
- Qualify columns when needed and correct aliases.
- Preserve the intended meaning of the query.
- Return only one SQL statement.
"""
        return self._llm(prompt, self.SYSTEM)

    def _fix_semantics(self, question: str, schema: str, sql: str, result: dict, detail: str) -> str:
        execution_state = "succeeded" if result.get("ok") else "failed"
        prompt = f"""Rewrite this SQL so it semantically answers the question.
Question:
{question}

Schema:
{schema}

Current SQL:
{sql or '(no SQL was extracted)'}

Execution state:
{execution_state}

Execution detail:
{detail}

Result preview:
{self._rows_preview(result.get("rows"))}

Rules:
- Preserve valid syntax and schema names.
- Correct SELECT columns, filters, joins, grouping, ordering, and LIMIT as needed.
- Return only one SQL statement.
"""
        return self._llm(prompt, self.SYSTEM)

    def _fallback_sql(self, question: str, schema: str) -> str:
        prompt = f"""Generate one SQL query that answers the question.
Question:
{question}

Schema:
{schema}

Return only one executable SQL statement.
"""
        return self._extract_sql(self._llm(prompt, self.SYSTEM))

    def _llm(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system=system, temperature=temperature)
            except TypeError:
                try:
                    response = self.llm(prompt, system=system)
                except TypeError:
                    response = self.llm(prompt)

        return self._to_text(response)

    def _to_text(self, response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            return "\n".join(self._to_text(item) for item in response)
        if isinstance(response, dict):
            for key in ("choices", "content", "text", "completion", "output", "message"):
                if key in response:
                    return self._to_text(response[key])
            return str(response)

        for attr in ("choices", "content", "text", "completion", "output", "message"):
            if hasattr(response, attr):
                value = getattr(response, attr)
                if not callable(value):
                    return self._to_text(value)

        return str(response)

    def _execute(self, sql: str) -> dict:
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "No SQL statement was produced."}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            ok = bool(result.get("ok"))
            rows = result.get("rows", [])
            error = str(result.get("error") or "")
        elif isinstance(result, bool):
            ok = result
            rows = []
            error = "" if ok else "Execution failed."
        elif isinstance(result, (list, tuple)):
            ok = True
            rows = list(result)
            error = ""
        else:
            ok = False
            rows = []
            error = str(result)

        if ok:
            error = ""
        elif not error:
            error = "Execution failed."

        return {"ok": ok, "rows": rows, "error": error}

    def _extract_sql(self, text: str) -> str:
        text = self._to_text(text)
        if not text:
            return ""

        sql = ""
        try:
            sql = bridge.extract_sql(text) or ""
        except Exception:
            sql = ""

        if not sql:
            sql = self._regex_extract_sql(text)

        if not sql and re.search(r"\b(?:select|with|insert|update|delete|create|pragma|explain)\b", text, re.I):
            sql = text

        return self._clean_sql(sql)

    def _regex_extract_sql(self, text: str) -> str:
        fenced = re.search(r"