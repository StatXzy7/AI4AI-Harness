"""Decompose the question into ordered sub-questions, answer each one with a small schema-grounded LLM call, then assemble (and execution-repair) the final SQL from the accumulated sub-answers."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Decompose(SQLHarness):
    """Decompose -> solve sub-questions sequentially -> assemble final SQL."""

    MAX_SUBQUESTIONS = 6

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out)

    def _parse_subquestions(self, text: str):
        subs = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:Q?\d+[\.\):\-]|\-|\*)\s*(.+)$", line)
            if m:
                q = m.group(1).strip().strip('"')
                if q:
                    subs.append(q)
        if not subs:  # fallback: treat non-empty lines as sub-questions
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if len(lines) > 1:
                subs = lines
        return subs[: self.MAX_SUBQUESTIONS]

    # ------------------------------------------------------------------
    # main pipeline
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        # ---- Step 1: decompose into ordered sub-questions ----
        decompose_prompt = (
            "You are given a database schema and a natural-language question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Break the question into an ordered list of at most {self.MAX_SUBQUESTIONS} "
            "simple sub-questions that, when answered in order, lead to the final "
            "SQL query. Each sub-question should isolate one concrete decision: "
            "which tables/columns to use, join paths, filter conditions, "
            "aggregations, grouping, sorting, or limits.\n"
            "Output ONLY the numbered sub-questions, one per line, e.g.:\n"
            "1. ...\n2. ...\n3. ..."
        )
        raw_decomp = self._call_llm(
            decompose_prompt,
            system="You are a careful query planner for Text-to-SQL.",
        )
        sub_questions = self._parse_subquestions(raw_decomp)
        if not sub_questions:
            sub_questions = [question]

        # ---- Step 2: answer each sub-question with a small LLM call ----
        solved = []  # list of (sub_question, answer), kept in order
        for idx, sub_q in enumerate(sub_questions, 1):
            prior = "\n".join(
                f"Sub-question {j}: {q}\nAnswer {j}: {a}"
                for j, (q, a) in enumerate(solved, 1)
            )
            answer_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
            )
            if prior:
                answer_prompt += f"Previously resolved steps:\n{prior}\n\n"
            answer_prompt += (
                f"Sub-question {idx}: {sub_q}\n\n"
                "Answer this sub-question concisely and concretely in terms of "
                "the schema: name the exact tables and columns, the SQL "
                "construct needed (JOIN / WHERE / GROUP BY / ORDER BY / LIMIT / "
                "aggregation), and any literal values. Do NOT write the full "
                "SQL query yet."
            )
            answer = self._call_llm(
                answer_prompt,
                system="You are a precise Text-to-SQL analyst.",
            ).strip()
            solved.append((sub_q, answer))

        # ---- Step 3: assemble the final SQL from the sub-answers ----
        steps_block = "\n".join(
            f"Sub-question {i}: {q}\nAnswer {i}: {a}"
            for i, (q, a) in enumerate(solved, 1)
        )
        assemble_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Solved sub-questions (in order):\n"
            f"{steps_block}\n\n"
            "Using ONLY the solved sub-questions above, assemble one single SQL "
            "query that answers the original question. Output only the SQL."
        )
        final_text = self._call_llm(
            assemble_prompt,
            system="You are an expert SQLite SQL generator. Output only SQL.",
        )
        sql = bridge.extract_sql(final_text)

        # ---- Step 4: execute; on failure, repair once using the trace ----
        result = self.execute(sql)
        if not result.get("ok"):
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Sub-question analysis:\n"
                f"{steps_block}\n\n"
                f"The assembled SQL failed:\n{sql}\n\n"
                f"Database error: {result.get('error', '')}\n\n"
                "Fix the SQL so it executes correctly while staying faithful to "
                "the sub-question analysis. Output only the corrected SQL."
            )
            repaired_sql = bridge.extract_sql(
                self._call_llm(
                    repair_prompt,
                    system="You are an expert SQL debugger. Output only SQL.",
                )
            )
            if repaired_sql:
                sql = repaired_sql

        return sql