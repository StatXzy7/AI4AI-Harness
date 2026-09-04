"""Wraps a frozen weak Text-to-SQL solver by extracting Hint constraints and enforcing them as hard guards in the generated SQL."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Extract hint line if present
        hint_constraints = []
        hint_match = re.search(r'(?im)^\s*Hint\s*:\s*(.+)$', question)
        if hint_match:
            hint_text = hint_match.group(1).strip()
            hint_constraints = self._parse_hint_constraints(hint_text)

        # Build a guarded prompt that restates hints as hard requirements
        guarded_question = self._inject_hint_guards(question, hint_constraints)

        system_prompt = (
            "You are a precise Text-to-SQL generator. "
            "Treat any HINT constraints as HARD REQUIREMENTS that must be satisfied "
            "in the generated SQL (use WHERE, JOIN, GROUP BY, ORDER BY, LIMIT as needed). "
            "Return only a single SQL statement, no commentary."
        )

        raw = self.llm(guarded_question, system=system_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Validate / enforce: re-run with a repair pass if constraints appear violated
        for attempt in range(2):
            violation = self._find_constraint_violation(sql, hint_constraints)
            if violation is None:
                break
            repair_prompt = self._build_repair_prompt(
                guarded_question, sql, violation, hint_constraints
            )
            raw2 = self.llm(repair_prompt, system=system_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(raw2)

        # Final mechanical guard: if we can, append a defensive clause
        sql = self._apply_mechanical_guards(sql, hint_constraints)
        return sql

    # ------------------------------------------------------------------
    # Hint parsing
    # ------------------------------------------------------------------
    def _parse_hint_constraints(self, hint_text: str) -> list:
        """Return a list of structured constraint dicts parsed from the hint line."""
        constraints = []
        ht = hint_text.lower()

        # LIMIT N
        m = re.search(r'top\s+(\d+)|first\s+(\d+)|limit\s+(\d+)|only\s+(\d+)', ht)
        if m:
            n = next(g for g in m.groups() if g)
            constraints.append({'type': 'limit', 'value': int(n), 'raw': m.group(0)})

        # ORDER BY ... ASC/DESC
        m = re.search(
            r'sort(?:ed)?\s+by\s+([\w\."]+)(?:\s+(asc|desc))?',
            hint_text, re.IGNORECASE
        )
        if m:
            constraints.append({
                'type': 'order',
                'column': m.group(1).strip(),
                'direction': (m.group(2) or 'asc').lower(),
                'raw': m.group(0),
            })

        # DISTINCT
        if re.search(r'\bdistinct\b|\bunique\b|\bno duplicates?\b|\bdedup', ht):
            constraints.append({'type': 'distinct', 'raw': 'distinct'})

        # WHERE-like equality / IN
        for eq in re.finditer(
            r'(?:where\s+)?([\w\."]+)\s*(=|is|in)\s*([\w\'"\(\),\- ]+)',
            hint_text, re.IGNORECASE
        ):
            constraints.append({
                'type': 'where_eq',
                'column': eq.group(1).strip(),
                'op': eq.group(2).lower(),
                'value': eq.group(3).strip(),
                'raw': eq.group(0),
            })

        # GROUP BY
        m = re.search(r'group(?:ed)?\s+by\s+([\w\."]+(?:\s*,\s*[\w\."]+)*)', hint_text, re.IGNORECASE)
        if m:
            constraints.append({
                'type': 'group',
                'columns': [c.strip() for c in m.group(1).split(',')],
                'raw': m.group(0),
            })

        # HAVING aggregate
        m = re.search(
            r'(count|sum|avg|min|max)\s*\(\s*([\w\."]+)\s*\)\s*(=|>|<|>=|<=)\s*(\d+)',
            hint_text, re.IGNORECASE
        )
        if m:
            constraints.append({
                'type': 'having',
                'func': m.group(1).upper(),
                'column': m.group(2).strip(),
                'op': m.group(3),
                'value': m.group(4),
                'raw': m.group(0),
            })

        return constraints

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------
    def _inject_hint_guards(self, question: str, constraints: list) -> str:
        if not constraints:
            return question
        guard_lines = ["HARD REQUIREMENTS (must be satisfied in the SQL):"]
        for c in constraints:
            if c['type'] == 'limit':
                guard_lines.append(f"- Use LIMIT {c['value']}.")
            elif c['type'] == 'order':
                guard_lines.append(
                    f"- ORDER BY {c['column']} {c['direction'].upper()}."
                )
            elif c['type'] == 'distinct':
                guard_lines.append("- Use SELECT DISTINCT.")
            elif c['type'] == 'where_eq':
                guard_lines.append(
                    f"- Include WHERE {c['column']} {c['op'].upper()} {c['value']}."
                )
            elif c['type'] == 'group':
                cols = ', '.join(c['columns'])
                guard_lines.append(f"- Include GROUP BY {cols}.")
            elif c['type'] == 'having':
                guard_lines.append(
                    f"- Include HAVING {c['func']}({c['column']}) "
                    f"{c['op']} {c['value']}."
                )
        return question + "\n\n" + "\n".join(guard_lines)

    def _build_repair_prompt(self, original: str, sql: str, violation: str,
                             constraints: list) -> str:
        return (
            original
            + "\n\nYour previous SQL:\n" + sql
            + "\n\nIt violates this HARD REQUIREMENT: " + violation
            + "\n\nRewrite the SQL so it satisfies ALL hard requirements. "
            + "Return only the corrected SQL."
        )

    # ------------------------------------------------------------------
    # Constraint validation against generated SQL
    # ------------------------------------------------------------------
    def _find_constraint_violation(self, sql: str, constraints: list) -> str | None:
        if not sql:
            return "empty SQL"
        sql_l = sql.lower()
        for c in constraints:
            if c['type'] == 'limit':
                if not re.search(rf'\blimit\s+{c["value"]}\b', sql_l):
                    return f"missing LIMIT {c['value']}"
            elif c['type'] == 'order':
                col = re.escape(c['column'].lower())
                pat = rf'\border\s+by\s+{col}\b'
                if not re.search(pat, sql_l):
                    return f"missing ORDER BY {c['column']} {c['direction'].upper()}"
                else:
                    if c['direction'] == 'desc' and 'desc' not in sql_l:
                        return f"missing DESC in ORDER BY {c['column']}"
            elif c['type'] == 'distinct':
                if 'distinct' not in sql_l:
                    return "missing DISTINCT"
            elif c['type'] == 'where_eq':
                col = re.escape(c['column'].lower())
                val = re.escape(c['value'].lower())
                if not re.search(rf'{col}\s*{re.escape(c["op"].lower())}\s*{val}', sql_l):
                    return f"missing WHERE {c['column']} {c['op'].upper()} {c['value']}"
            elif c['type'] == 'group':
                cols = [re.escape(c.lower()) for c in c['columns']]
                if not all(re.search(rf'\bgroup\s+by\b.*\b{col}\b', sql_l) for col in cols):
                    return f"missing GROUP BY {', '.join(c['columns'])}"
            elif c['type'] == 'having':
                fpat = rf'\b{re.escape(c["func"].lower())}\s*\(\s*{re.escape(c["column"].lower())}\s*\)\s*{re.escape(c["op"])}\s*{re.escape(c["value"])}'
                if not re.search(fpat, sql_l):
                    return (f"missing HAVING {c['func']}({c['column']}) "
                             f"{c['op']} {c['value']}")
        return None

    # ------------------------------------------------------------------
    # Mechanical (post-LLM) guards — last-resort enforcement
    # ------------------------------------------------------------------
    def _apply_mechanical_guards(self, sql: str, constraints: list) -> str:
        if not sql or not constraints:
            return sql
        sql_l = sql.lower()

        for c in constraints:
            if c['type'] == 'limit' and not re.search(rf'\blimit\s+\d+\b', sql_l):
                sql = sql.rstrip(';') + f" LIMIT {c['value']}"

            elif c['type'] == 'distinct' and 'distinct' not in sql_l:
                sql = re.sub(r'(?i)\bselect\s+', 'SELECT DISTINCT ', sql, count=1)

            elif c['type'] == 'order':
                if not re.search(rf'\border\s+by\s+{re.escape(c["column"].lower())}\b', sql_l):
                    sql = sql.rstrip(';') + f" ORDER BY {c['column']} {c['direction'].upper()}"
                elif c['direction'] == 'desc' and 'desc' not in sql_l:
                    sql = re.sub(
                        rf'(?i)(\border\s+by\s+{re.escape(c["column"])})',
                        r'\1 DESC',
                        sql,
                    )

            elif c['type'] == 'where_eq':
                col = c['column']
                op = c['op'].upper()
                val = c['value']
                if not re.search(rf'{re.escape(col.lower())}\s*{re.escape(c["op"].lower())}\s*{re.escape(val.lower())}', sql_l):
                    clause = f" WHERE {col} {op} {val}" if 'where' not in sql_l else f" AND {col} {op} {val}"
                    if not sql_l.strip().endswith(';'):
                        sql = sql + clause
                    else:
                        sql = sql[:-1] + clause + ';'

        return sql