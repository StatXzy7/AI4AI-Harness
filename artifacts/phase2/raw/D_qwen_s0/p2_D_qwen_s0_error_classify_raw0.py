"""Generate SQL, execute it, classify execution failures as syntax/schema/semantics, and apply class-specific repairs for up to two rounds."""
try:
    from ..harness_base import SQLHarness
    from .. import bridge
except ImportError:
    SQLHarness = object
    bridge = None


class P2P2DQwenS0ErrorClassify(SQLHarness):
    MAX_FIX_ROUNDS = 2
    ERROR_SNIPPET_LIMIT = 1200

    SCHEMA_PATTERNS = (
        "no such table",
        "no such column",
        "no such field",
        "unknown column",
        "unknown table",
        "column not found",
        "table not found",
        "field not found",
        "ambiguous column",
        "invalid column",
        "invalid table",
        "invalid column name",
        "invalid table name",
        "does not exist",
        "relation not found",
        "from-clause entry",
        "cannot find column",
        "cannot find table",
        "unrecognized column",
        "unrecognized table",
    )

    SEMANTIC_PATTERNS = (
        "datatype mismatch",
        "type mismatch",
        "invalid input syntax",
        "invalid value",
        "cannot convert",
        "conversion",
        "misuse",
        "aggregate",
        "group by",
        "having",
        "wrong number of arguments",
        "too many arguments",
        "no such function",
        "not authorized",
        "division by zero",
        "constraint",
        "unique",
        "foreign key",
        "check constraint",
        "out of range",
        "permission denied",
        "invalid use",
        "collate",
    )

    SYNTAX_PATTERNS = (
        "syntax error",
        "syntax",
        "near",
        "incomplete input",
        "unrecognized token",
        "parse error",
        "malformed",
        "invalid sql",
        "unexpected",
        "expected",
        "missing",
        "unclosed",
        "bad sql",
    )

    def solve(self, question: str) -> str:
        sql = self._generate_initial_sql(question)
        if not sql:
            return ""

        current_sql = sql
        result = self._safe_execute(current_sql)
        if result.get("ok"):
            return current_sql

        error = self._error_text(result)
        failure_class = self._classify_failure(error, current_sql, result)
        attempts = []

        for _ in range(self.MAX_FIX_ROUNDS):
            attempts.append(
                {
                    "sql": current_sql,
                    "error": error,
                    "class": failure_class,
                }
            )

            fixed_sql = self._repair(
                question=question,
                sql=current_sql,
                error=error,
                failure_class=failure_class,
                attempts=attempts,
            )

            if not fixed_sql or self._same_sql(fixed_sql, current_sql):
                break

            current_sql = fixed_sql
            result = self._safe_execute(current_sql)

            if result.get("ok"):
                return current_sql

            error = self._error_text(result)
            failure_class = self._classify_failure(error, current_sql, result)

        return current_sql

    def _generate_initial_sql(self, question: str) -> str:
        prompt = self._initial_prompt(question)
        text = self._call_llm(
            prompt,
            system="You are an expert Text-to-SQL assistant. Return only SQL.",
        )
        sql = self._extract_sql(text)
        if sql:
            return sql

        retry_prompt = self._retry_generation_prompt(question)
        text = self._call_llm(
            retry_prompt,
            system="Return only one SQL statement.",
        )
        return self._extract_sql(text)

    def _initial_prompt(self, question: str) -> str:
        return f"""Write one SQL query that answers the question using the schema below.
Return only the SQL query, with no explanation and no markdown.

Schema:
{self._schema_text()}

Question:
{question}

SQL:"""

    def _retry_generation_prompt(self, question: str) -> str:
        return f"""Your previous reply did not contain a SQL query.
Write one SQL query that answers the question using the schema below.
Return only the SQL query.

Schema:
{self._schema_text()}

Question:
{question}

SQL:"""

    def _repair(
        self,
        question: str,
        sql: str,
        error: str,
        failure_class: str,
        attempts: list,
    ) -> str:
        if failure_class == "syntax":
            prompt = self._syntax_prompt(question, sql, error, attempts)
        elif failure_class == "schema":
            prompt = self._schema_prompt(question, sql, error, attempts)
        else:
            prompt = self._semantic_prompt(question, sql, error, attempts)

        system = self._system_for(failure_class)
        text = self._call_llm(prompt, system=system)
        fixed = self._extract_sql(text)

        if not fixed:
            prompt += "\n\nYour previous reply did not contain a SQL statement. Reply with only one SQL statement."
            text = self._call_llm(prompt, system=system)
            fixed = self._extract_sql(text)

        return fixed

    def _syntax_prompt(
        self,
        question: str,
        sql: str,
        error: str,
        attempts: list,
    ) -> str:
        return f"""The SQL query below failed with a syntax error. Fix only the syntax so it can execute.
Do not change the intended tables, columns, filters, joins, aggregation, or result semantics.
Return only the corrected SQL query.

Schema:
{self._schema_text()}

Question:
{question}

Original SQL:
{sql}

Execution error:
{error}
{self._attempts_text(attempts)}

Corrected SQL:"""

    def _schema_prompt(
        self,
        question: str,
        sql: str,
        error: str,
        attempts: list,
    ) -> str:
        return f"""The SQL query below failed because it references invalid database objects.
Use only tables and columns that exist in the schema. Correct table names, column names, aliases,
qualification, and spelling/case as needed while preserving the question intent.
Return only the corrected SQL query.

Schema:
{self._schema_text()}

Question:
{question}

Original SQL:
{sql}

Execution error:
{error}
{self._attempts_text(attempts)}

Corrected SQL:"""

    def _semantic_prompt(
        self,
        question: str,
        sql: str,
        error: str,
        attempts: list,
    ) -> str:
        symptom = error.strip() or "Execution succeeded, but the query is suspected to be semantically wrong."
        return f"""The SQL query below has a semantic or logical SQL problem.
Fix the SQL logic: joins, filters, grouping, aggregation, DISTINCT, LIMIT, functions, value matching,
or other semantic issues. Do not invent tables or columns.
Return only the corrected SQL query.

Schema:
{self._schema_text()}

Question:
{question}

Original SQL:
{sql}

Symptom:
{symptom}
{self._attempts_text(attempts)}

Corrected SQL:"""

    def _attempts_text(self, attempts: list) -> str:
        if not attempts:
            return ""

        lines = ["Previous failed attempts:"]
        for i, attempt in enumerate(attempts[-3:], 1):
            err = str(attempt.get("error") or "")
            if len(err) > 300:
                err = err[:300] + "..."
            lines.append(f"{i}. class={attempt.get('class')}, error={err}")
            lines.append(f"   SQL: {attempt.get('sql')}")
        lines.append("Do not repeat the same mistake.")
        return "\n" + "\n".join(lines)

    def _system_for(self, failure_class: str) -> str:
        if failure_class == "syntax":
            return "You are a SQL syntax repair assistant. Return only corrected SQL."
        if failure_class == "schema":
            return "You are a SQL schema-mapping repair assistant. Return only corrected SQL."
        if failure_class == "semantics":
            return "You are a SQL logic repair assistant. Return only corrected SQL."
        return "You are an expert SQL generator. Return only SQL."

    def _classify_failure(self, error: str, sql: str, result: dict) -> str:
        err = (error or "").lower()
        if not err:
            return "semantics"

        for pattern in self.SCHEMA_PATTERNS:
            if pattern in err:
                return "schema"

        for pattern in self.SEMANTIC_PATTERNS:
            if pattern in err:
                return "semantics"

        for pattern in self.SYNTAX_PATTERNS:
            if pattern in err:
                return "syntax"

        if any(word in err for word in ("column", "table", "relation", "field")):
            return "schema"

        if "near" in err:
            return "syntax"

        return "semantics"

    def _safe_execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        if isinstance(result, (list, tuple)):
            return {"ok": True, "rows": list(result), "error": ""}

        return {
            "ok": bool(result),
            "rows": [],
            "error": "" if result else "Execution failed",
        }

    def _error_text(self, result: dict) -> str:
        err = str(result.get("error") or "") if isinstance(result, dict) else str(result)
        err = err.strip()
        if len(err) > self.ERROR_SNIPPET_LIMIT:
            err = err[: self.ERROR_SNIPPET_LIMIT] + "..."
        return err

    def _same_sql(self, sql_a: str, sql_b: str) -> bool:
        return self._normalize_sql_for_comparison(sql_a) == self._normalize_sql_for_comparison(sql_b)

    def _normalize_sql_for_comparison(self, sql: str) -> str:
        s = (sql or "").strip().rstrip(";").strip()
        return " ".join(s.lower().split())

    def _schema_text(self) -> str:
        return str(getattr(self, "schema", "") or "")

    def _call_llm(self, prompt: str, system: str = "") -> str:
        try:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                raw = self.llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""

        return self._to_text(raw)

    def _to_text(self, raw) -> str:
        if raw is None:
            return ""

        if isinstance(raw, list):
            return self._to_text(raw[0]) if raw else ""

        if isinstance(raw, dict):
            for key in ("text", "content", "completion", "result", "output"):
                if key in raw:
                    return self._to_text(raw[key])
            return str(raw)

        if hasattr(raw, "choices"):
            try:
                return self._to_text(raw.choices[0].message.content)
            except Exception:
                try:
                    return self._to_text(raw.choices[0].text)
                except Exception:
                    return str(raw)

        return str(raw).strip()

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        text = str(text)

        if bridge is not None and hasattr(bridge, "extract_sql"):
            try:
                extracted = bridge.extract_sql(text)
            except Exception:
                extracted = None

            extracted_text = self._to_text(extracted).strip()
            if extracted_text:
                return extracted_text

        return self._fallback_extract_sql(text)

    def _fallback_extract_sql(self, text: str) -> str:
        t = str(text).strip()
        if not t:
            return ""

        if "