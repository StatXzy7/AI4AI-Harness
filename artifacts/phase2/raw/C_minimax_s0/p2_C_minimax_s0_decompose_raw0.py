"""Decompose the question into ordered sub-questions, answer each via small LLM calls, then assemble the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0Decompose(SQLHarness):
    """Plan-to-Plan, Plan-to-SQL-Compose: a two-stage decomposition harness.

    Stage 1 (Plan-to-Plan): Break the natural language question into an
    ordered sequence of sub-questions that, taken together, specify every
    component needed to build the SQL (tables, columns, joins, filters,
    group-by, order-by, aggregations, etc.).

    Stage 2 (Plan-to-Compose): For each sub-question, query the LLM with a
    tight, focused prompt asking only for that SQL fragment. Stitch the
    fragments into a coherent final SELECT statement. Validate by
    executing against the live schema; on failure, perform one targeted
    repair pass before returning.
    """

    # ------------------------------------------------------------------ #
    #  Tunable knobs -- kept here so the strategy is explicit.          #
    # ------------------------------------------------------------------ #
    _MAX_REPAIR_ATTEMPTS = 1
    _LLM_TEMPERATURE = 0.0
    _LLM_N = 1

    # ------------------------------------------------------------------ #
    #  Public entry point                                               #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        """Return a SQL string that answers ``question`` over ``self.schema``."""

        # ----- Stage 1: decompose the question into ordered sub-questions -----
        sub_questions = self._decompose(question)

        # ----- Stage 2: answer each sub-question, get a SQL fragment -----
        fragments = []
        for idx, sq in enumerate(sub_questions, start=1):
            fragments.append(self._ask_fragment(idx, sq))

        # ----- Stage 3: assemble the final SQL from the fragments -----
        composed_sql = self._assemble(question, sub_questions, fragments)

        # Pull a single SELECT out (the assembler may include rationale).
        composed_sql = bridge.extract_sql(composed_sql) or composed_sql

        # ----- Stage 4: validate by execution; repair once if needed -----
        final_sql = self._validate_and_repair(question, composed_sql)
        return bridge.extract_sql(final_sql) or final_sql

    # ------------------------------------------------------------------ #
    #  Stage 1 -- Decompose into sub-questions                           #
    # ------------------------------------------------------------------ #
    def _decompose(self, question: str) -> list:
        """Ask the LLM to break ``question`` into an ordered list of sub-questions."""
        system = (
            "You are a Text-to-SQL planning assistant. "
            "Decompose the user's question into a minimal, ordered list of "
            "sub-questions that, answered in order, supply every detail "
            "needed to write a single SQL query.\n"
            "Output ONLY a numbered list, one sub-question per line, "
            "no commentary, no SQL."
        )
        prompt = self._wrap_with_schema(
            "Question:\n"
            f"{question}\n\n"
            "Return a numbered list (1., 2., 3., ...) of sub-questions."
        )
        raw = self.llm(prompt, system=system,
                       temperature=self._LLM_TEMPERATURE, n=self._LLM_N)
        return self._parse_numbered_list(raw)

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        """Parse '1. foo\\n2. bar' (or '- foo\\n- bar') into ['foo', 'bar']."""
        items = []
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # accept "1.", "1)", "1 -", or "- " / "* "
            for prefix_len in range(1, 5):
                head = stripped[:prefix_len]
                if head.rstrip(".)").isdigit() and stripped[prefix_len:].lstrip(
                        " .-):").strip():
                    stripped = stripped[prefix_len:].lstrip(" .-):").strip()
                    break
            else:
                if stripped.startswith(("- ", "* ")):
                    stripped = stripped[2:].strip()
            if stripped:
                items.append(stripped)
        # Fallback: treat the whole text as a single sub-question.
        return items or [(text or "").strip()]

    # ------------------------------------------------------------------ #
    #  Stage 2 -- Per-fragment LLM call                                   #
    # ------------------------------------------------------------------ #
    def _ask_fragment(self, index: int, sub_question: str) -> str:
        """Ask the LLM for the SQL fragment that answers one sub-question."""
        system = (
            "You supply ONE small SQL fragment for a single planning sub-question. "
            "Use the provided database schema. Output ONLY the fragment "
            "(no prose, no numbering, no semicolon). If the sub-question "
            "is purely informational (e.g. 'which tables?'), answer with "
            "the names separated by commas."
        )
        prompt = self._wrap_with_schema(
            f"Sub-question {index}: {sub_question}\n\n"
            "Provide the SQL fragment (or list of identifiers) that "
            "answers exactly this sub-question."
        )
        raw = self.llm(prompt, system=system,
                       temperature=self._LLM_TEMPERATURE, n=self._LLM_N)
        frag = bridge.extract_sql(raw) or raw
        return frag.strip().rstrip(";").strip()

    # ------------------------------------------------------------------ #
    #  Stage 3 -- Compose the final SQL                                   #
    # ------------------------------------------------------------------ #
    def _assemble(self, question: str, sub_questions: list, fragments: list) -> str:
        """Ask the LLM to stitch the fragments into a single correct SQL query."""
        joined = "\n".join(
            f"{i}. Q: {q}\n   Fragment: {frag}"
            for i, (q, frag) in enumerate(zip(sub_questions, fragments), start=1)
        )
        system = (
            "You are a Text-to-SQL composer. You will be given the user's "
            "original question, a numbered list of sub-questions, and the "
            "SQL fragment the planner produced for each. Combine them into "
            "ONE valid SQL query that answers the original question. "
            "Output ONLY the final SQL -- no explanation, no markdown fence."
        )
        prompt = self._wrap_with_schema(
            "Original question:\n"
            f"{question}\n\n"
            "Fragments:\n"
            f"{joined}\n\n"
            "Return the final SQL query."
        )
        out = self.llm(prompt, system=system,
                       temperature=self._LLM_TEMPERATURE, n=self._LLM_N)
        return out

    # ------------------------------------------------------------------ #
    #  Stage 4 -- Validate and repair                                     #
    # ------------------------------------------------------------------ #
    def _validate_and_repair(self, question: str, sql: str) -> str:
        """Run ``sql``; if it fails, perform one targeted repair call."""
        last = sql
        for _ in range(self._MAX_REPAIR_ATTEMPTS + 1):
            result = self.execute(last)
            if result.get("ok"):
                return last

            system = (
                "You repair SQL queries. You will receive the database schema, "
                "the original question, the current SQL, and the execution "
                "error. Output ONLY a corrected SQL query -- no prose."
            )
            prompt = self._wrap_with_schema(
                "Original question:\n"
                f"{question}\n\n"
                "Failing SQL:\n"
                f"{last}\n\n"
                "Execution error:\n"
                f"{result.get('error', '')}\n\n"
                "Return the corrected SQL."
            )
            repaired = self.llm(prompt, system=system,
                                temperature=self._LLM_TEMPERATURE,
                                n=self._LLM_N)
            last = bridge.extract_sql(repaired) or repaired
        return last

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _wrap_with_schema(self, body: str) -> str:
        """Prepend the live database schema to a prompt body."""
        schema = (self.schema or "").strip()
        if not schema:
            return body
        return f"Database schema:\n{schema}\n\n{body}"