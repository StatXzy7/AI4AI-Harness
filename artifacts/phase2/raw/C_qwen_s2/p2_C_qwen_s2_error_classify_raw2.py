"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies class-specific repairs for up to two rounds."""

import difflib
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2ErrorClassify(SQLHarness):
    SYNTAX = "syntax"
    SCHEMA = "schema"
    SEMANTICS = "semantics"
    MAX_REPAIR_ROUNDS = 2

    _SYNTAX_PATTERNS = (
        r"syntax",
        r"parse",
        r"near\s+",
        r"incomplete input",
        r"unrecognized token",
        r"unexpected",
        r"expected",
        r"unterminated",
        r"invalid input",
        r"malformed",
        r"illegal",
        r"you have an error in your sql syntax",
        r"missing (?:keyword|parenthesis|comma|quote|operator)",
        r"unclosed",
        r"invalid operator",
        r"prepare failed",
        r"cannot prepare",
        r"unrecognized keyword",
        r"invalid escape",
    )

    _SCHEMA_PATTERNS = (
        r"no such table",
        r"no such column",
        r"no such field",
        r"no such function",
        r"unknown column",
        r"unknown table",
        r"unknown identifier",
        r"column not found",
        r"table not found",
        r"field not found",
        r"invalid identifier",
        r"invalid column",
        r"invalid table",
        r"invalid object name",
        r"table or view not found",
        r"relation .* does not exist",
        r"does not exist",
        r"ambiguous column",
        r"ambiguous",
        r"cannot resolve",
        r"unresolved",
        r"missing from-clause entry",
        r"has no column named",
        r"no column named",
        r"column .* is not in",
        r"object name .* invalid",
    )

    _SEMANTIC_PATTERNS = (
        r"group by",
        r"aggregate",
        r"aggregat",
        r"datatype",
        r"data type",
        r"type mismatch",
        r"conversion",
        r"division by zero",
        r"constraint",
        r"unique",
        r"foreign key",
        r"not null",
        r"check constraint",
        r"too many rows",
        r"more than 1 row",
        r"more than one row",
        r"subquery",
        r"misuse",
        r"invalid use",
        r"wrong number of arguments",
        r"argument",
        r"overflow",
        r"out of range",
        r"permission",
        r"read only",
        r"lock",
        r"timeout",
        r"collation",
        r"illegal mixture",
        r"not allowed",
    )

    _SQL_KEYWORDS = frozenset({
        "select", "from", "where", "group", "by", "order", "having", "limit",
        "offset", "join", "inner", "left", "right", "full", "outer", "cross",
        "on", "using", "as", "and", "or", "not", "in", "exists", "between",
        "like", "is", "null", "case", "when", "then", "else", "end", "union",
        "all", "intersect", "except", "distinct", "asc", "desc", "values",
        "insert", "into", "update", "set", "delete", "create", "table",
        "primary", "key", "foreign", "references", "constraint", "default",
        "check", "unique", "index", "view", "trigger", "cast", "collate",
        "escape", "glob", "regexp", "varchar", "integer", "int", "text",
        "date", "datetime", "timestamp", "boolean", "real", "float", "double",
        "decimal", "numeric", "char", "blob", "time", "if", "temporary",
        "temp", "autoincrement", "rowid", "without", "row", "true", "false",
        "with", "recursive", "over", "partition", "filter", "within",
        "group_concat", "count", "sum", "avg", "min", "max",
    })

    def solve(self, question: str) -> str:
        question = str(question or "").strip()
        sql = self._generate_initial_sql(question)

        result = self._execute_safe(sql)
        if result.get("ok"):
            return self._clean_sql(sql) or "SELECT 1"

        error = self._error_text(result)
        history = []

        for round_no in range(1, self.MAX_REPAIR_ROUNDS + 1):
            failure_class = self._classify_error(error, sql)
            history.append(
                {
                    "round": round_no,
                    "sql": self._clean_sql(sql),
                    "error": error,
                    "class": failure_class,
                }
            )

            if failure_class == self.SYNTAX:
                candidate = self._fix_syntax(question, sql, error, history)
            elif failure_class == self.SCHEMA:
                candidate = self._fix_schema(question, sql, error, history)
            else:
                candidate = self._fix_semantics(question, sql, error, history)

            candidate = self._clean_sql(candidate)
            if not candidate:
                candidate = sql

            sql = candidate
            result = self._execute_safe(sql)
            if result.get("ok"):
                return self._clean_sql(sql)

            error = self._error_text(result)

        return self._clean_sql(sql) or "SELECT 1"

    def _generate_initial_sql(self, question: str) -> str:
        system = "You are a precise Text-to-SQL engine. Output only one executable SQL query."
        prompt = self._initial_prompt(question)
        sql = self._extract_sql(self._llm_text(prompt, system=system, temperature=0.0, n=1))

        if not self._looks_like_sql(sql):
            retry_prompt = (
                prompt
                + "\n\nIMPORTANT: Your entire response must be only one SQL query, with no explanation or Markdown."
            )
            retry_sql = self._extract_sql(
                self._llm_text(retry_prompt, system=system, temperature=0.0, n=1)
            )
            if self._looks_like_sql(retry_sql):
                sql = retry_sql

        return self._clean_sql(sql)

    def _initial_prompt(self, question: str) -> str:
        return f"""Schema:
{self.schema}

Question:
{question}

Write one SQL query that answers the question using only the schema above.
Output SQL only, without explanation or Markdown.
"""

    def _fix_syntax(self, question: str, sql: str, error: str, history: list) -> str:
        extra = (
            "Fix only the syntax error. Preserve the intended tables, columns, joins, filters, "
            "and output semantics. Do not rewrite the query unless needed for syntax."
        )
        repaired = self._llm_repair(question, sql, error, self.SYNTAX, extra, history)

        if not repaired or self._same_sql(repaired, sql):
            programmatic = self._programmatic_syntax_fix(sql)
            if programmatic and not self._same_sql(programmatic, sql):
                return programmatic

        return repaired or sql

    def _fix_schema(self, question: str, sql: str, error: str, history: list) -> str:
        missing = self._missing_identifiers(error)
        suggestions = self._identifier_suggestions(missing)

        extra_lines = [
            "Fix schema/reference errors by using only tables and columns that appear in the schema."
        ]
        if missing:
            extra_lines.append("Missing/invalid identifiers: " + ", ".join(missing) + ".")
        if suggestions:
            extra_lines.append("Valid identifier candidates:")
            for name, candidates in suggestions.items():
                if candidates:
                    extra_lines.append(f"- {name}: {', '.join(candidates)}")
        extra_lines.append(
            "Replace invalid identifiers with the closest valid schema identifiers. "
            "Qualify columns with table names or aliases when needed. Do not invent tables or columns."
        )

        repaired = self._llm_repair(question, sql, error, self.SCHEMA, "\n".join(extra_lines), history)

        if not repaired or self._same_sql(repaired, sql):
            programmatic = self._programmatic_schema_fix(sql, missing, suggestions)
            if programmatic and not self._same_sql(programmatic, sql):
                return programmatic

        return repaired or sql

    def _fix_semantics(self, question: str, sql: str, error: str, history: list) -> str:
        hints = self._semantic_hints(error)
        extra_lines = [
            "Fix semantic/logic errors while keeping the query executable and faithful to the question. "
            "Check joins, filters, aggregation, GROUP BY, DISTINCT, ORDER BY, LIMIT, literals, and column choice."
        ]
        if hints:
            extra_lines.append("Hints: " + " ".join(hints))

        repaired = self._llm_repair(question, sql, error, self.SEMANTICS, "\n".join(extra_lines), history)

        if not repaired or self._same_sql(repaired, sql):
            programmatic = self._programmatic_semantic_fix(sql, error)
            if programmatic and not self._same_sql(programmatic, sql):
                return programmatic

        return repaired or sql

    def _llm_repair(
        self,
        question: str,
        sql: str,
        error: str,
        failure_class: str,
        extra: str,
        history: list,
    ) -> str:
        system = "You are a precise SQL repair tool. Output only one corrected SQL statement."
        prompt = self._repair_prompt(question, sql, error, failure_class, extra, history)
        response = self._llm_text(prompt, system=system, temperature=0.0, n=1)
        return self._extract_sql(response)

    def _repair_prompt(
        self,
        question: str,
        sql: str,
        error: str,
        failure_class: str,
        extra: str,
        history: list,
    ) -> str:
        history_text = self._format_history(history)
        return f"""Repair the SQL query below.

Schema:
{self.schema}

Question:
{question}

Current SQL:
{self._clean_sql(sql)}

Execution error:
{error}

Failure class:
{failure_class}

Class-specific guidance:
{extra}

Previous attempts:
{history_text}

Output rules:
- Return exactly one executable SQL statement.
- Use only tables and columns from the schema.
- Do not include explanations, Markdown, or multiple statements.

Corrected SQL:
"""

    def _format_history(self, history: list) -> str:
        if not history:
            return "None."
        entries = []
        for item in history[-3:]:
            entries.append(
                f"Round {item.get('round')} [{item.get('class')}]\n"
                f"SQL: {item.get('sql')}\n"
                f"Error: {item.get('error')}"
            )
        return "\n\n".join(entries)

    def _programmatic_syntax_fix(self, sql: str) -> str:
        fixed = self._clean_sql(sql) or str(sql or "").strip()
        if not fixed:
            return ""

        fixed = re.sub(
            r",\s*(\bFROM\b|\bWHERE\b|\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|\bOFFSET\b|"
            r"\bUNION\b|\bINTERSECT\b|\bEXCEPT\b|\bJOIN\b|\bINNER\b|\bLEFT\b|\bRIGHT\b|\bFULL\b|"
            r"\bCROSS\b|\bON\b|\bUSING\b|\bSELECT\b|\bVALUES\b|\))",
            r" \1",
            fixed,
            flags=re.I,
        )
        fixed = re.sub(r",\s*\)", ")", fixed)
        fixed = re.sub(r",\s*,", ",", fixed)
        fixed = re.sub(r"\bSELECT\s+,", "SELECT ", fixed, flags=re.I)
        fixed = re.sub(r"\s+\)", ")", fixed)
        fixed = re.sub(r"\s+", " ", fixed).strip()
        return fixed

    def _programmatic_schema_fix(self, sql: str, missing: list, suggestions: dict) -> str:
        fixed = self._clean_sql(sql) or str(sql or "").strip()
        if not fixed:
            return ""

        for name in missing:
            candidates = suggestions.get(name) or []
            if len(candidates) != 1:
                continue

            replacement = candidates[0]
            if not replacement or replacement.lower() == name.lower():
                continue

            pattern = re.compile(r"(?<![\w.])" + re.escape(name) + r"(?![\w.])", re.I)
            fixed = pattern.sub(replacement, fixed)

        return fixed

    def _programmatic_semantic_fix(self, sql: str, error: str) -> str:
        fixed = self._clean_sql(sql) or str(sql or "").strip()
        if not fixed:
            return ""

        err = str(error or "").lower()
        if "division by zero" in err:
            fixed = re.sub(r"/\s*0(?![\d.])", "/ NULLIF(0, 0)", fixed)

        fixed = re.sub(r",\s*\)", ")", fixed)
        fixed = re.sub(r"\s+", " ", fixed).strip()
        return fixed

    def _semantic_hints(self, error: str) -> list:
        err = str(error or "").lower()
        hints = []

        if "group by" in err or "aggregate" in err:
            hints.append(
                "Ensure every non-aggregated SELECT expression is included in GROUP BY, "
                "or wrap it in an aggregate function."
            )
        if "ambiguous" in err:
            hints.append("Qualify ambiguous columns with table names or aliases.")
        if "datatype" in err or "data type" in err or "type mismatch" in err or "conversion" in err:
            hints.append("Use literals, casts, and comparisons compatible with column types.")
        if "division by zero" in err:
            hints.append("Guard division with NULLIF to avoid division by zero.")
        if (
            ("subquery" in err and ("row" in err or "rows" in err))
            or "more than 1 row" in err
            or "more than one row" in err
        ):
            hints.append("Scalar subqueries must return at most one row; use LIMIT 1 or an aggregate if appropriate.")
        if "duplicate" in err or "unique" in err or "constraint" in err:
            hints.append(
                "Remove unintended duplicates caused by joins, filters, or aggregation; "
                "use DISTINCT only when appropriate."
            )
        if "not null" in err:
            hints.append("Avoid NULL where NOT NULL is required; ensure required expressions are present.")

        return hints

    def _missing_identifiers(self, error: str) -> list:
        err = str(error or "")
        found = []

        patterns = (
            r"no such column:?\s*([A-Za-z_][\w\.]*)",
            r"no such table:?\s*([A-Za-z_][\w\.]*)",
            r"no such field:?\s*([A-Za-z_][\w\.]*)",
            r"no such function:?\s*([A-Za-z_][\w\.]*)",
            r"unknown column\s*['\"`]?([\w\.]+)",
            r"unknown table\s*['\"`]?([\w\.]+)",
            r"unknown identifier\s*['\"`]?([\w\.]+)",
            r"column\s*['\"`]?([\w\.]+)['\"` ]*not found",
            r"table\s*['\"`]?([\w\.]+)['\"` ]*not found",
            r"field\s*['\"`]?([\w\.]+)['\"` ]*not found",
            r"relation\s*['\"`]?([\w\.]+)['\"` ]*does not exist",
            r"invalid identifier\s*['\"`]?([\w\.]+)",
            r"invalid column\s*['\"`]?([\w\.]+)",
            r"invalid table\s*['\"`]?([\w\.]+)",
            r"ambiguous column name\s*['\"`]?([\w\.]+)",
            r"has no column named\s*['\"`]?([\w\.]+)",
            r"no column named\s*['\"`]?([\w\.]+)",
        )

        for pattern in patterns:
            for match in re.findall(pattern, err, flags=re.I):
                if match:
                    found.append(match)

        found.extend(re.findall(r"[\"`]([A-Za-z_][A-Za-z0-9_.]*)[\"`]", err))
        found.extend(re.findall(r"\[([A-Za-z_][A-Za-z0-9_.]*)\]", err))

        cleaned = []
        seen = set()
        for name in found:
            name = str(name or "").strip().strip("'\"`[]").strip()
            if not name:
                continue

            key = name.lower()
            if key in seen or key in self._SQL_KEYWORDS:
                continue

            seen.add(key)
            cleaned.append(name)

        return cleaned

    def _identifier_suggestions(self, missing: list) -> dict:
        schema_map = self._schema_identifier_map()
        if not schema_map:
            return {}

        keys = list(schema_map.keys())
        suggestions = {}

        for name in missing:
            bare = name.split(".")[-1].lower().strip()
            candidates = []

            if bare:
                for lower, original in schema_map.items():
                    if lower == bare or bare in lower or lower in bare:
                        self._append_unique(candidates, original)

                for close in difflib.get_close_matches(bare, keys, n=5, cutoff=0.45):
                    self._append_unique(candidates, schema_map[close])

            if "." in name:
                table_part = name.split(".")[0].lower().strip()
                column_part = name.split(".")[-1].strip()
                if table_part:
                    for close in difflib.get_close_matches(table_part, keys, n=3, cutoff=0.50):
                        self._append_unique(candidates, f"{schema_map[close]}.{column_part}")

            suggestions[name] = candidates[:5]

        return suggestions

    def _schema_identifier_map(self) -> dict:
        text = str(self.schema or "")
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
        mapping = {}

        for token in tokens:
            lower = token.lower()
            if len(lower) <= 1 or lower in self._SQL_KEYWORDS:
                continue
            mapping.setdefault(lower, token)

        return mapping

    def _append_unique(self, items: list, value: str) -> None:
        if value and value not in items:
            items.append(value)

    def _classify_error(self, error: str, sql: str) -> str:
        err = str(error or "").lower().strip()
        if not err:
            return self.SEMANTICS

        strong_schema = re.search(
            r"no such (?:table|column|field|function)|unknown (?:column|table|identifier)|"
            r"column not found|table not found|field not found|has no column named|no column named|"
            r"relation .* does not exist|invalid identifier|ambiguous column|missing from-clause entry",
            err,
        )
        if strong_schema:
            return self.SCHEMA

        strong_syntax = re.search(
            r"syntax error|incomplete input|unrecognized token|parse error|"
            r"you have an error in your sql syntax",
            err,
        )
        if strong_syntax:
            return self.SYNTAX

        syntax_score = 0
        schema_score = 0
        semantic_score = 0

        for pattern in self._SYNTAX_PATTERNS:
            if re.search(pattern, err):
                syntax_score += 1

        for pattern in self._SCHEMA_PATTERNS:
            if re.search(pattern, err):
                schema_score += 1

        for pattern in self._SEMANTIC_PATTERNS:
            if re.search(pattern, err):
                semantic_score += 1

        if re.search(
            r"no such (?:table|column|field|function)|unknown (?:column|table|identifier)|"
            r"column not found|table not found|field not found|has no column named|no column named|"
            r"relation .* does not exist|invalid identifier|ambiguous column",
            err,
        ):
            schema_score += 5

        if re.search(
            r"syntax error|incomplete input|unrecognized token|parse error|"
            r"you have an error in your sql syntax|near\s+",
            err,
        ):
            syntax_score += 5

        if re.search(
            r"group by|aggregate|division by zero|type mismatch|datatype|data type|"
            r"more than one row|more than 1 row|subquery returns more than",
            err,
        ):
            semantic_score += 3

        if schema_score > 0 and schema_score >= syntax_score and schema_score >= semantic_score:
            return self.SCHEMA

        if syntax_score > 0 and syntax_score >= semantic_score:
            return self.SYNTAX

        if semantic_score > 0:
            return self.SEMANTICS

        if re.search(r"\bnear\b|expected|unexpected|incomplete|unrecognized|syntax", err):
            return self.SYNTAX

        return self.SEMANTICS

    def _execute_safe(self, sql: str) -> dict:
        sql = self._clean_sql(sql)
        if not sql:
            return {"ok": False, "rows": [], "error": "empty SQL"}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            if "ok" not in result:
                result["ok"] = not bool(result.get("error"))
            return result

        if isinstance(result, (list, tuple)):
            return {"ok": True, "rows": result, "error": ""}

        if result is None:
            return {"ok": True, "rows": [], "error": ""}

        return {"ok": bool(result), "rows": [], "error": "" if result else "execution failed"}

    def _error_text(self, result: dict) -> str:
        if isinstance(result, dict):
            err = result.get("error")
            if err:
                return str(err)
            if result.get("ok") is False:
                return "execution failed"
        return "execution failed"

    def _llm_text(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=n)
        except TypeError:
            try:
                response = self.llm(prompt, system=system, temperature=temperature)
            except TypeError:
                response = self.llm(prompt)
        except Exception:
            return ""

        return self._stringify_llm_response(response)

    def _stringify_llm_response(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore")

        if isinstance(response, str):
            return response

        if isinstance(response, (list, tuple)):
            return self._stringify_llm_response(response[0]) if response else ""

        if isinstance(response, dict):
            for key in ("text", "content", "completion", "answer", "message", "sql", "output"):
                if key in response:
                    return self._stringify_llm_response(response[key])
            return str(response)

        if hasattr(response, "choices"):
            choices = getattr(response, "choices")
            if choices:
                return self._stringify_llm_response(choices[0])

        if hasattr(response, "message"):
            return self._stringify_llm_response(response.message)

        if hasattr(response, "content"):
            return self._stringify_llm_response(response.content)

        if hasattr(response, "text"):
            return self._stringify_llm_response(response.text)

        return str(response)

    def _extract_sql(self, text: str) -> str:
        text = "" if text is None else str(text)

        try:
            extracted = bridge.extract_sql(text)
            if extracted and str(extracted).strip():
                return str(extracted).strip()
        except Exception:
            pass

        if not text.strip():
            return ""

        fence = re.search(r"