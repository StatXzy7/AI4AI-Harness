"""Generate SQL, execute it, classify failures as syntax/schema/semantics, and apply class-specific repairs for up to two rounds."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = str(getattr(self, "schema", "") or "")

        sql = self._initial_sql(question, schema)
        best_sql = sql
        current_sql = sql

        if current_sql:
            result = self._safe_execute(current_sql)
            if result.get("ok") and self._looks_like_select(current_sql):
                return current_sql
            if result.get("ok"):
                result = self._non_select_failure(result)
        else:
            result = {"ok": False, "rows": [], "error": "No SQL was generated."}

        for round_idx in range(self.MAX_REPAIR_ROUNDS):
            category = self._classify_failure(current_sql, result)
            fixed_sql = self._repair_sql(
                category,
                question,
                schema,
                current_sql,
                result,
                round_idx,
            )

            if not fixed_sql:
                if not best_sql and round_idx == self.MAX_REPAIR_ROUNDS - 1:
                    best_sql = "SELECT 1"
                continue

            current_sql = fixed_sql
            best_sql = fixed_sql
            result = self._safe_execute(current_sql)

            if result.get("ok") and self._looks_like_select(current_sql):
                return current_sql
            if result.get("ok"):
                result = self._non_select_failure(result)

        return best_sql or "SELECT 1"

    def _initial_sql(self, question: str, schema: str) -> str:
        system = (
            "You are an expert Text-to-SQL system. "
            "Output only one executable SQL query."
        )
        prompt = "\n\n".join(
            [
                "Generate a SQL query that answers the question.",
                f"Schema:\n{schema}",
                f"Question:\n{question}",
                "\n".join(
                    [
                        "Rules:",
                        "- Use only tables and columns present in the schema.",
                        "- Use SQLite-compatible SQL.",
                        "- Return only the SQL query, without markdown or explanations.",
                    ]
                ),
            ]
        )
        return self._extract_sql(self._llm_text(prompt, system=system))

    def _repair_sql(
        self,
        category: str,
        question: str,
        schema: str,
        sql: str,
        result: dict,
        round_idx: int,
    ) -> str:
        category = category if category in {"syntax", "schema", "semantics"} else "semantics"

        systems = {
            "syntax": (
                "You repair SQL syntax errors. Preserve the original intent. "
                "Output only one corrected executable SQL query."
            ),
            "schema": (
                "You repair SQL schema errors. Use only exact table and column names "
                "from the provided schema. Output only one corrected executable SQL query."
            ),
            "semantics": (
                "You repair SQL semantic and logic errors. Make the query correctly "
                "answer the question. Output only one corrected executable SQL query."
            ),
        }

        checklists = {
            "syntax": "\n".join(
                [
                    "- Fix grammar, punctuation, keywords, quoting, and statement termination.",
                    "- Keep the original question intent unchanged.",
                    "- Produce a single SQLite-compatible SELECT or WITH ... SELECT statement.",
                    "- Do not include markdown, explanations, or multiple statements.",
                ]
            ),
            "schema": "\n".join(
                [
                    "- Use only tables and columns that exist in the schema.",
                    "- Replace missing or misspelled schema objects with the closest valid ones.",
                    "- Qualify ambiguous columns with table names or aliases.",
                    "- Preserve the original question intent as much as possible.",
                ]
            ),
            "semantics": "\n".join(
                [
                    "- Fix logic problems such as joins, filters, aggregation, GROUP BY, DISTINCT, ordering, casts, and date handling.",
                    "- Ensure the query returns the columns and rows needed to answer the question.",
                    "- Use only valid schema objects and SQLite-compatible constructs.",
                    "- The final statement must be a SELECT or WITH ... SELECT query.",
                ]
            ),
        }

        error = str(result.get("error") or "unknown execution error")
        parts = [
            f"Repair round {round_idx + 1} of {self.MAX_REPAIR_ROUNDS}.",
            f"The previous SQL failed with a {category} problem.",
            f"Question:\n{question}",
            f"Schema:\n{schema}",
        ]

        if sql:
            parts.append(f"Previous SQL:\n{sql}")
        else:
            parts.append("No previous SQL was extracted.")

        parts.append(f"Execution error:\n{error}")

        if category == "semantics":
            rows_sample = self._format_rows(result.get("rows"))
            if rows_sample:
                parts.append(f"Execution result sample:\n{rows_sample}")

        parts.append(f"Fix checklist:\n{checklists[category]}")
        parts.append("Output only the corrected SQL query. No markdown, no explanations.")

        return self._extract_sql(self._llm_text("\n\n".join(parts), system=systems[category]))

    def _classify_failure(self, sql: str, result: dict) -> str:
        if not sql or not str(sql).strip():
            return "syntax"

        error = str(result.get("error") or "").lower()
        if not error:
            return "semantics"

        if "does not look like a select" in error:
            return "semantics"

        if re.search(
            r"(function|operator|cast|type).*does not exist|no such function|unknown function",
            error,
        ):
            return "semantics"

        if re.search(
            r"(table|column|field|relation)\b.*does not exist|does not exist.*\b(table|column|field|relation)\b",
            error,
        ):
            return "schema"

        schema_terms = (
            "no such table",
            "no such column",
            "no column named",
            "has no column",
            "unknown column",
            "unknown table",
            "table not found",
            "column not found",
            "field not found",
            "invalid table",
            "invalid column",
            "ambiguous column",
            "column reference",
            "relation",
            "cannot resolve",
            "unrecognized column",
            "not a valid table",
            "not a valid column",
            "table or column not found",
            "missing table",
            "missing column",
            "table does not exist",
            "column does not exist",
            "field does not exist",
            "relation does not exist",
        )

        syntax_terms = (
            "syntax error",
            "syntax",
            "near",
            "parse error",
            "parse",
            "incomplete input",
            "unrecognized token",
            "unexpected token",
            "unexpected",
            "expected",
            "malformed",
            "invalid sql",
            "bad sql",
            "compile error",
            "unclosed",
            "missing",
            "extraneous",
            "illegal",
            "invalid input",
        )

        semantic_terms = (
            "datatype mismatch",
            "type mismatch",
            "aggregate",
            "group by",
            "misuse of aggregate",
            "wrong number of arguments",
            "no such function",
            "unknown function",
            "conversion",
            "unique constraint",
            "foreign key",
            "check constraint",
            "constraint",
            "division by zero",
            "overflow",
            "underflow",
            "subquery",
            "cardinality",
            "ambiguous",
            "invalid value",
            "out of range",
            "cannot convert",
            "null value",
            "not a valid date",
            "not a valid month",
        )

        schema_score = sum(1 for term in schema_terms if term in error)
        syntax_score = sum(1 for term in syntax_terms if term in error)
        semantic_score = sum(1 for term in semantic_terms if term in error)

        if schema_score > 0 and schema_score >= syntax_score and schema_score >= semantic_score:
            return "schema"
        if syntax_score > 0 and syntax_score >= semantic_score:
            return "syntax"
        if semantic_score > 0:
            return "semantics"

        if re.search(
            r"no such (table|column)|unknown (table|column)|column .* does not exist|table .* does not exist",
            error,
        ):
            return "schema"

        if re.search(
            r"syntax error|parse error|incomplete input|unrecognized token|unexpected token|near\b",
            error,
        ):
            return "syntax"

        return "semantics"

    def _safe_execute(self, sql: str) -> dict:
        if not sql or not str(sql).strip():
            return {"ok": False, "rows": [], "error": "No SQL to execute."}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {exc}"}

        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": f"Unexpected executor result: {result!r}"}

        result.setdefault("ok", False)
        result.setdefault("rows", [])
        result.setdefault("error", "")
        return result

    def _llm_text(self, prompt: str, system: str = "") -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        return self._response_to_text(response)

    def _response_to_text(self, response, depth: int = 0) -> str:
        if depth > 3:
            return str(response)
        if response is None:
            return ""
        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore")
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            return self._response_to_text(response[0], depth + 1) if response else ""
        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output", "sql", "response"):
                if key in response:
                    return self._response_to_text(response[key], depth + 1)
            return str(response)

        for attr in ("text", "content", "completion", "output"):
            if hasattr(response, attr):
                return self._response_to_text(getattr(response, attr), depth + 1)

        return str(response)

    def _extract_sql(self, text: str) -> str:
        if text is None:
            return ""

        text = str(text)

        try:
            extracted = bridge.extract_sql(text)
            if isinstance(extracted, (list, tuple)):
                extracted = extracted[0] if extracted else ""
            if isinstance(extracted, dict):
                extracted = self._response_to_text(extracted)
            if extracted is not None:
                extracted = str(extracted).strip()
                if extracted:
                    return self._clean_sql(extracted)
        except Exception:
            pass

        fence = re.search(r"