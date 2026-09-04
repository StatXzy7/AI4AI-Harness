"""A harness that extracts a 'Hint:' line from the user question and restates it as hard SQL constraints before prompting the frozen LLM."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        main_question, hint = self._extract_hint(question)

        if hint:
            prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{main_question}\n\n"
                "Hard constraints from the Hint (you MUST satisfy these exactly):\n"
                f"{hint}\n\n"
                "Write a valid SQL query that satisfies both the question and every hard constraint."
            )
            system = (
                "You are an expert SQL generator. The user question contains a hint; "
                "the constraints extracted from that hint are absolute requirements. "
                "Generate SQL that obeys them."
            )
        else:
            prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                "Write a valid SQL query."
            )
            system = "You are an expert SQL generator."

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(raw)

    @staticmethod
    def _extract_hint(question: str):
        lines = question.splitlines()
        main_lines = []
        hints = []
        hint_pattern = re.compile(r'^\s*hint\s*:\s*(.*)$', re.IGNORECASE)

        for line in lines:
            match = hint_pattern.match(line)
            if match:
                hint_text = match.group(1).strip()
                if hint_text:
                    hints.append(hint_text)
            else:
                main_lines.append(line)

        hint = " ".join(hints) if hints else None
        main_question = "\n".join(main_lines).strip()
        return main_question, hint