"""Parses the 'Hint:' line from the question, restates it as hard requirements, and enforces them with a generate-check-repair guard loop before returning the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1HintGuard(SQLHarness):
    """Hint-guarded Text-to-SQL harness.

    Control flow (the strategy lives here, not only in the prompt):
      1. Parse the 'Hint:' (or 'Evidence:') line out of the question.
      2. Restate the hint as a numbered list of HARD REQUIREMENTS via the LLM.
      3. Generate SQL with those requirements injected as mandatory constraints.
      4. Guard: deterministically check hint-implied literals / LIMIT / ordering /
         GROUP BY / DISTINCT, then run an LLM pass over every requirement, and
         finally a trial execution; on any failure, regenerate with targeted
         feedback and re-check, bounded by MAX_ATTEMPTS repairs.
    """

    MAX_ATTEMPTS = 3        # number of repair regenerations after the first draft
    MAX_REQUIREMENTS = 8    # cap on restated hard requirements

    _HINT_LINE_RE = re.compile(
        r"(?im)^\s*(?:hint|evidence)\s*[:：]\s*(?P<body>.+?)\s*$"
    )
    _HINT_INLINE_RE = re.compile(
        r"(?is)(?:hint|evidence)\s*[:：]\s*(?P<body>.+?)\s*$"
    )
    _REQ_ITEM_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s*(.+)$")

    # ------------------------------------------------------------------ entry
    def solve(self, question: str) -> str:
        hint = self._extract_hint(question)
        requirements = self._restate_requirements(question, hint) if hint else []
        hard_block = self._format_requirements(requirements)

        feedback = ""
        sql = self._generate_sql(question, hard_block, feedback)
        for _ in range(self.MAX_ATTEMPTS):
            # Cheap deterministic guard first; only escalate if it passes.
            violations = self._deterministic_violations(sql, hint, requirements)
            if not violations:
                violations = self._llm_violations(sql, requirements)
            exec_error = None
            if not violations:
                exec_error = self._execution_error(sql)
            if not violations and exec_error is None:
                return sql
            feedback = self._build_feedback(violations, exec_error)
            sql = self._generate_sql(question, hard_block, feedback)
        return sql  # best effort after the repair budget is exhausted

    # ------------------------------------------------------- hint extraction
    def _extract_hint(self, question: str) -> str:
        m = self._HINT_LINE_RE.search(question) or self._HINT_INLINE_RE.search(question)
        if not m:
            return ""
        return m.group("body").strip()

    # --------------------------------------------- requirement restatement
    def _restate_requirements(self, question: str, hint: str) -> list:
        system = "You rewrite question hints as strict, checkable SQL requirements."
        prompt = (
            "Schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n"
            "Hint: " + hint + "\n\n"
            "Restate the hint as hard requirements that any correct SQL query MUST "
            "satisfy. Rules: one requirement per line, each line starts with '- '; "
            "preserve exact literal values, column names, comparison directions and "
            "row limits verbatim; output at most " + str(self.MAX_REQUIREMENTS) +
            " requirements; output nothing else."
        )
        raw = self._call_llm(prompt, system=system)
        reqs = []
        for line in raw.splitlines():
            m = self._REQ_ITEM_RE.match(line.strip())
            if m:
                reqs.append(m.group(1).strip())
        if not reqs:
            reqs = [raw.strip()] if raw.strip() else [hint]
        return reqs[: self.MAX_REQUIREMENTS]

    def _format_requirements(self, requirements: list) -> str:
        if not requirements:
            return ""
        lines = [
            "HARD REQUIREMENTS (restated from the hint — every one MUST be "
            "satisfied by the SQL):"
        ]
        for i, req in enumerate(requirements, 1):
            lines.append(f"{i}. {req}")
        return "\n".join(lines)

    # --------------------------------------------------------------- generation
    def _generate_sql(self, question: str, hard_block: str, feedback: str) -> str:
        system = (
            "You are an expert Text-to-SQL generator. "
            "Output exactly one SQL query and nothing else."
        )
        parts = ["Schema:", self.schema, "", "Question:", question]
        if hard_block:
            parts += ["", hard_block]
        if feedback:
            parts += [
                "",
                "Your previous SQL was rejected for the following reasons — fix ALL of them:",
                feedback,
            ]
        parts += ["", "Write the SQL query now. It must satisfy every hard requirement above."]
        raw = self._call_llm("\n".join(parts), system=system)
        try:
            sql = bridge.extract_sql(raw)
        except Exception:
            sql = ""
        return sql.strip() if sql and sql.strip() else raw.strip()

    # ------------------------------------------------------ deterministic guard
    def _deterministic_violations(self, sql: str, hint: str, requirements: list) -> list:
        violations = []
        low = sql.lower()
        corpus = hint + "\n" + "\n".join(requirements)

        # 1. Exact literal values quoted in the hint must appear in the SQL.
        literals = re.findall(r"'([^']+)'", corpus) + re.findall(r'"([^"]+)"', corpus)
        for val in literals:
            val = val.strip()
            if val and val.lower() not in low:
                violations.append(
                    f"Missing required literal value '{val}' stated in the hint."
                )

        # 2. Explicit row limits ("top N", "at most N", "limit N", "first N").
        m = re.search(r"(?i)\b(?:top|limit|at\s+most|first)\s+(\d+)\b", corpus)
        if m and not re.search(r"(?i)\blimit\s+" + re.escape(m.group(1)) + r"\b", sql):
            violations.append(f"Must include LIMIT {m.group(1)} as implied by the hint.")

        # 3. Ordering direction: descending must be explicit; ascending needs ORDER BY.
        wants_sort = re.search(r"(?i)\b(order|sort|top|rank)\b", corpus)
        if wants_sort and re.search(
            r"(?i)\b(descending|desc|highest|largest|most|greatest)\b", corpus
        ):
            if "desc" not in low:
                violations.append(
                    "Must order descending (ORDER BY ... DESC) as implied by the hint."
                )
        if wants_sort and re.search(
            r"(?i)\b(ascending|asc|lowest|smallest|least|fewest)\b", corpus
        ):
            if "order by" not in low:
                violations.append(
                    "Must include an ORDER BY (ascending) as implied by the hint."
                )

        # 4. Explicitly mentioned clauses must be present.
        if re.search(r"(?i)\bgroup\s*by\b", corpus) and "group by" not in low:
            violations.append("Must use GROUP BY as stated in the requirements.")
        if re.search(r"(?i)\b(distinct|unique)\b", corpus) and "distinct" not in low:
            violations.append("Must use DISTINCT as stated in the requirements.")

        # Deduplicate while preserving order.
        seen, out = set(), []
        for v in violations:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    # ------------------------------------------------------------- LLM guard
    def _llm_violations(self, sql: str, requirements: list) -> list:
        if not requirements:
            return []
        req_text = "\n".join(f"{i}. {r}" for i, r in enumerate(requirements, 1))
        system = (
            "You are a strict SQL requirements checker. "
            "Answer only with violated requirement numbers or 'NONE'."
        )
        prompt = (
            "Schema:\n" + self.schema + "\n\n"
            "SQL:\n" + sql + "\n\n"
            "Hard requirements:\n" + req_text + "\n\n"
            "Which requirements does the SQL VIOLATE? Reply with a comma-separated "
            "list of numbers, or 'NONE' if every requirement is satisfied."
        )
        raw = self._call_llm(prompt, system=system)
        if "none" in raw.lower():
            return []
        out = []
        for tok in re.findall(r"\d+", raw):
            idx = int(tok)
            if 1 <= idx <= len(requirements):
                out.append(f"Violates hard requirement {idx}: {requirements[idx - 1]}")
        return out

    # -------------------------------------------------------- execution guard
    def _execution_error(self, sql: str):
        try:
            res = self.execute(sql)
        except Exception as exc:  # defensive: treat harness errors as failures
            return str(exc)
        if isinstance(res, dict) and not res.get("ok"):
            return res.get("error") or "unknown execution error"
        return None

    # ---------------------------------------------------------------- helpers
    def _build_feedback(self, violations: list, exec_error) -> str:
        parts = []
        if violations:
            parts.append(
                "Requirement violations:\n" + "\n".join("- " + v for v in violations)
            )
        if exec_error:
            parts.append("Execution error: " + str(exec_error))
        return "\n".join(parts)

    def _call_llm(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out)