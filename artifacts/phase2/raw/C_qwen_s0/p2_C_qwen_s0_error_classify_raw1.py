"""Generate SQL, execute it, classify failures as syntax, schema, or semantics, and apply class-specific repair prompts for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS0ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)
        best_sql = sql

        result = self._execute_safe(sql)
        if result.get("ok"):
            return self._clean_sql(sql)

        error = self._error_text(result)
        category = self._classify_failure(error, sql)

        for round_idx in range(2):
            if category == "syntax":
                candidate = self._fix_syntax(question, sql, error, round_idx)
            elif category == "schema":
                candidate = self._fix_schema(question, sql, error, round_idx)
            else:
                candidate = self._fix_semantics(question, sql, error, round_idx)

            if candidate:
                sql = candidate
                best_sql = sql

            result = self._execute_safe(sql)
            if result.get("ok"):
                return self._clean_sql(sql)

            error = self._error_text(result)
            category = self._classify_failure(error, sql)

        return self._clean_sql(best_sql or sql or "")

    def _schema_text(self):
        return str(getattr(self, "schema", "") or "")

    def _generate_initial(self, question):
        system = "You are an expert Text-to-SQL system. Return only one executable SQL query."
        prompt = (
            "Write a SQL query that answers the question.\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"Question:\n{question}\n\n"
            "Return only SQL, no explanation, no markdown."
        )
        return self._ask_llm(prompt, system)

    def _fix_syntax(self, question, sql, error, round_idx):
        system = "You are a SQL syntax repairer. Return only one executable SQL query."
        prompt = (
            f"Repair round {round_idx + 1} of 2: the SQL query has a syntax error.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"Failing SQL:\n{sql or '(no SQL)'}\n\n"
            f"Execution error:\n{error}\n\n"
            "Fix the syntax error only. Preserve the original intent. "
            "Return only corrected SQL, no explanation, no markdown."
        )
        return self._ask_llm(prompt, system)

    def _fix_schema(self, question, sql, error, round_idx):
        system = "You are a SQL schema-alignment repairer. Return only one executable SQL query."
        prompt = (
            f"Repair round {round_idx + 1} of 2: the SQL query references invalid tables or columns.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"Failing SQL:\n{sql or '(no SQL)'}\n\n"
            f"Execution error:\n{error}\n\n"
            "Use only tables and columns that appear exactly in the schema. "
            "Qualify column names when needed and remove nonexistent fields. "
            "Return only corrected SQL, no explanation, no markdown."
        )
        return self._ask_llm(prompt, system)

    def _fix_semantics(self, question, sql, error, round_idx):
        system = "You are a SQL semantic repairer. Return only one executable SQL query."
        prompt = (
            f"Repair round {round_idx + 1} of 2: the SQL query has a semantic/runtime problem.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"Failing SQL:\n{sql or '(no SQL)'}\n\n"
            f"Execution error:\n{error}\n\n"
            "Rewrite the query so it is semantically valid and still answers the question. "
            "Fix aggregation, GROUP BY, joins, predicates, and function usage. "
            "Return only corrected SQL, no explanation, no markdown."
        )
        return self._ask_llm(prompt, system)

    def _ask_llm(self, prompt, system):
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        text = self._response_text(response)
        extracted = ""
        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        extracted = self._response_text(extracted)
        sql = self._clean_sql(extracted)
        if sql:
            return sql

        text = self._clean_sql(text)
        if self._looks_like_sql(text):
            return text
        return ""

    def _response_text(self, response):
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            for item in response:
                text = self._response_text(item)
                if text:
                    return text
            return ""
        if isinstance(response, dict):
            for key in ("content", "text", "completion", "output", "message", "sql"):
                if key in response:
                    text = self._response_text(response[key])
                    if text:
                        return text
            choices = response.get("choices")
            if isinstance(choices, (list, tuple)):
                for choice in choices:
                    text = self._response_text(choice)
                    if text:
                        return text
            return ""
        return str(response)

    def _execute_safe(self, sql):
        cleaned = self._clean_sql(sql)
        if not cleaned:
            return {"ok": False, "rows": [], "error": "Empty SQL query."}

        try:
            result = self.execute(cleaned)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return {
                "ok": bool(result.get("ok", False)),
                "rows": result.get("rows", []),
                "error": str(result.get("error", "") or ""),
            }

        return {
            "ok": bool(result),
            "rows": [],
            "error": "" if result else "Execution failed.",
        }

    def _error_text(self, result):
        if isinstance(result, dict):
            error = result.get("error")
            if error:
                return str(error)
            if not result.get("ok"):
                return "Execution failed"
        return ""

    def _classify_failure(self, error, sql):
        if not self._clean_sql(sql):
            return "syntax"

        err = (error or "").lower()
        if not err:
            return "semantics"

        syntax_markers = (
            "syntax error",
            "incomplete input",
            "unrecognized token",
            "unexpected token",
            "unexpected end",
            'near "',
            "near '",
            "parser",
            "parse error",
            "malformed",
            "unclosed",
            "mismatched",
        )
        semantic_markers = (
            "no such function",
            "wrong number of arguments",
            "aggregate",
            "group by",
            "datatype",
            "data type",
            "type mismatch",
            "division by zero",
            "misuse",
            "not a valid",
        )
        schema_markers = (
            "no such table",
            "no such column",
            "no such field",
            "unknown table",
            "unknown column",
            "unknown identifier",
            "table not found",
            "column not found",
            "field not found",
            'relation "',
            "does not exist",
            "invalid column",
            "invalid table",
            "ambiguous column",
            "ambiguous reference",
            "cannot find",
            "could not find",
        )

        for marker in syntax_markers:
            if marker in err:
                return "syntax"

        for marker in semantic_markers:
            if marker in err:
                return "semantics"

        for marker in schema_markers:
            if marker in err:
                return "schema"

        if ("table" in err or "column" in err or "field" in err) and any(
            word in err
            for word in ("not found", "does not exist", "unknown", "invalid", "missing")
        ):
            return "schema"

        return "semantics"

    def _looks_like_sql(self, text):
        if not text:
            return False
        compact = " ".join(text.lower().split())
        prefixes = (
            "select",
            "with",
            "insert",
            "update",
            "delete",
            "create",
            "drop",
            "explain",
            "pragma",
            "values",
        )
        if compact.startswith(prefixes):
            return True
        keywords = (
            "select ",
            "insert into ",
            "update ",
            "delete from ",
            "create table ",
        )
        return any(keyword in compact for keyword in keywords)

    def _clean_sql(self, sql):
        if sql is None:
            return ""
        text = str(sql).strip()
        if not text:
            return ""

        if text.startswith("