"""Harness that parses the 'Hint:' line from the question, restates its constraints as hard requirements before SQL generation, and mechanically guards/repairs the candidate SQL against those constraints before returning it."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2HintGuard(SQLHarness):
    """Hint-guarding Text-to-SQL harness.

    Control flow (the strategy lives here, not only in the prompt):
      1. Parse the ``Hint:`` line out of the natural-language question.
      2. Compile it into explicit constraints: quoted literals, referenced
         schema columns, numeric comparisons, and structural directives
         (ORDER BY / LIMIT / GROUP BY / DISTINCT).
      3. Restate those constraints as HARD REQUIREMENTS in the prompt,
         placed *before* the question, so the frozen solver writes SQL
         under them.
      4. Guard: mechanically check the extracted SQL against the parsed
         constraints and against live execution; on any violation, feed the
         exact violation list back and force a bounded rewrite.
      5. Return the surviving candidate SQL.
    """

    MAX_ATTEMPTS = 4  # 1 initial generation + up to 3 guarded repairs

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        hint = self._parse_hint(question)
        constraints = self._extract_constraints(hint)
        requirements = self._format_requirements(hint, constraints)

        system = (
            "You are an expert SQLite Text-to-SQL engine. The prompt contains "
            "HARD REQUIREMENTS restated from the question's Hint. You must "
            "satisfy every one of them exactly; they override any conflicting "
            "intuition. Output only the SQL query."
        )

        candidate = ""
        feedback = ""
        for _attempt in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(question, requirements, feedback)
            raw = self._call_llm(prompt, system)
            extracted = bridge.extract_sql(raw)
            candidate = (extracted or raw or "").strip() or candidate

            # Guard 1: mechanical check against the parsed Hint constraints.
            violations = self._check_constraints(candidate, constraints)

            # Guard 2: live execution check (only if the Hint guard passes,
            # so we never execute SQL that already violates the Hint).
            exec_error = ""
            if not violations:
                try:
                    result = self.execute(candidate)
                    if not result.get("ok"):
                        exec_error = result.get("error", "unknown error")
                except Exception as exc:  # defensive: treat harness errors as DB errors
                    exec_error = str(exc)

            if not violations and not exec_error:
                break

            problems = []
            if violations:
                problems.append(
                    "Hard-requirement violations:\n"
                    + "\n".join(f"- {v}" for v in violations)
                )
            if exec_error:
                problems.append(f"Execution error: {exec_error}")
            feedback = (
                "The previous SQL was rejected.\n"
                + "\n\n".join(problems)
                + f"\nPrevious SQL:\n{candidate}\n"
                "Rewrite the SQL fixing ALL of the above while still "
                "satisfying every HARD REQUIREMENT."
            )

        return candidate.strip() or "SELECT 1"

    # -------------------------------------------------------------- parsing
    def _parse_hint(self, question: str) -> str:
        """Extract the text of the 'Hint:' line (possibly multi-line)."""
        if not question:
            return ""
        # Preferred: a dedicated Hint: field, spanning until the next field
        # label (Question:/Evidence:/Answer:), a blank line, or end of text.
        m = re.search(
            r"^\s*hint\s*:\s*(.+?)(?=^\s*(?:question|evidence|answer)\s*:|\n\s*\n|\Z)",
            question,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if m:
            return " ".join(m.group(1).split())
        # Fallback: inline "Hint: ..." up to the end of that line.
        m = re.search(r"\bhint\s*:\s*([^\n]+)", question, re.IGNORECASE)
        return " ".join(m.group(1).split()) if m else ""

    def _extract_constraints(self, hint: str) -> dict:
        """Compile the raw hint text into mechanically checkable constraints."""
        constraints = {
            "literals": [],   # exact quoted filter values that must appear
            "columns": [],    # schema columns the Hint explicitly names
            "numbers": [],    # (operator, value) comparisons the Hint states
            "order": False,   # Hint implies a ranking -> ORDER BY
            "limit": False,   # Hint implies top-N / single answer -> LIMIT
            "group": False,   # Hint implies per-group aggregation -> GROUP BY
            "distinct": False # Hint asks for unique values -> DISTINCT
        }
        if not hint:
            return constraints

        # 1) Quoted literals are almost always mandatory filter values.
        for m in re.finditer(r"""['"]([^'"]+)['"]""", hint):
            lit = m.group(1).strip()
            if lit and lit not in constraints["literals"]:
                constraints["literals"].append(lit)

        # 2) Schema columns explicitly named in the Hint must be used.
        for col in self._schema_columns():
            if re.search(rf"(?<![\w]){re.escape(col)}(?![\w])", hint, re.IGNORECASE):
                constraints["columns"].append(col)

        # 3) Numeric comparisons stated symbolically or in words.
        for m in re.finditer(r"(>=|<=|<>|!=|=|>|<)\s*(-?\d+(?:\.\d+)?)", hint):
            pair = (m.group(1), m.group(2))
            if pair not in constraints["numbers"]:
                constraints["numbers"].append(pair)
        for word, op in (
            ("at least", ">="), ("no less than", ">="),
            ("more than", ">"), ("greater than", ">"), ("over", ">"),
            ("at most", "<="), ("no more than", "<="),
            ("less than", "<"), ("fewer than", "<"), ("under", "<"),
            ("equal to", "="), ("exactly", "="),
        ):
            for m in re.finditer(rf"{word}\s+(-?\d+(?:\.\d+)?)", hint, re.IGNORECASE):
                pair = (op, m.group(1))
                if pair not in constraints["numbers"]:
                    constraints["numbers"].append(pair)

        # 4) Structural directives implied by the Hint's wording.
        low = hint.lower()
        constraints["order"] = any(
            k in low for k in ("order by", "sort", "highest", "lowest", "most", "least", "top", "largest", "smallest")
        )
        constraints["limit"] = bool(re.search(r"\btop\s+\d+\b", low)) or any(
            k in low for k in ("first", "only one", "single", "limit")
        )
        constraints["group"] = any(k in low for k in ("each", "per ", "group by", "for every"))
        constraints["distinct"] = "distinct" in low or "unique" in low
        return constraints

    def _schema_columns(self) -> list:
        """Best-effort extraction of column names from self.schema."""
        cols = set()
        schema = getattr(self, "schema", "") or ""
        # CREATE TABLE style bodies.
        for m in re.finditer(r"CREATE\s+TABLE\s+\S+\s*\((.*?)\)", schema, re.IGNORECASE | re.DOTALL):
            for chunk in m.group(1).split(","):
                tokens = chunk.strip().split()
                if not tokens:
                    continue
                name = tokens[0].strip('`"[]')
                if name and name.upper() not in (
                    "PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "KEY", "CHECK",
                ):
                    cols.add(name)
        # table.column dotted references.
        for m in re.finditer(r"\b\w+\.(\w+)\b", schema):
            cols.add(m.group(1))
        # "-- column_name" comment style.
        for m in re.finditer(r"^\s*(\w+)\s+[A-Za-z]+\s*,?\s*(?:--|$)", schema, re.MULTILINE):
            cols.add(m.group(1))
        return sorted(cols)

    # -------------------------------------------------------- restatement
    def _format_requirements(self, hint: str, constraints: dict) -> str:
        """Restate the parsed Hint as an explicit HARD REQUIREMENTS block."""
        if not hint:
            return ""
        lines = [
            f'The question includes a Hint: "{hint}".',
            "The Hint's constraints are HARD REQUIREMENTS; every one is mandatory:",
        ]
        idx = 1
        for lit in constraints["literals"]:
            lines.append(f"{idx}. Filter using the exact value '{lit}'.")
            idx += 1
        for col in constraints["columns"]:
            lines.append(f"{idx}. Use the column '{col}' mentioned in the Hint.")
            idx += 1
        for op, num in constraints["numbers"]:
            lines.append(f"{idx}. Include the comparison '{op} {num}'.")
            idx += 1
        if constraints["order"]:
            lines.append(f"{idx}. Include ORDER BY to satisfy the ranking implied by the Hint.")
            idx += 1
        if constraints["limit"]:
            lines.append(f"{idx}. Include LIMIT to satisfy the top-N/single-answer restriction implied by the Hint.")
            idx += 1
        if constraints["group"]:
            lines.append(f"{idx}. Include GROUP BY for the per-group aggregation implied by the Hint.")
            idx += 1
        if constraints["distinct"]:
            lines.append(f"{idx}. Use DISTINCT as required by the Hint.")
            idx += 1
        if idx == 1:
            lines.append("1. Follow the Hint literally; treat every condition in it as mandatory.")
        return "\n".join(lines)

    def _build_prompt(self, question: str, requirements: str, feedback: str) -> str:
        """Schema, then HARD REQUIREMENTS, then the question, then feedback."""
        parts = ["Database schema:", getattr(self, "schema", "") or "", ""]
        if requirements:
            parts += [
                "HARD REQUIREMENTS (restated from the Hint — satisfy ALL of them):",
                requirements,
                "",
            ]
        parts += ["Question:", question, ""]
        if feedback:
            parts += ["Correction required:", feedback, ""]
        parts.append(
            "Write a single SQLite query that answers the question while "
            "satisfying every HARD REQUIREMENT above."
        )
        return "\n".join(parts)

    # ---------------------------------------------------------------- guard
    def _check_constraints(self, sql: str, constraints: dict) -> list:
        """Return a list of human-readable Hint-constraint violations in sql."""
        violations = []
        if not sql.strip():
            return ["SQL is empty."]
        sql_low = sql.lower()

        for lit in constraints.get("literals", []):
            if lit.lower() not in sql_low:
                violations.append(
                    f"Filter value '{lit}' from the Hint must appear in the SQL."
                )
        for col in constraints.get("columns", []):
            if not re.search(rf"(?<![\w]){re.escape(col)}(?![\w])", sql, re.IGNORECASE):
                violations.append(
                    f"Column '{col}' named in the Hint must be used in the SQL."
                )
        for op, num in constraints.get("numbers", []):
            exact = rf"{re.escape(op)}\s*{re.escape(num)}(?![\d.])"
            present = rf"(?<![\d.]){re.escape(num)}(?![\d.])"
            if not (re.search(exact, sql) or re.search(present, sql)):
                violations.append(
                    f"Comparison '{op} {num}' from the Hint must appear in the SQL."
                )
        agg_extremum = re.search(r"\b(max|min)\s*\(", sql_low)
        if constraints.get("order") and "order by" not in sql_low and not agg_extremum:
            violations.append(
                "The Hint implies a ranking, so the SQL must contain ORDER BY "
                "(or an equivalent MAX/MIN aggregate)."
            )
        if constraints.get("limit") and "limit" not in sql_low and not agg_extremum:
            violations.append(
                "The Hint implies a top-N/single-answer restriction, so the SQL "
                "must contain LIMIT (or an equivalent MAX/MIN aggregate)."
            )
        if constraints.get("group") and "group by" not in sql_low:
            violations.append(
                "The Hint implies per-group aggregation, so the SQL must contain GROUP BY."
            )
        if constraints.get("distinct") and "distinct" not in sql_low:
            violations.append(
                "The Hint asks for distinct/unique values, so the SQL must use DISTINCT."
            )
        return violations

    # ---------------------------------------------------------------- utils
    def _call_llm(self, prompt: str, system: str) -> str:
        """Invoke the frozen solver and normalise its output to a string."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out or "")