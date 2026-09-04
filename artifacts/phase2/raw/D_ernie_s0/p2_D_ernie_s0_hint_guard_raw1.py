"""Parses a 'Hint:' line from the question and enforces its constraints as hard requirements before generating SQL via a frozen LLM."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Parse the 'Hint:' line from the question
        hint_text = ""
        for line in question.splitlines():
            if line.startswith("Hint:"):
                hint_text = line[len("Hint:"):].strip()
                break

        # Step 2: Build a prompt that includes the schema, question, and hard requirements
        prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Hard requirements from hint: {hint_text if hint_text else 'None'}\n\n"
            f"Generate a SQL query that answers the question while strictly adhering to the hard requirements. "
            f"Output only the SQL query."
        )

        # Step 3: Call the frozen LLM (temperature=0.0, n=1) to get the raw text
        raw_text = self.llm(prompt, system="", temperature=0.0, n=1)

        # Step 4: Extract the SQL string from the LLM output
        sql = bridge.extract_sql(raw_text)

        # Step 5: (Optional) Verify execution; if it fails, return the extracted SQL anyway
        # This harness is designed for a frozen weak solver, so we trust the extraction.
        # Uncomment the following block if execution feedback is desired.
        # result = self.execute(sql)
        # if not result["ok"]:
        #     # In a real harness, one might retry or fallback, but here we return as-is.
        #     pass

        return sql