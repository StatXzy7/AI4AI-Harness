"""Generate SQL, execute it, classify failures as syntax/schema/semantics, and apply class-specific repairs for up to two rounds."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = str(getattr(self, "schema", "") or "")

        best_sql = self._normalize_sql(self._generate_initial_sql(question, schema))
        last_error = ""
        last_result = {"ok": False, "rows": [], "error": "No attempt executed."}
        attempted = set()

        # Initial attempt plus up to two class-specific repair rounds.
        for round_index in range(self.MAX_REPAIR_ROUNDS + 1):
            if round_index > 0:
                category = self._classify_failure(last_error, last_result)
                repaired = self._apply_fix(
                    category=category,
                    question=question,
                    schema=schema,
                    sql=best_sql,
                    error=last_error,
                    result=last_result,
                )
                repaired = self._normalize_sql(repaired)
                if repaired:
                    best_sql = repaired

            if not best_sql:
                last_error = last_error or "Empty SQL was generated."
                last_result = {"ok": False, "rows": [], "error": last_error}
                if round_index >= self.MAX_REPAIR_ROUNDS:
                    break
                continue

            signature = self._sql_signature(best_sql)
            if signature in attempted:
                break
            attempted.add(signature)

            result = self._execute_safe(best_sql)
            last_result = result

            if result.get("ok"):
                if self._looks_like_select(best_sql):
                    return best_sql

                # Executable but not a query statement: treat as semantic failure.
                last_error = "The executed statement is not a SELECT/WITH query."
                last_result = {
                    "ok": False,
                    "rows": result.get("rows", []),
                    "error": last_error,
                }
                continue

            last_error = str(result.get("error") or "")

        return best_sql or "SELECT 1"

    def _generate_initial_sql(self, question: str, schema: str) -> str:
        prompt = "\n".join(
            [
                "Generate one executable SQL query that answers the question.",
                "Return only SQL, with no markdown and no explanation.",
                "",
                f"Schema:\n{schema}",
                "",
                f"Question:\n{question}",
                "",
                "SQL:",
            ]
        )
        system = "You are a precise text-to-SQL generator. Output exactly one SQL statement."
        return self._extract_sql(self._llm_text(prompt, system=system))

    def _apply_fix(
        self,
        category: str,
        question: str,
        schema: str,
        sql: str,
        error: str,
        result: dict,
    ) -> str:
        if category == "syntax":
            return self._fix_syntax(question, schema, sql, error)
        if category == "schema":
            return self._fix_schema(question, schema, sql, error)
        return self._fix_semantics(question, schema, sql, error)

    def _fix_syntax(self, question: str, schema: str, sql: str, error: str) -> str:
        sql = self._normalize_sql(sql)

        # Strategy-specific local syntax repair before spending an LLM call.
        fast_fixed = self._fast_syntax_fix(sql, error)
        if fast_fixed and fast_fixed != sql:
            return fast_fixed

        prompt = "\n".join(
            [
                "The following SQL failed with a syntax error.",
                "Repair only the syntax. Preserve the intended tables, columns, filters, and logic.",
                "Return only one executable SQL statement, with no markdown or explanation.",
                "",
                f"Database error:\n{self._truncate(error)}",
                "",
                f"Schema:\n{schema}",
                "",
                f"Question:\n{question}",
                "",
                f"Broken SQL:\n{sql}",
                "",
                "Fixed SQL:",
            ]
        )
        system = "You repair SQL syntax errors while preserving the original query intent."
        return self._extract_sql(self._llm_text(prompt, system=system))

    def _fix_schema(self, question: str, schema: str, sql: str, error: str) -> str:
        sql = self._normalize_sql(sql)
        missing = self._extract_missing_object(error)
        candidates = self._schema_candidates(schema, missing)

        notes = []
        if missing:
            notes.append(f"Problematic schema object reported by the database: {missing}.")
        if candidates:
            notes.append(
                "Use only identifiers that exist in the schema. "
                f"Closest valid identifiers: {', '.join(candidates)}."
            )
        if "ambiguous" in str(error).lower():
            notes.append("Qualify ambiguous columns with the appropriate table name or alias.")

        parts = [
            "The following SQL failed because it references the schema incorrectly.",
            "Repair only schema references: table names, column names, aliases, and qualification.",
            "Do not change the intended question semantics. Return only one executable SQL statement.",
        ]
        if notes:
            parts.append("")
            parts.extend(notes)

        parts.extend(
            [
                "",
                f"Schema:\n{schema}",
                "",
                f"Question:\n{question}",
                "",
                f"Database error:\n{self._truncate(error)}",
                "",
                f"Broken SQL:\n{sql}",
                "",
                "Fixed SQL:",
            ]
        )

        prompt = "\n".join(parts)
        system = "You repair SQL schema-reference errors while preserving query intent."
        return self._extract_sql(self._llm_text(prompt, system=system))

    def _fix_semantics(self, question: str, schema: str, sql: str, error: str) -> str:
        sql = self._normalize_sql(sql)
        err = str(error or "").lower()

        notes = []
        if "not a select/with" in err:
            notes.append("The final statement must be a SELECT or WITH query.")
        if "group by" in err:
            notes.append("Ensure every non-aggregated column appears in GROUP BY or is aggregated.")
        if "type" in err or "cast" in err:
            notes.append("Add explicit CASTs or remove type mismatches.")
        if "division by zero" in err:
            notes.append("Guard division with NULLIF or appropriate filters.")
        if "unique" in err or "duplicate" in err:
            notes.append("Remove unintended duplicate rows or adjust joins/DISTINCT.")

        parts = [
            "The following SQL failed because of semantic or logical problems.",
            "Fix aggregation, joins, filters, type casts, and other logic so it answers the question.",
            "Use only tables and columns present in the schema. Return only one executable SQL statement.",
        ]
        if notes:
            parts.append("")
            parts.extend(notes)

        parts.extend(
            [
                "",
                f"Schema:\n{schema}",
                "",
                f"Question:\n{question}",
                "",
                f"Database error:\n{self._truncate(error)}",
                "",
                f"Broken SQL:\n{sql}",
                "",
                "Fixed SQL:",
            ]
        )

        prompt = "\n".join(parts)
        system = "You repair SQL semantic and logical errors while preserving query intent."
        return self._extract_sql(self._llm_text(prompt, system=system))

    def _fast_syntax_fix(self, sql: str, error: str) -> str:
        fixed = self._normalize_sql(sql)
        if not fixed:
            return ""

        # Remove a common trailing-comma syntax error before major clause keywords.
        fixed = re.sub(
            r",\s*(FROM|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|UNION|EXCEPT|INTERSECT)\b",
            r" \1",
            fixed,
            flags=re.IGNORECASE,
        )

        err = str(error or "").lower()
        if ";" in fixed and ('near ";"' in err or "unrecognized token" in err):
            fixed = fixed.replace(";", " ")

        return fixed.strip()

    def _classify_failure(self, error: str, result: dict) -> str:
        err = str(error or "").lower()
        if not err:
            return "semantics"

        syntax_hints = (
            "syntax error",
            "sql syntax",
            "incomplete input",
            "unrecognized token",
            "parse error",
            "expected",
            "malformed",
        )
        if any(hint in err for hint in syntax_hints):
            return "syntax"

        schema_hints = (
            "no such table",
            "no such column",
            "unknown column",
            "unknown table",
            "column not found",
            "table not found",
            "does not exist",
            "doesn't exist",
            "ambiguous column",
            "missing from-clause entry",
            "relation not found",
            "object not found",
            "invalid identifier",
            "invalid column",
            "invalid table",
        )
        if any(hint in err for hint in schema_hints):
            return "schema"

        return "semantics"

    def _extract_missing_object(self, error: str) -> str:
        error = str(error or "")
        patterns = (
            r"no such column:?\s*([A-Za-z_][A-Za-z0-9_.]*)",
            r"no such table:?\s*([A-Za-z_][A-Za-z0-9_.]*)",
            r"""unknown column\s+['"`]?([A-Za-z_][A-Za-z0-9_.]*)""",
            r"""unknown table\s+['"`]?([A-Za-z_][A-Za-z0-9_.]*)""",
            r"""column\s+['"`]?([A-Za-z_][A-Za-z0-9_.]*)['"`]?\s+does not exist""",
            r"""table\s+['"`]?([A-Za-z_][A-Za-z0-9_.]*)['"`]?\s+does not exist""",
            r"""relation\s+['"`]?([A-Za-z_][A-Za-z0-9_.]*)['"`]?\s+does not exist""",
            r"""['"`]([A-Za-z_][A-Za-z0-9_.]*)['"`]?\s+doesn't exist""",
            r"ambiguous column name:?\s*([A-Za-z_][A-Za-z0-9_.]*)",
            r"""missing FROM-clause entry for table\s+['"`]?([A-Za-z_][A-Za-z0-9_.]*)""",
        )

        for pattern in patterns:
            match = re.search(pattern, error, re.IGNORECASE)
            if match:
                return match.group(1).strip("'\"`")

        return ""

    def _schema_candidates(self, schema: str, token: str) -> list:
        token = str(token or "").strip().strip("'\"`").split(".")[-1].lower()
        if not token:
            return []

        identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(schema or "")))
        exact, prefix, substring = [], [], []

        for identifier in identifiers:
            lowered = identifier.lower()
            if lowered == token:
                exact.append(identifier)
            elif lowered.startswith(token):
                prefix.append(identifier)
            elif token in lowered:
                substring.append(identifier)

        candidates = []
        for bucket in (exact, prefix, substring):
            for identifier in sorted(bucket):
                if identifier not in candidates:
                    candidates.append(identifier)

        return candidates[:10]

    def _extract_sql(self, text: str) -> str:
        text = str(text or "")

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        extracted = self._stringify_llm_response(extracted)
        if extracted and extracted.strip():
            return self._normalize_sql(extracted)

        cleaned = text.strip()
        fence = re.search(r"