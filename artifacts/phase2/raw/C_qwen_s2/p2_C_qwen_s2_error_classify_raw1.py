"""Executes generated SQL, classifies failures as syntax/schema/semantics, and applies class-specific repairs for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge

import re


class P2P2CQwenS2ErrorClassify(SQLHarness):
    MAX_FIX_ROUNDS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        sql = self._normalize_sql(self._initial_sql(question))
        if not sql:
            sql = "SELECT 1"

        best_sql = sql
        best_ok_sql = None
        last_sql = sql
        seen = set()

        for round_idx in range(self.MAX_FIX_ROUNDS + 1):
            canonical = self._canonical_sql(sql)
            if canonical in seen:
                if best_ok_sql:
                    return best_ok_sql
                break
            seen.add(canonical)
            last_sql = sql

            result = self._safe_execute(sql)
            ok = bool(result.get("ok"))
            error = str(result.get("error") or "")
            rows = result.get("rows") or []

            if ok:
                best_ok_sql = sql
                semantic_issue, semantic_reason = self._semantic_issue(question, sql, rows)
                if not semantic_issue:
                    return sql
                category = "semantics"
                reason = semantic_reason or "The query executed but likely does not answer the question."
                repair_rows = rows
            else:
                category = self._classify_error(error, sql)
                reason = error or "Execution failed."
                repair_rows = []

            if round_idx >= self.MAX_FIX_ROUNDS:
                break

            fixed = self._repair(question, sql, category, reason, repair_rows)
            fixed = self._normalize_sql(fixed)
            if not fixed:
                break
            sql = fixed

        if best_ok_sql:
            return best_ok_sql
        return last_sql or best_sql or "SELECT 1"

    def _initial_sql(self, question: str) -> str:
        prompt = (
            "You are an expert Text-to-SQL system.\n"
            f"{self._context_block(question)}\n\n"
            "Generate one executable SQL query that answers the question.\n"
            "Output only the SQL query, with no explanation and no markdown.\n"
        )
        raw = self._llm_text(
            prompt,
            system="You translate natural language questions into SQL. Output only SQL.",
        )
        return self._extract_sql(raw)

    def _repair(self, question: str, sql: str, category: str, reason: str, rows):
        category = (category or "syntax").lower().strip()
        if category == "schema":
            return self._repair_schema(question, sql, reason)
        if category == "semantics":
            return self._repair_semantics(question, sql, reason, rows)
        return self._repair_syntax(question, sql, reason)

    def _repair_syntax(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "You are repairing a SQL query with a syntax error.\n"
            f"{self._context_block(question)}\n\n"
            f"Current SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Fix only the syntax problem: punctuation, clause order, quoting, parentheses, keywords, or malformed tokens.\n"
            "Preserve the original intent as much as possible.\n"
            "Output only the corrected SQL query.\n"
        )
        raw = self._llm_text(prompt, system="You fix SQL syntax errors. Output only SQL.")
        return self._extract_sql(raw)

    def _repair_schema(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "You are repairing a SQL query that references invalid schema objects.\n"
            f"{self._context_block(question)}\n\n"
            f"Current SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Fix only schema-reference problems: use exact table names and column names from the schema, qualify columns, "
            "correct aliases, and remove or replace nonexistent objects.\n"
            "Keep the question intent unchanged.\n"
            "Output only the corrected SQL query.\n"
        )
        raw = self._llm_text(prompt, system="You repair SQL schema reference errors. Output only SQL.")
        return self._extract_sql(raw)

    def _repair_semantics(self, question: str, sql: str, reason: str, rows) -> str:
        rows_summary = self._rows_summary(rows)
        if rows:
            status = "The query executed, but its result likely does not answer the question."
        else:
            status = "The query did not produce a plausible answer for the question."
        prompt = (
            "You are repairing a SQL query with a semantic problem.\n"
            f"{self._context_block(question)}\n\n"
            f"Current SQL:\n{sql}\n\n"
            f"Problem:\n{reason}\n\n"
            f"{status}\n"
            f"Result summary:\n{rows_summary}\n\n"
            "Rewrite the query so it directly answers the question. Fix selected columns, filters, joins, grouping, "
            "aggregation, ordering, LIMIT, or DISTINCT as needed.\n"
            "Output only the corrected SQL query.\n"
        )
        raw = self._llm_text(prompt, system="You repair SQL semantic errors. Output only SQL.")
        return self._extract_sql(raw)

    def _safe_execute(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {exc}"}

        if isinstance(result, dict):
            return {
                "ok": bool(result.get("ok", False)),
                "rows": result.get("rows", []) or [],
                "error": str(result.get("error", "") or ""),
            }

        return {"ok": True, "rows": result if isinstance(result, list) else [], "error": ""}

    def _classify_error(self, error: str, sql: str) -> str:
        e = (error or "").lower()
        if not e.strip():
            return "syntax"

        schema_terms = [
            "no such table",
            "no such column",
            "unknown column",
            "invalid column",
            "column not found",
            "table not found",
            "does not exist",
            "ambiguous column",
            "invalid identifier",
            "unrecognized table",
            "unrecognized column",
        ]
        syntax_terms = [
            "syntax error",
            "syntax",
            "near",
            "incomplete input",
            "unrecognized token",
            "expected",
            "parse error",
            "malformed",
            "unclosed",
            "invalid input",
            "incomplete",
        ]
        semantic_terms = [
            "datatype mismatch",
            "type mismatch",
            "conversion",
            "division by zero",
            "overflow",
            "constraint",
            "foreign key",
            "unique",
            "check constraint",
            "semantic",
        ]

        schema_score = sum(1 for term in schema_terms if term in e)
        syntax_score = sum(1 for term in syntax_terms if term in e)
        semantic_score = sum(1 for term in semantic_terms if term in e)

        if schema_score and schema_score >= syntax_score and schema_score >= semantic_score:
            return "schema"
        if syntax_score > semantic_score:
            return "syntax"
        if semantic_score:
            return "semantics"

        llm_category = self._llm_classify_error(error, sql)
        if llm_category in {"syntax", "schema", "semantics"}:
            return llm_category
        return "syntax"

    def _llm_classify_error(self, error: str, sql: str) -> str:
        prompt = (
            "Classify the following SQL execution failure into exactly one category.\n"
            "Categories:\n"
            "- syntax: malformed SQL text\n"
            "- schema: invalid table/column references\n"
            "- semantics: query is syntactically and schema-valid but has logical/value problems\n\n"
            f"SQL:\n{sql}\n\n"
            f"Error:\n{error}\n\n"
            "Answer with one word: syntax, schema, or semantics.\n"
        )
        raw = self._llm_text(prompt, system="You classify SQL errors. Answer with one lowercase word.")
        raw = (raw or "").strip().lower()
        for category in ("syntax", "schema", "semantics"):
            if category in raw:
                return category
        return ""

    def _semantic_issue(self, question: str, sql: str, rows):
        suspicious, reason = self._semantic_heuristic(question, sql, rows)
        if not suspicious:
            return False, ""

        prompt = (
            "Decide whether the executed SQL clearly fails to answer the question.\n"
            f"{self._context_block(question)}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Result summary:\n{self._rows_summary(rows)}\n\n"
            f"Heuristic concern: {reason}\n\n"
            "Answer YES if the query could still be correct. Answer NO only if it clearly does not answer the question.\n"
            "Output only YES or NO.\n"
        )
        raw = self._llm_text(prompt, system="You are a conservative SQL validator. Answer only YES or NO.")
        answer = (raw or "").strip().upper()
        if answer.startswith("NO"):
            return True, reason
        return False, ""

    def _semantic_heuristic(self, question: str, sql: str, rows):
        q = (question or "").lower()
        s = (sql or "").lower()
        reasons = []

        selects_star = re.search(r"\bselect\s+(?:distinct\s+)?\*", s) is not None
        has_aggregate = re.search(
            r"\b(count|sum|avg|min|max|group_concat|json_group_array|total)\s*\(",
            s,
        ) is not None
        has_order_limit = re.search(r"\border\s+by\b.*\blimit\s+\d+", s, flags=re.DOTALL) is not None

        count_question = any(term in q for term in ("how many", "number of", "count"))
        aggregate_question = any(term in q for term in (
            "average",
            "avg",
            "mean",
            "total",
            "sum",
            "maximum",
            "minimum",
            "highest",
            "lowest",
            "largest",
            "smallest",
            "most",
            "least",
        ))
        entity_question = any(term in q for term in ("which", "what", "who", "name", "list", "names", "titles"))

        if count_question and selects_star:
            reasons.append("the question asks for a count but the query selects *")

        if count_question and rows:
            first = rows[0]
            if isinstance(first, dict):
                column_count = len(first)
            elif isinstance(first, (list, tuple)):
                column_count = len(first)
            else:
                column_count = 1

            if len(rows) != 1 or column_count != 1:
                reasons.append("the count-like question did not produce a single scalar value")

        if aggregate_question and not has_aggregate and not has_order_limit:
            reasons.append(
                "the question asks for an aggregate or superlative but the query lacks aggregation or ORDER BY ... LIMIT"
            )

        if selects_star and any(term in q for term in ("name", "title", "id", "average", "total", "maximum", "minimum")):
            reasons.append("the question asks for a specific value but the query selects *")

        if not rows and entity_question:
            reasons.append("the query returned no rows for a question that appears to expect entities")

        return bool(reasons), "; ".join(reasons)

    def _context_block(self, question: str) -> str:
        return f"Schema:\n{self.schema}\n\nQuestion: {question}"

    def _canonical_sql(self, sql: str) -> str:
        return " ".join((sql or "").lower().split())

    def _normalize_sql(self, text: str) -> str:
        sql = self._extract_sql(text)
        sql = (sql or "").strip()
        if not sql:
            return ""
        if ";" in sql:
            sql = sql.split(";", 1)[0].strip()
        return sql

    def _extract_sql(self, text: str) -> str:
        if text is None:
            return ""
        text = str(text).strip()
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
            if extracted and str(extracted).strip():
                return str(extracted).strip()
        except Exception:
            pass

        fence = re.search(r"