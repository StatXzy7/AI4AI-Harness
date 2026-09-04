"""Parse the 'Hint:' line, restate its constraints as enumerated hard requirements before SQL generation, and guard the generated SQL against the machine-checkable subset of those requirements with a bounded feedback-repair loop."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0HintGuard(SQLHarness):
    """Hint-guard harness: the hint is parsed in code, restated as mandatory
    requirements in the prompt, and the emitted SQL is verified against the
    enforceable subset of those requirements (ordering, LIMIT, literals,
    referenced schema identifiers) before it is returned."""

    MAX_GUARD_RETRIES = 2   # feedback repairs driven by requirement violations
    MAX_EXEC_RETRIES = 1    # extra repair attempts if the SQL does not execute

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        # 1. Parse the 'Hint:' line and restate it as hard requirements.
        hint = self._extract_hint(question)
        atoms = self._split_constraints(hint) if hint else []
        requirements = self._build_requirements(atoms)
        req_block = self._format_requirements(requirements)

        # 2. Generate SQL under the restated hard requirements.
        sql = self._gen(
            self._build_initial_prompt(question, req_block),
            system=("You are a precise Text-to-SQL engine. The HARD REQUIREMENTS "
                    "listed in the prompt are mandatory: every one of them must "
                    "be satisfied by the SQL you output."),
        )

        # 3. Guard: verify the SQL against the machine-checkable requirements
        #    and feed any violations back for a bounded number of repairs.
        for _ in range(self.MAX_GUARD_RETRIES):
            violations = self._check_sql(sql, requirements)
            if not violations:
                break
            sql = self._gen(
                self._build_repair_prompt(question, req_block, sql, violations),
                system=("You are fixing a SQL query that violated mandatory "
                        "requirements. Satisfy every listed violation while "
                        "still answering the question."),
            )

        # 4. Execution sanity: a repair is only accepted if it still satisfies
        #    the hint requirements and actually runs.
        result = self.execute(sql)
        if not result.get("ok"):
            for _ in range(self.MAX_EXEC_RETRIES):
                fixed = self._gen(
                    self._build_exec_repair_prompt(
                        question, req_block, sql, result.get("error", "")),
                    system=("Fix the SQL so it executes on the given schema "
                            "without dropping any HARD REQUIREMENT."),
                )
                if self._check_sql(fixed, requirements):
                    continue  # repair must not re-violate the hint requirements
                r2 = self.execute(fixed)
                if r2.get("ok"):
                    sql = fixed
                    break
                result = r2

        return sql

    # ------------------------------------------------------------- LLM call
    def _gen(self, prompt: str, system: str = "") -> str:
        resp = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(resp, (list, tuple)):
            resp = resp[0] if resp else ""
        return bridge.extract_sql(resp)

    # --------------------------------------------------------- hint parsing
    @staticmethod
    def _extract_hint(question: str) -> str:
        """Return the raw text following the 'Hint:' marker, or ''."""
        m = re.search(r"hint\s*:\s*(.+)", question,
                      flags=re.IGNORECASE | re.DOTALL)
        if not m:
            return ""
        hint = m.group(1)
        hint = re.split(r"\n\s*\n", hint)[0]  # stop at a paragraph break
        return hint.strip()

    @staticmethod
    def _split_constraints(hint: str) -> list:
        """Split the hint into atomic constraint phrases."""
        atoms = []
        for part in re.split(r"\s*;\s*", hint):
            for piece in re.split(r"\s*,\s*", part):
                for atom in re.split(r"\s+and\s+", piece, flags=re.IGNORECASE):
                    atom = atom.strip(" .")
                    if atom:
                        atoms.append(atom)
        return atoms

    # -------------------------------------------------- requirement building
    def _build_requirements(self, atoms: list) -> list:
        """Restate each hint atom as a hard requirement, attaching any
        machine-checkable conditions derivable from it."""
        schema_ids = self._schema_identifiers()
        requirements = []
        for atom in atoms:
            checks, seen = [], set()
            low = atom.lower()

            def add(kind, payload, desc):
                key = (kind, str(payload).lower())
                if key not in seen:
                    seen.add(key)
                    checks.append((kind, payload, desc))

            if re.search(r"\b(descending|desc)\b", low):
                add("order", "desc", "SQL must ORDER BY ... DESC")
            elif re.search(r"\b(ascending|asc)\b", low):
                add("order", "asc", "SQL must ORDER BY ... ASC (plain ORDER BY counts)")

            m = re.search(r"\b(?:top|first|limit(?:ed\s+to)?)\s+(\d+)\b", low)
            if m:
                add("limit", int(m.group(1)), f"SQL must contain LIMIT {m.group(1)}")
            elif re.search(r"\blimit\b", low):
                add("limit", None, "SQL must use a LIMIT clause")

            for tup in re.findall(r"'([^']+)'|\"([^\"]+)\"", atom):
                lit = next((g for g in tup if g), "").strip()
                if lit:
                    add("literal", lit, f"SQL must contain the literal '{lit}'")

            unquoted = re.sub(r"'[^']*'|\"[^\"]*\"", " ", atom)
            for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", unquoted):
                if len(tok) >= 2 and tok.lower() in schema_ids:
                    add("identifier", tok, f"SQL must reference '{tok}'")

            requirements.append({"text": atom, "checks": checks})
        return requirements

    @staticmethod
    def _schema_identifiers(schema: str) -> set:
        stop = {"integer", "int", "text", "real", "blob", "numeric", "varchar",
                "char", "date", "datetime", "boolean", "float", "double",
                "primary", "key", "foreign", "references", "table", "create",
                "not", "null", "default", "constraint", "unique", "index",
                "on", "values", "autoincrement"}
        return {tok.lower()
                for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", schema or "")
                if tok.lower() not in stop}

    @staticmethod
    def _format_requirements(requirements: list) -> str:
        lines = []
        for i, req in enumerate(requirements, 1):
            line = f"{i}. MUST: {req['text']}"
            notes = [desc for _, _, desc in req["checks"]]
            if notes:
                line += "  [checked: " + "; ".join(notes) + "]"
            lines.append(line)
        return "\n".join(lines)

    # ---------------------------------------------------------------- guard
    @staticmethod
    def _check_sql(sql: str, requirements: list) -> list:
        """Return a list of human-readable violations of the hard requirements."""
        violations = []
        low = (sql or "").lower()
        for req in requirements:
            for kind, payload, desc in req["checks"]:
                if kind == "order":
                    has_ob = re.search(r"\border\s+by\b", low) is not None
                    has_desc = re.search(r"\bdesc\b", low) is not None
                    ok = (has_ob and has_desc) if payload == "desc" \
                        else (has_ob and not has_desc)
                elif kind == "limit":
                    m = re.search(r"\blimit\s+(\d+)", low)
                    ok = m is not None and (payload is None
                                            or int(m.group(1)) == payload)
                elif kind == "literal":
                    ok = payload.lower() in low
                elif kind == "identifier":
                    ok = re.search(r"\b" + re.escape(payload.lower()) + r"\b",
                                   low) is not None
                else:
                    ok = True
                if not ok:
                    violations.append(
                        f"Requirement '{req['text']}' unsatisfied: {desc}")
        return violations

    # --------------------------------------------------------------- prompts
    def _build_initial_prompt(self, question: str, req_block: str) -> str:
        parts = ["Database schema:", self.schema, "",
                 "Question:", question, ""]
        if req_block:
            parts += ["HARD REQUIREMENTS (parsed from the hint; the SQL MUST "
                      "satisfy every one of them):", req_block, ""]
        parts.append("Write one SQLite query that answers the question and "
                     "satisfies all hard requirements. Output only the SQL.")
        return "\n".join(parts)

    def _build_repair_prompt(self, question: str, req_block: str,
                             sql: str, violations: list) -> str:
        v = "\n".join(f"- {x}" for x in violations)
        return (f"Database schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"HARD REQUIREMENTS:\n{req_block}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"It VIOLATES these hard requirements:\n{v}\n\n"
                "Rewrite the SQL so that every requirement is satisfied. "
                "Output only the corrected SQL.")

    def _build_exec_repair_prompt(self, question: str, req_block: str,
                                  sql: str, error: str) -> str:
        return (f"Database schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"HARD REQUIREMENTS (must remain satisfied):\n{req_block}\n\n"
                f"This SQL failed to execute:\n{sql}\n\n"
                f"Database error:\n{error}\n\n"
                "Fix the SQL so it runs, keeping every hard requirement intact. "
                "Output only the corrected SQL.")