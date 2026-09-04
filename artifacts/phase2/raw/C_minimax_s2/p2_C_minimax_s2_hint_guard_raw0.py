"""Wraps a frozen Text-to-SQL solver by parsing explicit Hint lines and enforcing their constraints as hard gates around SQL generation."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2HintGuard(SQLHarness):
    # Strategy token: parse-hint-enforce
    STRATEGY_TOKEN = "parse-hint-enforce"

    def _parse_hint(self, question: str):
        """Extract a 'Hint:' clause from the question, if present.

        Returns a tuple (hint_text, hint_constraints) where hint_constraints is a
        list of structured requirement strings derived from the hint. If no hint
        line is found, returns (None, []).
        """
        hint_text = None
        constraints = []

        # Scan the question line-by-line for a Hint: prefix (case-insensitive).
        for raw_line in question.splitlines():
            stripped = raw_line.strip()
            lower = stripped.lower()
            if lower.startswith("hint:") or lower.startswith("hint :"):
                hint_text = stripped.split(":", 1)[1].strip()
                break

        if not hint_text:
            return None, []

        # Break the hint into individual constraint clauses.
        # Constraints are separated by ';', ' and ', or commas depending on phrasing.
        raw_clauses = []
        # Primary separator is ';'. We keep quote awareness simple: no nested
        # SQL string literals are expected inside Hint lines in this benchmark.
        for piece in hint_text.split(";"):
            piece = piece.strip()
            if not piece:
                continue
            # Within each piece, ' and ' often separates conjunctional requirements.
            if " and " in piece.lower():
                # split on ' and ' but preserve original casing of pieces
                buf = ""
                parts = []
                tokens = piece.split(" ")
                i = 0
                current = []
                while i < len(tokens):
                    if tokens[i].lower() == "and" and current:
                        parts.append(" ".join(current).strip())
                        current = []
                        i += 1
                        # skip following 'then' / ',' tokens if any
                        while i < len(tokens) and tokens[i] in {",", "then", "also"}:
                            i += 1
                        continue
                    current.append(tokens[i])
                    i += 1
                if current:
                    parts.append(" ".join(current).strip())
                raw_clauses.extend([p for p in parts if p])
            else:
                raw_clauses.append(piece)

        # Normalize each clause into a clean constraint statement.
        for clause in raw_clauses:
            c = clause.strip().rstrip(",").strip()
            if not c:
                continue
            constraints.append(c)

        return hint_text, constraints

    def _build_constraint_system_prompt(self, constraints):
        """Translate parsed hint constraints into a hard-requirement system prompt.

        Each constraint becomes a numbered HARD requirement that the produced
        SQL MUST satisfy. The prompt also includes a self-check instruction so
        the weak solver is forced to verify each constraint explicitly.
        """
        if not constraints:
            return ""

        lines = []
        lines.append("You are generating a single SQL query for the user's question.")
        lines.append("")
        lines.append("The following are HARD requirements derived from the user's Hint.")
        lines.append("Every one of them MUST be satisfied by the SQL you produce.")
        lines.append("If a requirement cannot be satisfied, you must still produce")
        lines.append("the SQL that comes closest while flagging the conflict in a comment.")
        lines.append("")
        for idx, c in enumerate(constraints, start=1):
            lines.append(f"HARD REQ {idx}: {c}.")
        lines.append("")
        lines.append("Before finalizing the SQL, mentally verify each HARD REQ against")
        lines.append("your query. If any requirement is missing or contradicted, rewrite")
        lines.append("the SQL until all HARD REQs are satisfied.")
        lines.append("")
        lines.append("Return ONLY the SQL query, optionally preceded by a brief")
        lines.append("# CHECK: <one line summary> comment.")
        return "\n".join(lines)

    def _verify_sql_against_constraints(self, sql: str, constraints):
        """Lightweight syntactic verification of obvious constraint violations.

        This is a control-flow gate, not a prompt-only claim. We check a few
        common, easy-to-detect cases (SELECT *, ORDER BY presence, LIMIT presence,
        DISTINCT presence, JOIN presence, GROUP BY presence, WHERE presence). If
        a violation is detected we record it; the caller will trigger a repair
        round-trip with the weak solver rather than accepting the SQL silently.
        """
        if not constraints:
            return [], []

        sql_l = sql.lower()
        satisfied = []
        violated = []

        for c in constraints:
            cl = c.lower()
            recorded = False

            # SELECT * prohibition
            if "no select *" in cl or "avoid select *" in cl or "don't select *" in cl or "do not select *" in cl:
                recorded = True
                if "select *" in sql_l or "select *\n" in sql_l:
                    violated.append(c)
                else:
                    satisfied.append(c)
                continue

            # ORDER BY requirement
            if "order by" in cl and ("must" in cl or "include" in cl or "use" in cl or "require" in cl or "sort" in cl):
                recorded = True
                if "order by" in sql_l:
                    satisfied.append(c)
                else:
                    violated.append(c)
                continue

            # LIMIT requirement
            if "limit" in cl and ("must" in cl or "include" in cl or "use" in cl or "require" in cl or "only" in cl or "top" in cl):
                recorded = True
                if " limit " in sql_l or sql_l.endswith("limit") or "\nlimit " in sql_l:
                    satisfied.append(c)
                else:
                    violated.append(c)
                continue

            # DISTINCT requirement
            if "distinct" in cl and ("must" in cl or "use" in cl or "require" in cl or "include" in cl):
                recorded = True
                if "distinct" in sql_l:
                    satisfied.append(c)
                else:
                    violated.append(c)
                continue

            # JOIN requirement
            if "join" in cl and ("must" in cl or "use" in cl or "require" in cl or "include" in cl):
                recorded = True
                if " join " in sql_l:
                    satisfied.append(c)
                else:
                    violated.append(c)
                continue

            # GROUP BY requirement
            if "group by" in cl and ("must" in cl or "use" in cl or "require" in cl or "include" in cl):
                recorded = True
                if "group by" in sql_l:
                    satisfied.append(c)
                else:
                    violated.append(c)
                continue

            # WHERE / filter requirement
            if ("where" in cl or "filter" in cl) and ("must" in cl or "use" in cl or "require" in cl or "include" in cl):
                recorded = True
                if " where " in sql_l:
                    satisfied.append(c)
                else:
                    violated.append(c)
                continue

            if not recorded:
                # Constraints we cannot mechanically check are treated as
                # satisfied-by-trust; the weak solver's own self-check is the
                # primary guard for unparseable requirements.
                satisfied.append(c)

        return satisfied, violated

    def _build_repair_prompt(self, question, original_sql, violated_constraints):
        """Ask the weak solver to repair the SQL so it satisfies the listed constraints."""
        lines = []
        lines.append("Your previous SQL did not satisfy these HARD requirements from the user's Hint:")
        for idx, c in enumerate(violated_constraints, start=1):
            lines.append(f"  - HARD REQ {idx}: {c}.")
        lines.append("")
        lines.append("Previous SQL:")
        lines.append(original_sql)
        lines.append("")
        lines.append("Rewrite the SQL so that every HARD REQ above is satisfied.")
        lines.append("Keep the query semantically equivalent to the user's question.")
        lines.append("Return ONLY the corrected SQL.")
        return "\n".join(lines)

    def solve(self, question: str) -> str:
        # ----- Step 1: parse the Hint line and convert to hard constraints -----
        hint_text, constraints = self._parse_hint(question)

        # Rewrite the question for the weak solver so the Hint is restated as
        # an explicit, in-prompt requirement rather than a soft suggestion.
        if hint_text is not None:
            restated_question = question
            # Remove the original Hint: line so the solver does not double-count.
            cleaned_lines = []
            for ln in question.splitlines():
                low = ln.strip().lower()
                if low.startswith("hint:") or low.startswith("hint :"):
                    continue
                cleaned_lines.append(ln)
            restated_question = "\n".join(cleaned_lines).strip()

            enforced_block = []
            enforced_block.append("")
            enforced_block.append("ENFORCED HINT CONSTRAINTS (these are HARD requirements, not suggestions):")
            for idx, c in enumerate(constraints, start=1):
                enforced_block.append(f"  {idx}. {c}.")
            enforced_block.append("")
            enforced_block.append("Every numbered constraint above MUST be reflected in the SQL you return.")
            restated_question = restated_question + "\n" + "\n".join(enforced_block)
        else:
            restated_question = question

        # ----- Step 2: build a system prompt that enforces the constraints -----
        system_prompt = self._build_constraint_system_prompt(constraints)

        # ----- Step 3: first attempt by the weak solver -----
        raw = self.llm(
            prompt=restated_question,
            system=system_prompt,
            temperature=0.0,
            n=1,
        )
        sql = bridge.extract_sql(raw)

        # ----- Step 4: control-flow gate: verify SQL against constraints -----
        _, violated = self._verify_sql_against_constraints(sql, constraints)

        # ----- Step 5: if any constraint is violated, force a repair round-trip -----
        max_repairs = 2
        repair_round = 0
        while violated and repair_round < max_repairs:
            repair_round += 1
            repair_prompt = self._build_repair_prompt(question, sql, violated)
            raw2 = self.llm(
                prompt=repair_prompt,
                system=system_prompt,
                temperature=0.0,
                n=1,
            )
            new_sql = bridge.extract_sql(raw2)
            if new_sql and new_sql.strip():
                sql = new_sql
            _, violated = self._verify_sql_against_constraints(sql, constraints)

        # ----- Step 6: final execution sanity (no DDL/DML, single statement) -----
        if sql:
            stripped = sql.strip().rstrip(";").strip()
            head = stripped.split(None, 1)[0].upper() if stripped else ""
            if head not in {"SELECT", "WITH"}:
                # Reject anything that isn't a read-only query.
                sql = ""

        return sql if sql else ""