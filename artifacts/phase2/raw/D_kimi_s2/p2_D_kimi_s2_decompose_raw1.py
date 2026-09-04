"""Decompose the question into ordered sub-questions, answer each with a small LLM call whose SQL is execution-probed, then assemble and execution-verify the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Decompose(SQLHarness):
    """Text-to-SQL harness driven by explicit sub-question decomposition.

    Control flow:
      1. ``_decompose`` -- one LLM call splits the question into an ordered
         list of sub-questions, each answerable by a single SQL query and
         building on the previous ones.
      2. ``_solve_subquestion`` -- one small LLM call per sub-question
         produces its SQL fragment; the fragment is executed so later steps
         and the assembler see verified intermediate results (or the error).
      3. ``_assemble`` -- one LLM call combines the original question with
         all solved steps into the final SQL.
      4. ``_validate_and_repair`` -- the final SQL is executed and, on
         failure, the database error is fed back for a bounded repair loop.
      5. ``_fallback`` -- direct single-shot generation, used whenever the
         decomposition or assembly stage yields no usable SQL.
    """

    MAX_SUBQUESTIONS = 6
    MAX_REPAIR_ATTEMPTS = 2
    MAX_SAMPLE_ROWS = 5
    MAX_SAMPLE_CHARS = 400

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        # Stage 1: ordered decomposition into sub-questions.
        sub_questions = self._decompose(question)

        # Stage 2: answer each sub-question with a small LLM call.
        solved = []
        for index, sub_q in enumerate(sub_questions, start=1):
            solved.append(self._solve_subquestion(question, sub_q, index, solved))

        # Stage 3: assemble the final SQL from the solved steps.
        final_sql = self._assemble(question, solved) if solved else ""

        # Degradation path: direct generation if decomposition/assembly failed.
        if not final_sql:
            final_sql = self._fallback(question)

        # Stage 4: execution check with a bounded repair loop.
        final_sql = self._validate_and_repair(question, final_sql, solved)
        return final_sql

    # ------------------------------------------------------------------
    # LLM plumbing
    # ------------------------------------------------------------------
    def _ask(self, prompt, system="", temperature=0.0):
        """Call the frozen solver's LLM and normalize the output to a string."""
        response = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        return response if isinstance(response, str) else str(response)

    # ------------------------------------------------------------------
    # Stage 1: decomposition
    # ------------------------------------------------------------------
    def _decompose(self, question):
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Decompose the question into an ordered list of at most "
            f"{self.MAX_SUBQUESTIONS} sub-questions such that:\n"
            "- each sub-question can be answered with ONE SQL query over the schema;\n"
            "- the sub-questions are ordered so that later ones may reuse the "
            "answers (or SQL logic) of earlier ones;\n"
            "- the LAST sub-question asks for exactly what the original question asks.\n"
            "If the question is already simple, output a single sub-question.\n"
            "Output ONLY the numbered list, one sub-question per line:\n"
            "1. <first sub-question>\n2. <second sub-question>\n..."
        )
        text = self._ask(prompt, system="You are a careful query planner for text-to-SQL.")
        return self._parse_subquestions(text)

    _ITEM_RE = re.compile(r"^\s*(?:\d{1,2}\s*[.\):]|[-*•])\s+(.*\S)\s*$")

    def _parse_subquestions(self, text):
        """Extract an ordered, de-duplicated, capped list of sub-questions."""
        items = []
        for raw in (text or "").splitlines():
            match = self._ITEM_RE.match(raw)
            if match:
                item = match.group(1).strip()
                if item:
                    items.append(item)
        seen, unique = set(), []
        for item in items:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[: self.MAX_SUBQUESTIONS]

    # ------------------------------------------------------------------
    # Stage 2: per-sub-question solving
    # ------------------------------------------------------------------
    def _solve_subquestion(self, question, sub_q, index, solved):
        history = self._format_solved(solved)
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Original question: {question}\n\n"
            "We are answering it step by step.\n"
        )
        if history:
            prompt += f"Previous steps:\n{history}\n\n"
        prompt += (
            f"Current step {index}: {sub_q}\n\n"
            "Write ONE SQL query that answers the current step, reusing the "
            "earlier steps' logic where helpful. Output ONLY the SQL query."
        )
        text = self._ask(prompt, system="You are an expert SQL generator. Output only SQL.")
        frag_sql = (bridge.extract_sql(text) or "").strip()
        note = self._probe(frag_sql)
        return {"sub_q": sub_q, "sql": frag_sql, "note": note}

    def _probe(self, sql):
        """Execute a fragment and return a short verification note."""
        if not sql:
            return "no SQL produced"
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: never crash the harness
            return f"execution raised: {exc}"
        if result.get("ok"):
            rows = result.get("rows") or []
            sample = repr(rows[: self.MAX_SAMPLE_ROWS])
            if len(sample) > self.MAX_SAMPLE_CHARS:
                sample = sample[: self.MAX_SAMPLE_CHARS] + "..."
            return f"OK ({len(rows)} row(s)); sample: {sample}"
        return f"ERROR: {result.get('error', 'unknown error')}"

    def _format_solved(self, solved):
        blocks = []
        for i, item in enumerate(solved, start=1):
            blocks.append(
                f"Step {i}: {item['sub_q']}\n"
                f"SQL {i}: {item['sql'] or '(none)'}\n"
                f"Outcome {i}: {item['note']}"
            )
        return "\n\n".join(blocks)

    # ------------------------------------------------------------------
    # Stage 3: assembly
    # ------------------------------------------------------------------
    def _assemble(self, question, solved):
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Original question: {question}\n\n"
            "The question was decomposed and solved step by step:\n"
            f"{self._format_solved(solved)}\n\n"
            "Using the steps above, write ONE final SQL query that answers the "
            "original question exactly. Repair any step that failed according "
            "to its recorded outcome. Output ONLY the final SQL query."
        )
        text = self._ask(
            prompt, system="You are an expert SQL generator. Output only the final SQL."
        )
        return (bridge.extract_sql(text) or "").strip()

    # ------------------------------------------------------------------
    # Stage 4: validation and bounded repair
    # ------------------------------------------------------------------
    def _validate_and_repair(self, question, sql, solved):
        if not sql:
            return sql
        context = self._format_solved(solved)
        current = sql
        for attempt in range(self.MAX_REPAIR_ATTEMPTS + 1):
            try:
                result = self.execute(current)
            except Exception as exc:  # defensive
                result = {"ok": False, "error": str(exc)}
            if result.get("ok"):
                return current
            if attempt >= self.MAX_REPAIR_ATTEMPTS:
                break
            error = result.get("error", "unknown error")
            prompt = (
                "Database schema:\n"
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
            )
            if context:
                prompt += f"Reasoning steps so far:\n{context}\n\n"
            prompt += (
                "The following SQL failed:\n"
                f"{current}\n\n"
                f"Database error: {error}\n\n"
                "Rewrite the SQL so it runs correctly and still answers the "
                "question. Output ONLY the corrected SQL query."
            )
            text = self._ask(prompt, system="You are an expert SQL debugger. Output only SQL.")
            fixed = (bridge.extract_sql(text) or "").strip()
            if not fixed:
                break
            current = fixed
        return current

    # ------------------------------------------------------------------
    # Degradation path
    # ------------------------------------------------------------------
    def _fallback(self, question):
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONE SQL query that answers the question. "
            "Output ONLY the SQL query."
        )
        text = self._ask(prompt, system="You are an expert SQL generator. Output only SQL.")
        sql = (bridge.extract_sql(text) or "").strip()
        return sql if sql else text.strip()