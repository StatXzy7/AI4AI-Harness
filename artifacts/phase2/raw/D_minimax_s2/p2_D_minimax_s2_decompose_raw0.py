"""Decompose-then-Plan harness: splits the question into ordered sub-questions, answers each via a dedicated LLM call, then assembles the final SQL through a planner pass with execution feedback."""

from ..harness_base import SQLHarness
from .. import bridge


DECOMPOSE_SYSTEM = (
    "You are a text-to-SQL decomposition planner. Read the user's natural language "
    "question and the database schema, then split it into a small, ordered list of "
    "sub-questions that, when answered in sequence, would let a downstream planner "
    "build a correct SQL query. Each sub-question must be self-contained, refer to "
    "concrete schema elements (tables/columns) by name, and have an obvious "
    "semantic role (identify tables, identify columns, identify filters, identify "
    "aggregations, identify joins, identify ordering, identify output projection, "
    "etc.). Output strictly valid JSON of the form "
    '{"sub_questions": [{"id": 1, "role": "...", "question": "..."}, ...]}. '
    "Do not output any SQL, any prose, and any commentary. Only the JSON object."
)


ANSWER_SYSTEM = (
    "You are a focused text-to-SQL sub-question answerer. Given the original "
    "question, the database schema, the list of previously answered sub-questions, "
    "and one current sub-question, produce a concise factual answer that names "
    "the specific schema elements (tables, columns, joins, conditions, "
    "aggregations) implied by the sub-question. Be terse. Do not write SQL. Do not "
    "add commentary."
)


PLAN_SYSTEM = (
    "You are a text-to-SQL assembler. You are given: (1) the original natural "
    "language question, (2) the database schema, (3) an ordered list of answered "
    "sub-questions with their factual answers. Your job is to assemble a single "
    "SQL query that answers the original question. Use the answered sub-questions "
    "as authoritative building blocks. Output ONLY the final SQL query, with no "
    "prose, no markdown fences, no explanation."
)


REPAIR_SYSTEM = (
    "You are a SQL repair assistant. The previous SQL query failed when executed "
    "against the database. The error message is shown. Use the schema, the "
    "original question, the answered sub-questions, and the failing SQL to "
    "produce a corrected SQL query. Address the reported error specifically "
    "(unknown column, wrong table, syntax, etc.). Output ONLY the corrected SQL "
    "query, with no prose, no markdown fences, no explanation."
)


class P2P2DMinimaxS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # ---- Step 1: Decompose the question into ordered sub-questions ----
        decompose_prompt = self._build_decompose_prompt(question)
        decompose_raw = self.llm(decompose_prompt, system=DECOMPOSE_SYSTEM, temperature=0.0, n=1)
        sub_questions = self._parse_sub_questions(decompose_raw)

        # ---- Step 2: Answer each sub-question independently ----
        answered = []
        for idx, sq in enumerate(sub_questions, start=1):
            ans_prompt = self._build_answer_prompt(question, answered, sq)
            ans_text = self.llm(ans_prompt, system=ANSWER_SYSTEM, temperature=0.0, n=1)
            answered.append({
                "id": sq.get("id", idx),
                "role": sq.get("role", ""),
                "question": sq.get("question", ""),
                "answer": ans_text.strip(),
            })

        # ---- Step 3: Assemble the final SQL via a planner pass ----
        plan_prompt = self._build_plan_prompt(question, answered)
        plan_raw = self.llm(plan_prompt, system=PLAN_SYSTEM, temperature=0.0, n=1)
        candidate_sql = bridge.extract_sql(plan_raw)

        # ---- Step 4: Execute; if it fails, request a correction ----
        result = self.execute(candidate_sql)
        if result.get("ok"):
            return candidate_sql

        repair_prompt = self._build_repair_prompt(question, answered, candidate_sql, result)
        repaired_raw = self.llm(repair_prompt, system=REPAIR_SYSTEM, temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repaired_raw)
        return repaired_sql if repaired_sql else candidate_sql

    # ------------------------------------------------------------------ #
    # Prompt builders
    # ------------------------------------------------------------------ #
    def _build_decompose_prompt(self, question: str) -> str:
        return (
            "DATABASE SCHEMA:\n"
            f"{self.schema}\n\n"
            "QUESTION:\n"
            f"{question}\n\n"
            "Decompose the question into an ordered list of sub-questions as JSON."
        )

    def _build_answer_prompt(self, question: str, answered, sq) -> str:
        parts = [
            "DATABASE SCHEMA:",
            self.schema,
            "",
            "ORIGINAL QUESTION:",
            question,
            "",
            "PREVIOUSLY ANSWERED SUB-QUESTIONS:",
        ]
        if answered:
            for item in answered:
                parts.append(
                    f"- [id={item['id']}, role={item['role']}] {item['question']} "
                    f"-> {item['answer']}"
                )
        else:
            parts.append("(none yet)")

        parts.append("")
        parts.append("CURRENT SUB-QUESTION:")
        parts.append(f"[role={sq.get('role', '')}] {sq.get('question', '')}")
        parts.append("")
        parts.append("Answer the current sub-question tersely, naming concrete schema elements.")
        return "\n".join(parts)

    def _build_plan_prompt(self, question: str, answered) -> str:
        parts = [
            "DATABASE SCHEMA:",
            self.schema,
            "",
            "ORIGINAL QUESTION:",
            question,
            "",
            "ANSWERED SUB-QUESTIONS (in order):",
        ]
        for item in answered:
            parts.append(
                f"- [id={item['id']}, role={item['role']}] {item['question']}\n"
                f"  Answer: {item['answer']}"
            )
        parts.append("")
        parts.append("Assemble a single SQL query using the answered sub-questions as building blocks.")
        parts.append("Output ONLY the SQL.")
        return "\n".join(parts)

    def _build_repair_prompt(self, question: str, answered, sql: str, result) -> str:
        parts = [
            "DATABASE SCHEMA:",
            self.schema,
            "",
            "ORIGINAL QUESTION:",
            question,
            "",
            "ANSWERED SUB-QUESTIONS:",
        ]
        for item in answered:
            parts.append(
                f"- [id={item['id']}, role={item['role']}] {item['question']} "
                f"-> {item['answer']}"
            )
        parts.append("")
        parts.append("FAILING SQL:")
        parts.append(sql)
        parts.append("")
        parts.append("EXECUTION ERROR:")
        parts.append(str(result.get("error", "")))
        parts.append("")
        parts.append("Produce a corrected SQL query. Output ONLY the SQL.")
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    def _parse_sub_questions(self, text: str):
        """Extract an ordered list of sub-questions from the decomposer's output."""
        import json
        import re

        cleaned = text.strip()

        # Strip markdown code fences if present.
        fence_match = re.search(r"