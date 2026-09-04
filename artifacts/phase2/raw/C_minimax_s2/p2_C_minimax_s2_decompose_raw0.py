"""Decompose a question into ordered sub-questions, answer each via LLM, then assemble the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge


DECOMPOSE_SYSTEM = """You are a query planner for Text-to-SQL. Break the user's question into an ordered list of small sub-questions that, when answered, give all the information needed to write one SQL query.

Rules:
- Output ONLY valid JSON, no prose, no markdown fences.
- Schema of JSON: {"subquestions": ["...", "...", ...]}
- Each sub-question must be answerable from the provided schema alone.
- Order matters: earlier sub-questions should provide context for later ones.
- Typical pattern: (1) identify target columns/measures, (2) identify filter conditions, (3) identify groupings/ordering/limits, (4) confirm joins if multiple tables.
- Do NOT write SQL. Only produce sub-questions in English.
"""

ANSWER_SYSTEM = """You answer a single sub-question about a database schema in the context of building a SQL query.

Rules:
- Be concise. Answer in 1-4 short sentences.
- Reference table and column names verbatim from the schema when relevant.
- If the sub-question cannot be answered from the schema, say "UNKNOWN".
- Do NOT write SQL. Only describe intent, table/column choices, conditions, or values.
"""

ASSEMBLE_SYSTEM = """You write one final SQL query for a given question, given a database schema and a set of answered sub-questions.

Rules:
- Output ONLY the SQL statement, no prose, no markdown fences.
- Use exact table and column names from the schema.
- Prefer a single SELECT statement.
- SQLite-compatible dialect unless the schema clearly indicates otherwise.
- Do not invent tables/columns not present in the schema.
"""


class P2P2CMinimaxS2Decompose(SQLHarness):
    """Plan -> Plan -> Code, with explicit decomposition (sub-question) stage."""

    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # --- Stage 1: Decompose the question into an ordered list of sub-questions ---
        decompose_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Produce the ordered list of sub-questions as JSON."
        )
        plan1_raw = self.llm(decompose_prompt, system=DECOMPOSE_SYSTEM, temperature=0.0, n=1)
        subquestions = self._parse_subquestions(plan1_raw)

        # Fallback: if we cannot extract sub-questions, use the question itself as one step
        if not subquestions:
            subquestions = [question]

        # --- Stage 2: Answer each sub-question in order, threading context forward ---
        answered = []
        context_so_far = ""
        for idx, sq in enumerate(subquestions, start=1):
            answer_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Original question: {question}\n\n"
                f"Already answered sub-questions and their answers:\n"
                f"{context_so_far if context_so_far else '(none yet)'}\n\n"
                f"Now answer sub-question {idx}/{len(subquestions)}: {sq}"
            )
            ans = self.llm(answer_prompt, system=ANSWER_SYSTEM, temperature=0.0, n=1).strip()
            if not ans:
                ans = "UNKNOWN"
            answered.append((sq, ans))
            context_so_far += f"Q{idx}: {sq}\nA{idx}: {ans}\n\n"

        # --- Stage 3: Assemble final SQL using the answers as a plan ---
        plan_block = "".join(
            f"Sub-question {i+1}: {sq}\nAnswer {i+1}: {ans}\n\n"
            for i, (sq, ans) in enumerate(answered)
        )
        assemble_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Resolved plan from sub-question answers:\n{plan_block}"
            "Write the final SQL."
        )
        final_text = self.llm(assemble_prompt, system=ASSEMBLE_SYSTEM, temperature=0.0, n=1)

        sql = bridge.extract_sql(final_text)

        # If extraction failed, retry once with a stricter instruction
        if not sql:
            retry_prompt = (
                assemble_prompt
                + "\n\nReminder: respond with exactly one SQL statement and nothing else."
            )
            retry_text = self.llm(retry_prompt, system=ASSEMBLE_SYSTEM, temperature=0.0, n=1)
            sql = bridge.extract_sql(retry_text)

        # Last-ditch fallback: return any non-empty trimmed string
        if not sql:
            sql = final_text.strip()

        return sql

    def _parse_subquestions(self, text: str) -> list:
        """Best-effort parse of the decomposition JSON; returns [] on failure."""
        if not text:
            return []
        import json
        import re

        # Try direct JSON parse first
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and isinstance(obj.get("subquestions"), list):
                return [str(s).strip() for s in obj["subquestions"] if str(s).strip()]
        except Exception:
            pass

        # Try to find a JSON object in the output
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict) and isinstance(obj.get("subquestions"), list):
                    return [str(s).strip() for s in obj["subquestions"] if str(s).strip()]
            except Exception:
                pass

        # Fallback: extract numbered or bulleted lines as sub-questions
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        subs = []
        for ln in lines:
            cleaned = re.sub(r"^[\-\*\u2022\d\.\)\(]+\s*", "", ln).strip()
            # Skip lines that are clearly not sub-questions
            if cleaned and not cleaned.startswith("{") and len(cleaned) > 3:
                subs.append(cleaned)
        return subs[:8]