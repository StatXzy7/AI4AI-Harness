"""Error-classifying Text-to-SQL harness that generates SQL, executes it, classifies each failure as syntax, schema, or semantics, and applies a class-specific repair for up to two rounds."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0ErrorClassify(SQLHarness):
    """Generate -> execute -> classify failure (syntax/schema/semantics) -> class-specific repair, max 2 rounds."""

    MAX_REPAIR_ROUNDS = 2

    # ---------------- public entry point ----------------

    def solve(self, question: str) -> str:
        self.error_history = []  # [(attempt, failure_class, diagnosis)]

        sql = self._generate_initial_sql(question)
        best_sql = None  # last SQL that executed without a DB error

        for attempt in range(self.MAX_REPAIR_ROUNDS + 1):
            if not sql:
                sql = self._generate_initial_sql(question)

            result = self.execute(sql)

            if result.get("ok"):
                best_sql = sql
                issue = self._semantic_issue(question, sql, result)
                if not issue:
                    return sql
                failure_class, diagnosis = "semantics", issue
            else:
                error = (result.get("error") or "unknown database error").strip()
                failure_class = self._classify_failure(sql, error)
                diagnosis = error

            self.error_history.append((attempt, failure_class, diagnosis))

            if attempt >= self.MAX_REPAIR_ROUNDS:
                break

            sql = self._repair(question, sql, failure_class, diagnosis)

        # Prefer the last executable SQL over a still-broken final candidate.
        return best_sql if best_sql is not None else sql

    # ---------------- generation ----------------

    def _generate_initial_sql(self, question: str) -> str:
        prompt = (
            "You are given a database schema and a natural-language question.\n"
            "Write a single SQL query that answers the question.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            "Respond with ONLY the SQL query."
        )
        text = self._ask(prompt, system="You are an expert Text-to-SQL engine.")
        return bridge.extract_sql(text) or self._fallback_extract(text)

    # ---------------- failure classification ----------------

    _SCHEMA_HINTS = (
        "no such table", "no such column", "unknown column", "unknown table",
        "does not exist", "ambiguous column", "undefined column", "undefined table",
        "no such function", "unknown identifier", "missing from-clause",
        "has no column named", "invalid column name",
    )
    _SEMANTIC_HINTS = (
        "misuse of aggregate", "must appear in the group by clause",
        "aggregate functions are not allowed", "invalid use of group function",
        "not contained in either an aggregate", "grouping error",
    )
    _SYNTAX_HINTS = ("syntax", "parse error", "at or near", "unrecognized token",
                     "unexpected token", "unterminated", "malformed")

    def _classify_failure(self, sql: str, error: str) -> str:
        e = error.lower()
        if any(h in e for h in self._SCHEMA_HINTS):
            return "schema"
        if any(h in e for h in self._SEMANTIC_HINTS):
            return "semantics"
        if any(h in e for h in self._SYNTAX_HINTS):
            return "syntax"
        return self._llm_classify(sql, error)

    def _llm_classify(self, sql: str, error: str) -> str:
        prompt = (
            "A SQL query failed against the database.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### SQL\n{sql}\n\n"
            f"### Database error\n{error}\n\n"
            "Classify the root cause into EXACTLY one class:\n"
            "- syntax: the SQL is malformed and cannot be parsed\n"
            "- schema: the SQL references tables/columns that do not exist or mis-uses identifiers\n"
            "- semantics: the SQL is valid but implements the wrong logic\n"
            "Reply with ONE word: syntax, schema, or semantics."
        )
        out = self._ask(prompt, system="You are a precise SQL debugger.").lower()
        for cls in ("syntax", "schema", "semantics"):
            if cls in out:
                return cls
        return "syntax"

    # ---------------- class-specific repairs ----------------

    def _repair(self, question: str, sql: str, failure_class: str, diagnosis: str) -> str:
        if failure_class == "schema":
            return self._repair_schema(question, sql, diagnosis)
        if failure_class == "semantics":
            return self._repair_semantics(question, sql, diagnosis)
        return self._repair_syntax(question, sql, diagnosis)

    def _repair_syntax(self, question: str, sql: str, diagnosis: str) -> str:
        prompt = (
            "The following SQL query has a SYNTAX error and cannot be parsed.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### Broken SQL\n{sql}\n\n"
            f"### Parser error\n{diagnosis}\n\n"
            "Fix ONLY the syntax (keywords, parentheses, commas, quoting, aliasing); "
            "preserve the original logic, tables, columns, and intent. "
            "Respond with ONLY the corrected SQL query."
        )
        text = self._ask(prompt, system="You are an expert SQL syntax fixer.")
        return bridge.extract_sql(text) or self._fallback_extract(text) or sql

    def _repair_schema(self, question: str, sql: str, diagnosis: str) -> str:
        bad = self._offending_identifiers(diagnosis)
        bad_line = (
            "Identifiers reported as invalid: " + ", ".join(bad) + "\n\n"
            if bad else ""
        )
        prompt = (
            "The following SQL query failed with a SCHEMA error: it references tables or "
            "columns that do not exist in this database.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### Broken SQL\n{sql}\n\n"
            f"### Database error\n{diagnosis}\n\n"
            f"{bad_line}"
            "Rewrite the query so it uses ONLY table and column names that appear in the "
            "schema above (check exact spelling, singular/plural, casing, and table prefixes); "
            "keep the question's intent. Respond with ONLY the corrected SQL query."
        )
        text = self._ask(prompt, system="You are an expert at mapping SQL to a given schema.")
        return bridge.extract_sql(text) or self._fallback_extract(text) or sql

    def _repair_semantics(self, question: str, sql: str, diagnosis: str) -> str:
        prompt = (
            "The following SQL query is syntactically valid and uses valid identifiers, but it "
            "does NOT correctly answer the question (a SEMANTIC / logic error).\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### Current SQL\n{sql}\n\n"
            f"### Why it is wrong\n{diagnosis}\n\n"
            "Re-derive the query from the question: re-check which tables are needed, the join "
            "keys, filter conditions, aggregation and GROUP BY, ordering, and LIMIT. Use only "
            "tables and columns from the schema. Respond with ONLY the corrected SQL query."
        )
        text = self._ask(prompt,
                         system="You are an expert Text-to-SQL re-planner.",
                         temperature=0.2)
        return bridge.extract_sql(text) or self._fallback_extract(text) or sql

    # ---------------- semantic verification ----------------

    def _semantic_issue(self, question: str, sql: str, result: dict) -> str:
        """Return '' if the SQL semantically answers the question, else a diagnosis string."""
        rows = result.get("rows") or []
        status = (
            f"The query returned {len(rows)} row(s). First rows: {rows[:5]}"
            if rows else
            "The query executed successfully but returned ZERO rows."
        )
        prompt = (
            "Verify whether a SQL query semantically answers the question.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### SQL\n{sql}\n\n"
            f"### Execution result\n{status}\n\n"
            "Does the SQL correctly and completely answer the question (right tables, joins, "
            "filters, aggregation, ordering)?\n"
            "Answer YES or NO on the first line. If NO, explain the logical mistake in one "
            "sentence on the second line."
        )
        out = self._ask(prompt, system="You are a strict SQL semantics verifier.")
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        if not lines:
            return ""
        verdict = lines[0].upper()
        if verdict.startswith("YES"):
            return ""
        if verdict.startswith("NO"):
            reason = lines[1] if len(lines) > 1 else "verifier rejected the query logic"
            return f"{reason} ({status})"
        return ""

    # ---------------- utilities ----------------

    def _ask(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out).strip()

    @staticmethod
    def _offending_identifiers(error: str):
        patterns = [
            r"no such (?:column|table)\s*:\s*([\w.\"']+)",
            r"[Uu]nknown (?:column|table)\s*'([^']+)'",
            r"column \"([^\"]+)\" does not exist",
            r"relation \"([^\"]+)\" does not exist",
            r"ambiguous column(?: name)?\s*[\"']?([\w.]+)",
            r"has no column named\s*([\w.\"']+)",
        ]
        found, seen = [], set()
        for pat in patterns:
            for m in re.findall(pat, error):
                name = m.strip("\"'")
                if name and name not in seen:
                    seen.add(name)
                    found.append(name)
        return found

    @staticmethod
    def _fallback_extract(text: str) -> str:
        m = re.search(r"