"""Generate SQL, execute it, classify failures as syntax/schema/semantics, and apply class-specific repairs for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS0ErrorClassify(SQLHarness):
    MAX_FIX_ROUNDS = 2

    def solve(self, question: str) -> str:
        sql = self._generate_initial_sql(question)
        best_sql = sql

        for round_idx in range(self.MAX_FIX_ROUNDS + 1):
            sql = self._clean_sql(sql)
            if not sql:
                break

            result = self._execute_safe(sql)

            if result.get("ok"):
                if self._row_count(result.get("rows")) > 0:
                    return sql
                failure_class = "semantics"
                error_text = "The query executed successfully but returned no rows."
            else:
                failure_class = self._classify_error(str(result.get("error") or ""))
                error_text = str(result.get("error") or "unknown execution error")

            best_sql = sql
            if round_idx >= self.MAX_FIX_ROUNDS:
                break

            repaired = self._repair_sql(question, sql, failure_class, error_text, result)
            repaired = self._clean_sql(repaired)
            if not repaired or self._sql_key(repaired) == self._sql_key(sql):
                break
            sql = repaired

        return self._clean_sql(best_sql or sql or "")

    def _generate_initial_sql(self, question: str) -> str:
        system = "You are a precise Text-to-SQL engine. Output only a single SQL query."
        prompt = (
            "Write one SQL query that answers the question using only the provided schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Output only the SQL query."
        )
        return self._clean_sql(self._llm_text(prompt, system=system))

    def _repair_sql(self, question: str, sql: str, failure_class: str, error_text: str, result: dict) -> str:
        row_count = self._row_count(result.get("rows")) if isinstance(result, dict) else 0

        if failure_class == "syntax":
            system = "You repair SQL syntax errors. Output only a single corrected SQL query."
            objective = (
                "Fix the syntax error so the query can execute. "
                "Preserve the original question intent and avoid changing schema references unless required."
            )
        elif failure_class == "schema":
            system = "You repair SQL schema errors. Output only a single corrected SQL query."
            objective = (
                "Fix table and column references so they exactly match the provided schema. "
                "Use valid identifiers, qualify ambiguous columns, and preserve the query intent."
            )
        else:
            system = "You repair SQL semantics errors. Output only a single corrected SQL query."
            objective = (
                "The query executed but likely does not answer the question correctly. "
                "Revise the query logic (joins, filters, grouping, aggregation, DISTINCT, literals, "
                "case sensitivity, date/numeric comparisons) so the result matches the question."
            )

        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Current SQL:
{sql}

Failure class:
{failure_class}

Execution problem:
{error_text}

Rows returned by current SQL:
{row_count}

Repair objective:
{objective}

Return only one corrected SQL query.
"""
        return self._llm_text(prompt, system=system)

    def _llm_text(self, prompt: str, system: str = "") -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        return self._response_to_text(response)

    def _response_to_text(self, response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            parts = [self._response_to_text(item) for item in response]
            return "\n".join(part for part in parts if part)
        if isinstance(response, dict):
            for key in ("text", "content", "output", "completion", "message", "result"):
                if key in response:
                    return self._response_to_text(response[key])
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                return self._response_to_text(choices[0])

        if hasattr(response, "choices"):
            choices = getattr(response, "choices")
            if isinstance(choices, (list, tuple)) and choices:
                return self._response_to_text(choices[0])
        for attr in ("text", "content", "output", "completion", "message", "result"):
            if hasattr(response, attr):
                return self._response_to_text(getattr(response, attr))

        return str(response)

    def _execute_safe(self, sql: str) -> dict:
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "Empty SQL."}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return {
                "ok": bool(result.get("ok", False)),
                "rows": result.get("rows", []),
                "error": str(result.get("error", "") or ""),
            }
        if isinstance(result, bool):
            return {"ok": result, "rows": [], "error": "" if result else "Execution failed."}
        if isinstance(result, (list, tuple)):
            return {"ok": True, "rows": list(result), "error": ""}
        if result is None:
            return {"ok": False, "rows": [], "error": "Execution returned no result."}
        return {"ok": True, "rows": [result], "error": ""}

    def _classify_error(self, error: str) -> str:
        text = str(error or "").lower()
        if not text:
            return "semantics"

        strong_schema = (
            "no such table",
            "no such column",
            "unknown table",
            "unknown column",
            "table not found",
            "column not found",
            "field not found",
            "missing table",
            "missing column",
            "missing field",
            "does not exist",
            "doesn't exist",
            "invalid column",
            "invalid object name",
            "ambiguous column",
            "undefined column",
            "undefined table",
            "unknown identifier",
            "identifier not found",
            "cannot resolve",
            "could not resolve",
        )
        if any(marker in text for marker in strong_schema):
            return "schema"

        syntax = (
            "syntax",
            "parse",
            "near",
            "unexpected",
            "expected",
            "invalid input",
            "unrecognized token",
            "incomplete input",
            "truncated",
            "mismatched input",
            "extraneous input",
            "missing",
            "unclosed",
            "unbalanced",
            "illegal",
            "malformed",
            "unterminated",
            "not a valid",
        )
        if any(marker in text for marker in syntax):
            return "syntax"

        return "semantics"

    def _clean_sql(self, text) -> str:
        if text is None:
            return ""
        text = str(text).strip()
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        if extracted:
            sql = str(extracted).strip()
        else:
            sql = self._fallback_extract_sql(text)

        sql = self._strip_code_fences(sql)
        sql = self._first_statement(sql)
        return sql.strip()

    def _fallback_extract_sql(self, text: str) -> str:
        text = self._strip_code_fences(text)
        upper = text.upper()
        keywords = ("WITH", "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")
        positions = [upper.find(keyword) for keyword in keywords if upper.find(keyword) != -1]
        if positions:
            return text[min(positions):].strip()
        return text.strip()

    def _strip_code_fences(self, text: str) -> str:
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("