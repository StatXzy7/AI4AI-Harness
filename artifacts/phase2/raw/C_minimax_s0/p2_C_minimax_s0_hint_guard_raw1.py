"""Wraps a frozen weak solver by extracting Hint: constraints and enforcing them as hard guards in the generated SQL."""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2CMinimaxS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hint = ""
        m = re.search(r"(?im)^\s*Hint\s*:\s*(.+)$", question)
        if m:
            hint = m.group(1).strip()

        cleaned_question = re.sub(r"(?im)^\s*Hint\s*:\s*.+$", "", question).strip()

        system_prompt = (
            "You are a Text-to-SQL assistant. Write a single SQLite-compatible SQL query "
            "that answers the question using the provided schema.\n\n"
            "Rules:\n"
            "1. Output ONLY the SQL statement, with no commentary, no markdown fences.\n"
            "2. Use only tables/columns from the provided schema.\n"
            "3. If the question contains a 'Hint:' line, treat EVERY constraint in the hint "
            "as a HARD REQUIREMENT that MUST appear (as a WHERE/JOIN/GROUP BY/HAVING/SELECT "
            "clause as appropriate) in the SQL you produce. Do not drop, soften, or reinterpret "
            "any hint constraint.\n"
            "4. Prefer deterministic SQL: no ORDER BY unless needed for LIMIT, no DISTINCT "
            "unless needed, no wildcards beyond what the question requires."
        )

        user_prompt_parts = []
        user_prompt_parts.append("SCHEMA:")
        user_prompt_parts.append(self.schema.strip())
        user_prompt_parts.append("")
        user_prompt_parts.append("QUESTION:")
        user_prompt_parts.append(cleaned_question)
        if hint:
            user_prompt_parts.append("")
            user_prompt_parts.append("HINT CONSTRAINTS (MUST be enforced verbatim in the SQL):")
            user_prompt_parts.append(hint)
            user_prompt_parts.append("")
            user_prompt_parts.append(
                "Re-state these hint constraints as WHERE/JOIN/GROUP BY/HAVING clauses in your SQL."
            )

        user_prompt = "\n".join(user_prompt_parts)

        raw = self.llm(user_prompt, system=system_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        if sql and hint:
            sql = self._enforce_hint(sql, hint)

        if sql:
            res = self.execute(sql)
            if res.get("ok"):
                return sql

        if not sql and hint:
            fallback_prompt = (
                user_prompt
                + "\n\nYour previous output could not be parsed as SQL. "
                + "Return ONLY a single SQL statement that includes EVERY hint constraint "
                + "as an explicit clause. No prose."
            )
            raw2 = self.llm(fallback_prompt, system=system_prompt, temperature=0.0, n=1)
            sql2 = bridge.extract_sql(raw2)
            if sql2:
                sql2 = self._enforce_hint(sql2, hint)
                res2 = self.execute(sql2)
                if res2.get("ok"):
                    return sql2
                sql = sql2

        return sql if sql else ""

    def _enforce_hint(self, sql: str, hint: str) -> str:
        """Append hard WHERE clauses derived from simple hint patterns as a final guard."""
        guards = []
        h = hint.lower()

        year_m = re.search(r"\b(?:in|for|of)\s+(19\d{2}|20\d{2})\b", hint)
        if year_m:
            guards.append(f"CAST(strftime('%Y', ...) AS INTEGER) = {year_m.group(1)}")

        m = re.search(r"(?i)\bmax(?:imum)?\s+of\s+([A-Za-z_][A-Za-z0-9_]*)", hint)
        if m:
            col = m.group(1)
            sql = re.sub(
                r"(?is)^(.*?FROM\s+.*?)(ORDER BY.*|LIMIT.*|;|\Z)",
                lambda mm: mm.group(1) + f" GROUP BY {col} HAVING MAX({col}) = (SELECT MAX({col}) FROM ({mm.group(1).split('FROM',1)[1].rsplit('GROUP BY',1)[0].rsplit('ORDER BY',1)[0]}) ) " + (mm.group(2) if not mm.group(2).startswith(';') else ';'),
                sql,
                count=1,
            )

        between_m = re.search(r"(?i)\bbetween\s+([0-9]+)\s+and\s+([0-9]+)\b", hint)
        if between_m:
            a, b = between_m.group(1), between_m.group(2)
            guards.append(f"BETWEEN {a} AND {b}")

        if guards:
            guard_clause = " AND ".join(guards)
            if re.search(r"(?i)\bWHERE\b", sql):
                sql = re.sub(r"(?i)\bWHERE\b", "WHERE (1=0) AND WHERE_TRUE_PLACEHOLDER ", sql, count=1)
                sql = sql.replace("WHERE_TRUE_PLACEHOLDER", "1=1 AND " + guard_clause, 1)
                if "WHERE (1=0) AND 1=1 AND" in sql:
                    sql = sql.replace("WHERE (1=0) AND 1=1 AND", "WHERE", 1)
            else:
                insert_at = len(sql)
                for pat in (r"(?i)\bGROUP BY\b", r"(?i)\bORDER BY\b", r"(?i)\bLIMIT\b", r";", r"\Z"):
                    mm = re.search(pat, sql)
                    if mm:
                        insert_at = min(insert_at, mm.start())
                sql = sql[:insert_at].rstrip() + "\nWHERE " + guard_clause + "\n" + sql[insert_at:].lstrip()

        return sql