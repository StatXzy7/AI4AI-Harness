"""Twostage: an initial LLM plan sketches table/column anchors, then a second LLM call composes SQL constrained to those anchors."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2BMinimaxS2G6(SQLHarness):
    def _extract_anchors(self, text: str) -> str:
        # Pull a compact list of "table.col" anchors from the planner output.
        anchors = []
        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b", text):
            anchors.append(f"{m.group(1)}.{m.group(2)}")
        # Preserve order, deduplicate.
        seen = set()
        ordered = []
        for a in anchors:
            if a.lower() not in seen:
                seen.add(a.lower())
                ordered.append(a)
        return ", ".join(ordered[:24])

    def solve(self, question: str) -> str:
        # Stage 1: planner identifies relevant tables/columns and the rough join structure.
        planner_system = (
            "You are a schema analyst. Given the schema and a question, output a short "
            "list of relevant table/column anchors (table.column form) and a one-line "
            "summary of how they should be joined. Do NOT write SQL."
        )
        planner_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Anchors and join plan:"
        )
        plan_raw = self.llm(planner_prompt, system=planner_system, temperature=0.0, n=1)
        anchors = self._extract_anchors(plan_raw)
        if not anchors:
            anchors = "(none identified)"

        # Stage 2: SQL writer uses the anchors + join plan as a hard constraint.
        writer_system = (
            "You are a Text-to-SQL writer. You MUST only reference the anchors provided "
            "below. Produce exactly one SQL query in a