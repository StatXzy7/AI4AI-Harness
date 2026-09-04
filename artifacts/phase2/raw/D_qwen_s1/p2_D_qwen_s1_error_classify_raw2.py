"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies targeted repairs for up to two rounds."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2
    PREVIEW_ROWS = 5

    SYNTAX_HINTS = (
        "syntax error",
        "syntaxerror",
        "syntax",
        "parse error",
        "incomplete input",
        "unrecognized token",
        "unexpected end",
        "unexpected token",
        "at or near",
        "malformed",
        "missing keyword",
        "invalid syntax",
        "expected",
    )

    SCHEMA_HINTS = (
        "no such table",
        "no such column",
        "unknown column",
        "unknown table",
        "unknown field",
        "relation does not exist",
        "column does not exist",
        "table does not exist",
        "invalid column",
        "invalid table",
        "ambiguous column",
        "column not found",
        "table not found",
        "field not found",
        "has no column named",
        "no column named",
        "cannot resolve",
        "unresolved relation",
        "object not found",
        "undefined column",
        "undefined table",
    )

    SEMANTIC_HINTS = (
        "semantic",
        "logic error",
        "logic",
        "datatype mismatch",
        "type mismatch",
        "operator does not exist",
        "function does not exist",
        "no such function",
        "aggregate",
        "group by",
        "not allowed",
        "constraint",
        "division by zero",
        "subquery returns more than 1 row",
        "invalid use",
        "wrong number of arguments",
        "foreign key",
        "check constraint",
        "unique constraint",
    )

    def solve(self, question: str) -> str:
        question = str(question or "").strip()
        sql = self._generate_initial_sql(question)
        best_ok_sql = ""

        last_class = "semantics"
        last_issue = ""
        last_rows = None

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._execute_safe(sql)

            if result.get("ok"):
                best_ok_sql = sql
                last_rows = result.get("rows")

                issue = self._semantic_issue(question, sql, last_rows)
                if not issue:
                    return sql

                last_class = "semantics"
                last_issue = issue
            else:
                last_rows = None
                last_issue = result.get("error") or "Execution failed"
                last_class = self._classify_failure(question, sql, last_issue)

            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break

            repaired = self._repair_sql(
                question=question,
                sql=sql,
                failure_class=last_class,
                issue=last_issue,
                rows=last_rows,
            )

            if not repaired:
                repaired = self._repair_generic(question, sql, last_issue)

            if not repaired:
                break

            if self._normalize_sql(repaired) == self._normalize_sql(sql):
                break

            sql = repaired

        return best_ok_sql or sql

    def _schema_text(self) -> str:
        return str(getattr(self, "schema", "") or "")

    def _generate_initial_sql(self, question: str) -> str:
        system = "You are an expert Text-to-SQL system. Return only a single executable SQL query."
        prompt = (
            "Produce one SQL query that answers the question.\n"
            "Return only SQL, no explanation, no markdown.\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        text = self._llm_text(prompt, system=system)
        sql = self._extract_sql(text)
        if sql:
            return sql

        retry_prompt = (
            prompt
            + "\n\nYour previous response did not contain a query. "
            "Return only one SQL query, beginning with SELECT or WITH."
        )
        text = self._llm_text(retry_prompt, system=system)
        sql = self._extract_sql(text)
        return sql or "SELECT 1"

    def _repair_sql(self, question: str, sql: str, failure_class: str, issue: str, rows):
        failure_class = str(failure_class or "semantics").lower()
        schema = self._schema_text()

        if failure_class == "syntax":
            system = "You fix SQL syntax errors. Return only one corrected SQL query."
            prompt = f"""The following SQL query failed with a syntax error.
Fix only the syntax problem while preserving the intended logic.
Return only one corrected SQL query, no explanation.

Question: {question}

Schema:
{schema}

Current SQL:
{sql}

Error:
{self._truncate(issue, 1200)}

Corrected SQL:"""

        elif failure_class == "schema":
            system = "You repair SQL queries that reference invalid database objects. Return only one corrected SQL query."
            prompt = f"""The following SQL query failed because it references invalid database objects.
Rewrite it using only tables and columns that exist in the schema.
Correct misspellings, qualify ambiguous columns, and add missing joins if needed.
Return only one corrected SQL query, no explanation.

Question: {question}

Schema:
{schema}

Current SQL:
{sql}

Error:
{self._truncate(issue, 1200)}

Corrected SQL:"""

        else:
            system = "You repair SQL query logic. Return only one corrected SQL query."
            result_context = self._format_rows(rows) if rows is not None else "Query did not execute successfully."
            prompt = f"""The following SQL query does not correctly answer the question.
Fix the query logic, including selected columns, joins, filters, grouping, aggregation, ordering, limits, or type usage.
Return only one corrected SQL query, no explanation.

Question: {question}

Schema:
{schema}

Current SQL:
{sql}

Problem:
{self._truncate(issue, 1500)}

Execution result sample:
{result_context}

Corrected SQL:"""

        text = self._llm_text(prompt, system=system)
        return self._extract_sql(text)

    def _repair_generic(self, question: str, sql: str, issue: str) -> str:
        system = "You repair SQL queries. Return only one executable SQL query."
        prompt = f"""Repair the following SQL query so it executes correctly and answers the question.
Return only one corrected SQL query, no explanation.

Question: {question}

Schema:
{self._schema_text()}

Current SQL:
{sql}

Problem:
{self._truncate(issue, 1200)}

Corrected SQL:"""

        text = self._llm_text(prompt, system=system)
        return self._extract_sql(text)

    def _classify_failure(self, question: str, sql: str, error: str) -> str:
        e = str(error or "").lower()
        if not e:
            return "semantics"

        if any(hint in e for hint in self.SYNTAX_HINTS):
            return "syntax"

        if any(hint in e for hint in self.SEMANTIC_HINTS):
            return "semantics"

        if any(hint in e for hint in self.SCHEMA_HINTS):
            return "schema"

        objects = ("table", "column", "relation", "field")
        signals = (
            "not found",
            "does not exist",
            "unknown",
            "invalid",
            "no such",
            "cannot resolve",
            "undefined",
        )
        if any(obj in e for obj in objects) and any(sig in e for sig in signals):
            return "schema"

        system = "You classify SQL failures. Return exactly one word: syntax, schema, or semantics."
        prompt = f"""Classify the SQL failure category.

Categories:
- syntax: the SQL cannot be parsed.
- schema: the SQL references tables/columns that do not exist or are ambiguous.
- semantics: the SQL parses and references valid objects but is logically or type-wise wrong.

Question: {question}

SQL:
{self._truncate(sql, 1000)}

Error:
{self._truncate(error, 1000)}

Category:"""

        response = self._llm_text(prompt, system=system).strip().lower()
        if "syntax" in response:
            return "syntax"
        if "schema" in response:
            return "schema"
        if "semantic" in response:
            return "semantics"

        return "semantics"

    def _semantic_issue(self, question: str, sql: str, rows):
        preview = self._format_rows(rows)
        system = "You are a strict Text-to-SQL validator. First line must be exactly VALID or INVALID."
        prompt = f"""Decide whether the SQL query likely answers the question.
Ignore style. Do not mark INVALID merely because the sample is empty or small.
Return INVALID only if the query is clearly wrong for the question.
First line must be exactly VALID or INVALID.

Question: {question}

SQL:
{sql}

Sample result:
{preview}

Judgment:"""

        response = self._llm_text(prompt, system=system)
        if not response:
            return ""

        first_line = response.strip().splitlines()[0].strip().upper()
        if not first_line:
            return ""

        first_token = first_line.split()[0] if first_line.split() else ""
        first_token = re.sub(r"[^A-Z]", "", first_token)

        if first_token == "INVALID" or first_line.startswith("INVALID"):
            return response.strip()

        return ""

    def _execute_safe(self, sql: str):
        sql = str(sql or "").strip()
        if not sql:
            return {"ok": False, "rows": [], "error": "Empty SQL"}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return {
                "ok": bool(result.get("ok", False)),
                "rows": result.get("rows", []),
                "error": result.get("error", "") or "",
            }

        return {
            "ok": True,
            "rows": result if result is not None else [],
            "error": "",
        }

    def _format_rows(self, rows) -> str:
        if rows is None:
            return "No rows returned."

        try:
            iterator = iter(rows)
        except TypeError:
            return self._truncate(str(rows), 500)

        preview = []
        count = 0

        for row in iterator:
            if count < self.PREVIEW_ROWS:
                preview.append(row)
            count += 1
            if count >= 1000:
                break

        if count == 0:
            return "0 rows returned."

        count_label = f"{count}+" if count >= 1000 else str(count)
        lines = [f"{count_label} rows returned; showing first {len(preview)}:"]

        for row in preview:
            row_text = str(row)
            if len(row_text) > 300:
                row_text = row_text[:300] + "..."
            lines.append(row_text)

        return "\n".join(lines)

    def _truncate(self, text, limit: int) -> str:
        text = str(text or "")
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[truncated]"

    def _normalize_sql(self, sql: str) -> str:
        s = str(sql or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        s = s.rstrip(";").strip()
        return s

    def _extract_sql(self, text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return ""

        candidate = ""
        try:
            candidate = bridge.extract_sql(text)
        except Exception:
            candidate = ""

        if isinstance(candidate, (list, tuple)):
            candidate = candidate[0] if candidate else ""

        candidate = self._postprocess_sql(candidate)
        if candidate:
            return candidate

        fence = re.search(r"