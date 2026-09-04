"""Parses a 'Hint:' line from the question and injects its constraints as hard requirements into the prompt before generating SQL via a frozen LLM solver."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Parse the Hint line from the question
        hint_constraints = []
        lines = question.strip().splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("hint:"):
                hint_text = stripped[len("Hint:"):].strip()
                # Split on common delimiters to extract individual constraints
                for part in hint_text.replace(";", ",").split(","):
                    part = part.strip()
                    if part:
                        hint_constraints.append(part)
                break  # only first Hint: line

        # Step 2: Build a hard-requirements block from parsed hints
        hard_requirements = ""
        if hint_constraints:
            hard_requirements = (
                "HARD REQUIREMENTS (derived from Hint: in the question — "
                "these MUST be satisfied by the generated SQL):\n"
            )
            for i, c in enumerate(hint_constraints, 1):
                hard_requirements += f"  {i}. {c}\n"
            hard_requirements += (
                "\nFailure to satisfy any of the above will result in an incorrect answer. "
                "Treat these as non-negotiable constraints.\n"
            )

        # Step 3: Construct the prompt with schema, question, and hard requirements
        prompt = (
            f"{hard_requirements}"
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a single SQL query that answers the question. "
            f"The query must satisfy all HARD REQUIREMENTS listed above.\n"
            f"Only output the SQL query, nothing else.\n"
        )

        # Step 4: Call the frozen LLM solver (temperature=0, n=1)
        raw_response = self.llm(prompt, system="", temperature=0.0, n=1)

        # Step 5: Extract the SQL string from the LLM output
        final_sql_string = bridge.extract_sql(raw_response)

        return final_sql_string