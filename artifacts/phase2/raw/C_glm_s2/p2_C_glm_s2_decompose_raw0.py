"""Decomposes the question into an ordered plan of sub-questions, answers each sub-question with its own focused LLM call validated by database execution, then assembles the step SQLs into one final statement and repairs it against execution errors."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS2Decompose"]


class P2P2CGlmS2Decompose(SQLHarness):
    """Plan -> per-step solve -> compose -> execute-and-repair pipeline."""

    name = "p2p2c_glm_s2_decompose"

    # Tunables of the decomposition strategy.
    max_subquestions = 8    # hard cap on the length of the plan
    max_step_retries = 1    # re-asks per sub-question after a failed step
    max_final_repairs = 2   # repair attempts on the assembled SQL
    max_preview_rows = 5    # rows fed back to later steps as context
    max_cell_chars = 60     # truncation width for previewed cell values

    _NUM_RE = re.compile(r"^(?:step\s*)?(\d{1,2})(?:[.)\]:-]|\s)\s*(.+)$", re.IGNORECASE)

    _PLANNER_SYSTEM = (
        "You are a Text-to-SQL planning assistant. You never write SQL; "
        "you only split a question into an ordered checklist of sub-questions."
    )
    _SOLVER_SYSTEM = (
        "You are a precise Text-to-SQL engineer. You answer exactly one "
        "sub-question with exactly one SQLite SELECT statement and nothing else."
    )
    _COMPOSER_SYSTEM = (
        "You are a Text-to-SQL composer. You merge already-solved sub-questions "
        "into one final SQLite SELECT statement answering the user's question."
    )
    _REPAIR_SYSTEM = (
        "You are a Text-to-SQL debugger. You fix a failing SQLite SELECT "
        "statement using its execution error, changing as little as possible."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "SELECT 1"

        # Stage 1: plan the work as an ordered list of sub-questions.
        plan = self._decompose(question) or [question]

        # Stage 2: answer each sub-question with its own small LLM call,
        # validating every step against the database before moving on.
        trace = []
        for idx in range(len(plan)):
            trace.append(self._answer_step(question, plan, idx, trace))

        # Stage 3: assemble the step SQLs into a single final statement.
        final_sql = self._assemble(question, plan, trace)
        if not final_sql:
            final_sql = self._fallback_sql(trace)
        if not final_sql:
            return "SELECT 1"

        # Stage 4: execute-and-repair loop on the assembled SQL.
        return self._validate_and_repair(question, plan, trace, final_sql)

    # ------------------------------------------------------- stage 1: plan

    def _decompose(self, question: str):
        prompt = "\n".join([
            "Database schema:",
            self._schema(),
            "",
            "User question:",
            question,
            "",
            "Break the question into 2-6 short, ordered sub-questions so that answering them in",
            "order is sufficient to answer the original question with SQL. Rules:",
            "- Each sub-question must be answerable by ONE standalone SQL SELECT over the schema above.",
            "- Later sub-questions may depend on the results of earlier ones.",
            "- Preserve the exact filters, values and aggregation intent of the original question.",
            "- Do NOT write SQL, table aliases or column lists in this step.",
            "",
            "Output ONLY a numbered list, one sub-question per line:",
            "1) first sub-question",
            "2) second sub-question",
        ])
        subs = self._parse_plan(self._ask(prompt, self._PLANNER_SYSTEM))
        if not subs:
            return [question]
        return subs[: self.max_subquestions]

    def _parse_plan(self, text: str):
        numbered, loose = [], []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip().strip("`").strip()
            if not line:
                continue
            m = self._NUM_RE.match(line)
            if m:
                item = m.group(2).strip().strip('"').strip("'").strip()
                if self._plausible_subq(item):
                    numbered.append(item)
            elif self._plausible_subq(line) and self._questionish(line):
                loose.append(line)
        plan = numbered or loose
        seen, unique = set(), []
        for item in plan:
            key = re.sub(r"\s+", " ", item.lower())
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    @staticmethod
    def _plausible_subq(item: str) -> bool:
        if not (4 <= len(item) <= 400):
            return False
        low = item.lower().lstrip()
        return not low.startswith(("sorry", "i cannot", "i can't", "as an ai"))

    @staticmethod
    def _questionish(line: str) -> bool:
        low = line.lower()
        first = low.split(" ", 1)[0].strip(".,!?")
        return line.endswith("?") or first in {
            "what", "which", "who", "whom", "whose", "when", "where", "why",
            "how", "is", "are", "was", "were", "do", "does", "did", "can",
            "could", "should", "would", "will", "find", "list", "show",
            "count", "get", "compute", "calculate", "return", "give", "name",
            "tell", "identify", "determine",
        }

    # ------------------------------------------------- stage 2: solve steps

    def _answer_step(self, question, plan, idx, trace):
        """Answer plan[idx] with a dedicated LLM call; execute and retry on failure."""
        subq = plan[idx]
        last_sql, last_error = "", "no answer produced"
        for attempt in range(self.max_step_retries + 1):
            feedback = last_error if attempt > 0 else None
            text = self._ask(
                self._step_prompt(question, plan, idx, trace, feedback),
                self._SOLVER_SYSTEM,
            )
            sql = self._sql_of(text)
            if not sql:
                last_error = "the previous answer contained no extractable SQL statement"
                continue
            result = self._run(sql)
            last_sql = sql
            last_error = result["error"] or "execution failed"
            if result["ok"]:
                return {
                    "i": idx,
                    "subq": subq,
                    "sql": sql,
                    "ok": True,
                    "preview": self._preview(result["rows"]),
                    "error": "",
                }
        return {
            "i": idx,
            "subq": subq,
            "sql": last_sql,
            "ok": False,
            "preview": "",
            "error": last_error,
        }

    def _step_prompt(self, question, plan, idx, trace, feedback=None):
        lines = [
            "Database schema:",
            self._schema(),
            "",
            "Original user question:",
            question,
            "",
            "Ordered plan of sub-questions (answer only the one marked CURRENT):",
        ]
        for j, sub in enumerate(plan):
            marker = "  <-- CURRENT" if j == idx else ""
            lines.append(f"{j + 1}. {sub}{marker}")
        lines.append("")
        if trace:
            lines.append("Sub-questions already answered:")
            lines.extend(self._trace_lines(trace))
        else:
            lines.append("No sub-question has been answered yet.")
        lines += [
            "",
            f"Answer sub-question {idx + 1}: {plan[idx]}",
            "",
            "Constraints:",
            "- Output ONE standalone SQLite SELECT statement.",
            "- If this sub-question depends on earlier results, embed the earlier step SQL as a",
            "  subquery instead of guessing values you cannot know.",
            "- Do not answer any other sub-question and do not add explanations.",
            "- Wrap the statement in a single