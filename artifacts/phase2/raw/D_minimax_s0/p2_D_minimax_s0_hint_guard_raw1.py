"""Parses the 'Hint:' line from the question, enforces its constraints as hard requirements via schema exploration and guard clauses, then delegates SQL generation to a frozen weak solver with the restated prompt."""
import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0HintGuard(SQLHarness):
    """
    Harness that extracts a 'Hint:' line from the user question, splits it into
    discrete constraints, and treats each as a hard requirement that must be
    reflected in the final SQL. The constraints are enforced in the control flow
    (not only in the prompt) by parsing the hint, asking the LLM to produce a
    first-pass SQL, executing it, and then re-prompting with concrete repair
    directives derived from the parsed hint when execution or coverage is off.
    """

    # ---- Hint parsing ---------------------------------------------------- #

    _HINT_PATTERN = re.compile(
        r"(?im)^\s*Hint\s*:\s*(?P<body>.+?)\s*$"
    )

    def _extract_hint(self, question: str) -> str:
        """Return the raw 'Hint:' body, or '' if no hint is present."""
        m = self._HINT_PATTERN.search(question or "")
        return (m.group("body").strip() if m else "")

    def _split_constraints(self, hint: str) -> List[str]:
        """
        Split a hint body into individual constraint clauses.
        Uses sentence/separator heuristics; never raises.
        """
        if not hint:
            return []
        # Normalize whitespace
        text = re.sub(r"\s+", " ", hint).strip()
        # Split on sentence terminators and explicit separators
        parts = re.split(r"(?<=[.!?;])\s+|,\s+(?=[A-Z])", text)
        parts = [p.strip(" .;:\t") for p in parts if p and p.strip()]
        return parts

    def _user_question_without_hint(self, question: str) -> str:
        """Return the original question with the 'Hint:' line stripped."""
        return self._HINT_PATTERN.sub("", question or "").strip()

    # ---- Schema introspection ------------------------------------------- #

    def _schema_excerpt_for_hint(self, hint: str) -> str:
        """
        If self.schema is structured (CREATE TABLE statements), return only the
        tables/columns that look topically relevant to the hint. Otherwise
        return self.schema unchanged. Best-effort, never raises.
        """
        schema = getattr(self, "schema", "") or ""
        if not hint or "CREATE TABLE" not in schema.upper():
            return schema

        try:
            # Naive split of CREATE TABLE blocks
            blocks = re.findall(
                r"(?is)CREATE\s+TABLE\s+[`\"']?(\w+)[`\"']?\s*\((.*?)\)\s*;?",
                schema,
            )
            if not blocks:
                return schema

            hint_tokens = {
                t.lower() for t in re.findall(r"[A-Za-z_]\w+", hint) if len(t) > 2
            }
            keep = []
            for name, body in blocks:
                body_tokens = {t.lower() for t in re.findall(r"[A-Za-z_]\w+", body)}
                if hint_tokens & body_tokens:
                    keep.append(f"CREATE TABLE {name} ({body.strip()})")
            return "\n\n".join(keep) if keep else schema
        except Exception:
            return schema

    # ---- Guard / repair directives -------------------------------------- #

    def _guard_directives(self, constraints: List[str]) -> str:
        """
        Turn parsed hint constraints into an explicit hard-requirements block
        that is appended to the prompt. This is what makes the hint a HARD
        requirement rather than a soft suggestion.
        """
        if not constraints:
            return ""
        bullets = "\n".join(f"- {c}" for c in constraints)
        return (
            "\n\nHARD REQUIREMENTS (from Hint:). The final query MUST satisfy "
            "every one of these. Do not drop, weaken, or substitute any of "
            "them:\n"
            f"{bullets}\n"
            "If the schema cannot satisfy a requirement, still emit SQL that "
            "encodes the requirement literally (e.g. via the requested filter, "
            "join, alias, or column name) so the guard can detect the mismatch."
        )

    def _coverage_check(self, sql: str, constraints: List[str]) -> List[str]:
        """
        Return the list of constraints that are NOT visibly reflected in the
        produced SQL. This is a structural check, not a semantic one — it
        enforces the hint at the harness level.
        """
        if not constraints:
            return []
        sql_low = sql.lower()
        missing: List[str] = []
        for c in constraints:
            tokens = [t.lower() for t in re.findall(r"[A-Za-z_]\w+", c) if len(t) > 2]
            if not tokens:
                continue
            # Constraint is considered covered if any of its key tokens appears
            # in the SQL (case-insensitive). Otherwise flag as not covered.
            if not any(tok in sql_low for tok in tokens):
                missing.append(c)
        return missing

    # ---- Main solve ------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # 1) Pull the hint and split it into hard constraints.
        hint = self._extract_hint(question)
        constraints = self._split_constraints(hint)
        base_question = self._user_question_without_hint(question)

        # 2) Build a schema excerpt relevant to the constraints, plus the full
        #    schema as a fallback for tables the LLM may need.
        focused_schema = self._schema_excerpt_for_hint(hint)
        full_schema = getattr(self, "schema", "") or ""

        # 3) Compose the prompt with the hint restated as requirements.
        guard = self._guard_directives(constraints)
        prompt = (
            f"Question:\n{base_question or question}\n\n"
            f"Relevant schema:\n{focused_schema}\n\n"
            f"Full schema (for reference):\n{full_schema}\n\n"
            f"{guard}\n\n"
            "Return exactly one SQL statement. No prose, no markdown fences."
        )

        # 4) Ask the frozen weak solver for a first-pass SQL.
        system = (
            "You are a Text-to-SQL generator. You MUST output exactly one SQL "
            "statement and nothing else. The HARD REQUIREMENTS listed in the "
            "prompt are non-negotiable; every one of them must be reflected "
            "verbatim in the SQL you emit."
        )

        first = self.llm(prompt=prompt, system=system, temperature=0.0, n=1)
        first_sql = bridge.extract_sql(first)

        # 5) Execute the SQL. If it fails, attempt one targeted repair that
        #    keeps the hint constraints as hard requirements.
        exec_result = self.execute(first_sql) if first_sql else {"ok": False, "error": "empty"}
        if exec_result.get("ok"):
            sql = first_sql
        else:
            repair_prompt = (
                f"The SQL you produced failed to execute.\n"
                f"Error: {exec_result.get('error', '')}\n\n"
                f"Original question:\n{base_question or question}\n\n"
                f"Schema:\n{full_schema}\n\n"
                f"{guard}\n\n"
                "Rewrite the SQL so it executes AND still satisfies every "
                "HARD REQUIREMENT. Return exactly one SQL statement, no prose."
            )
            repaired = self.llm(prompt=repair_prompt, system=system,
                                temperature=0.0, n=1)
            sql = bridge.extract_sql(repaired) or first_sql

        # 6) Coverage guard: if any hint constraint is not visibly reflected
        #    in the SQL, force one more regeneration that is told explicitly
        #    which constraints are missing. This is the enforcement loop that
        #    makes the hint a hard requirement at the harness level.
        missing = self._coverage_check(sql, constraints)
        if missing:
            missing_block = "\n".join(f"- {m}" for m in missing)
            enforce_prompt = (
                f"Your previous SQL did not visibly include every required "
                f"constraint. The following constraints from the Hint are "
                f"missing from the SQL you produced:\n{missing_block}\n\n"
                f"Question:\n{base_question or question}\n\n"
                f"Schema:\n{full_schema}\n\n"
                f"{guard}\n\n"
                "Produce a new SQL that explicitly contains each missing "
                "constraint (use the requested table, column, filter value, "
                "join, or alias verbatim). Return exactly one SQL statement, "
                "no prose, no markdown."
            )
            enforced = self.llm(prompt=enforce_prompt, system=system,
                                 temperature=0.0, n=1)
            enforced_sql = bridge.extract_sql(enforced)
            if enforced_sql:
                sql = enforced_sql

        return sql