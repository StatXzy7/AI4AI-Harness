"""Harness that extracts Hint constraints from the question, enforces them as hard guards in the generated SQL, and wraps a frozen weak Text-to-SQL solver."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1HintGuard(SQLHarness):
    # Regex fragments used to detect common hint patterns
    _RE_YEAR = re.compile(r"\b(?:in|for|during)?\s*(?:the\s+)?(19|20)\d{2}\b", re.IGNORECASE)
    _RE_TOP_N = re.compile(r"\b(?:top|first|latest|most\s+recent|earliest|smallest|largest|highest|lowest)\s+(\d+)\b", re.IGNORECASE)
    _RE_ORDER = re.compile(r"\b(?:order\s+by|sort\s+by)\s+([a-zA-Z_][\w\.]*)\s+(asc|desc|ascending|descending)\b", re.IGNORECASE)
    _RE_AGG = re.compile(r"\b(count|sum|avg|average|min|minimum|max|maximum|total)\b", re.IGNORECASE)
    _RE_GROUP = re.compile(r"\b(group\s+by|per\s+|by\s+|for\s+each)\b", re.IGNORECASE)
    _RE_DISTINCT = re.compile(r"\b(distinct|unique|deduplicate|distinctly)\b", re.IGNORECASE)
    _RE_HINT_KW = re.compile(r"\bhint\s*:\s*", re.IGNORECASE)
    _RE_NOT_NULL = re.compile(r"\b(non-?null|not\s+null|exclude\s+null|ignore\s+null|where\s+\w+\s+is\s+not\s+null)\b", re.IGNORECASE)
    _RE_HAVING = re.compile(r"\b(having|with\s+a\s+minimum|at\s+least|>=?\s*\d+)\b", re.IGNORECASE)
    _RE_LIMIT = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)

    def _parse_hint(self, question: str):
        """Parse constraints from a 'Hint:' segment of the question."""
        m = self._RE_HINT_KW.search(question)
        if not m:
            # Fall back to the whole question if no explicit Hint: marker
            hint_text = question
            start = -1
        else:
            start = m.end()
            hint_text = question[start:]

        constraints = []
        hint_text_lower = hint_text.lower()

        # Year constraint
        ym = self._RE_YEAR.search(hint_text)
        if ym:
            year = ym.group(0)
            # Extract a clean 4-digit year
            dm = re.search(r"((?:19|20)\d{2})", year)
            if dm:
                constraints.append(f"WHERE clause must filter on year = {dm.group(1)} (or equivalent date range).")

        # Top-N / ordering type
        tn = self._RE_TOP_N.search(hint_text)
        if tn:
            n = tn.group(1)
            constraints.append(f"Result limited to top {n} rows.")

        # Order by with direction
        om = self._RE_ORDER.search(hint_text)
        if om:
            col, direction = om.group(1), om.group(2).lower()
            direction = "DESC" if direction.startswith("desc") else "ASC"
            constraints.append(f"Order results by {col} {direction}.")

        # Aggregation
        agg_terms = self._RE_AGG.findall(hint_text_lower)
        if agg_terms:
            constraints.append(f"Use aggregate function(s): {', '.join(sorted(set(agg_terms)))}.")

        # Group by
        if self._RE_GROUP.search(hint_text_lower):
            constraints.append("Use GROUP BY to partition appropriately.")

        # Distinct
        if self._RE_DISTINCT.search(hint_text_lower):
            constraints.append("Apply DISTINCT to remove duplicate rows.")

        # NOT NULL filtering
        if self._RE_NOT_NULL.search(hint_text_lower):
            constraints.append("Filter out NULL values (IS NOT NULL).")

        # Having / threshold
        if self._RE_HAVING.search(hint_text_lower):
            constraints.append("Apply a HAVING (or post-aggregation) threshold condition.")

        # Limit
        lm = self._RE_LIMIT.search(hint_text)
        if lm:
            constraints.append(f"Hard LIMIT {lm.group(1)} required.")

        return constraints, hint_text, start

    def _build_guard_prompt(self, original_prompt: str, constraints):
        """Insert a HARD REQUIREMENTS block immediately after the system/user separator."""
        if not constraints:
            guard_block = "HARD REQUIREMENTS: None — follow the question faithfully."
        else:
            items = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(constraints))
            guard_block = (
                "HARD REQUIREMENTS (derived from the Hint): these are non-negotiable and must "
                "be present in the final SQL.\n" + items
            )

        # Prepend guard block with explicit instruction, before the user question
        guarded = (
            f"{guard_block}\n\n"
            f"You MUST satisfy every numbered hard requirement above. If the question omits "
            f"a detail needed to fulfill them, infer the safest match from the schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{original_prompt}"
        )
        return guarded

    def _sanitize_sql(self, sql: str):
        """Light post-processing: drop trailing semicolons/whitespace."""
        if sql is None:
            return ""
        s = sql.strip()
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s

    def _meets_constraints(self, sql: str, constraints):
        """Best-effort structural check that the SQL contains the required knobs."""
        if not constraints:
            return True
        sql_l = sql.lower()
        ok = True
        for c in constraints:
            cl = c.lower()
            if "year =" in cl:
                m = re.search(r"year\s*=\s*((?:19|20)\d{2})", cl)
                if m and m.group(1) not in sql:
                    ok = False
                    break
            elif cl.startswith("result limited to top") or cl.startswith("hard limit"):
                pass  # The wrapped solver is responsible; we don't reject here.
            elif cl.startswith("order results by"):
                if "order by" not in sql_l:
                    ok = False
                    break
            elif cl.startswith("use aggregate"):
                if not re.search(r"\b(count|sum|avg|min|max)\s*\(", sql_l):
                    ok = False
                    break
            elif cl.startswith("use group by"):
                if "group by" not in sql_l:
                    ok = False
                    break
            elif cl.startswith("apply distinct"):
                if "distinct" not in sql_l:
                    ok = False
                    break
            elif "filter out null" in cl:
                if "is not null" not in sql_l and "isn't null" not in sql_l:
                    ok = False
                    break
            elif "having" in cl:
                if "having" not in sql_l:
                    ok = False
                    break
        return ok

    def solve(self, question: str) -> str:
        # 1. Parse Hint constraints FIRST (control-flow enforcement of the strategy).
        constraints, hint_text, hint_pos = self._parse_hint(question)

        # 2. Strip the raw Hint: line from the prompt body so the frozen solver
        #    sees a clean question, but we still enforce the constraints ourselves.
        if hint_pos >= 0:
            clean_question = question[:hint_pos].rstrip() + "\n\n" + question[hint_pos + len(hint_text):]
            clean_question = clean_question.strip()
        else:
            clean_question = question.strip()

        # 3. Build a guarded prompt with hard requirements injected.
        guarded_prompt = self._build_guard_prompt(clean_question, constraints)

        # 4. Ask the frozen weak solver (single low-temp sample).
        raw = self.llm(
            guarded_prompt,
            system=(
                "You are a precise Text-to-SQL generator. Output ONLY a single SQL statement "
                "that satisfies every HARD REQUIREMENT listed in the prompt. No commentary."
            ),
            temperature=0.0,
            n=1,
        )

        # 5. Extract SQL robustly.
        sql = bridge.extract_sql(raw)
        sql = self._sanitize_sql(sql)

        # 6. If constraints not obviously satisfied, do ONE corrective re-query
        #    that explicitly lists the missing requirements (true control-flow fallback).
        if constraints and not self._meets_constraints(sql, constraints):
            missing = []
            for c in constraints:
                if not self._meets_constraints(sql, [c]):
                    missing.append(c)
            fix_prompt = (
                "Your previous SQL did not satisfy these mandatory constraints:\n"
                + "\n".join(f"  - {m}" for m in missing)
                + f"\n\nRegenerate the SQL using this schema:\n{self.schema}\n\n"
                + f"Original question:\n{clean_question}\n\n"
                + "Output ONLY the corrected SQL."
            )
            retry_raw = self.llm(
                fix_prompt,
                system="You fix SQL so it strictly obeys every listed constraint. Output only SQL.",
                temperature=0.0,
                n=1,
            )
            retry_sql = bridge.extract_sql(retry_raw)
            sql = self._sanitize_sql(retry_sql)

        return sql