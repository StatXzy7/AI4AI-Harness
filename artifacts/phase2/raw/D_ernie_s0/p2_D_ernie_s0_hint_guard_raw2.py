"""Parses the 'Hint:' line from the question, restates its constraints as hard requirements, and feeds them to the frozen LLM solver to produce validated SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Parse the 'Hint:' line from the question
        hint_lines = [line.strip() for line in question.splitlines() if line.strip().startswith("Hint:")]
        hint_text = " ".join(hint_lines) if hint_lines else ""

        # Strip the "Hint:" prefix to get the raw hint content
        if hint_text:
            hint_content = hint_text[len("Hint:"):].strip()
        else:
            hint_content = ""

        # Step 2: Restate hint constraints as hard requirements
        hard_requirements = ""
        if hint_content:
            hard_requirements = (
                f"\n\nHARD REQUIREMENTS (must be satisfied in the SQL):\n"
                f"{hint_content}\n"
                f"You MUST obey every constraint listed above. Do not ignore or relax any of them."
            )

        # Step 3: Build the prompt that includes schema + hint-as-requirement + question
        prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Answer the following question by writing a single SQL query."
            f"{hard_requirements}"
            f"\n\nQuestion: {question}\n\n"
            f"Write only the SQL query. Do not include any explanation."
        )

        # Step 4: Call the frozen weak solver LLM
        raw_output = self.llm(prompt, system="", temperature=0.0, n=1)

        # Step 5: Extract SQL from the LLM output
        final_sql = bridge.extract_sql(raw_output)

        # Step 6: Optionally validate by executing (guard against bad SQL)
        if final_sql:
            result = self.execute(final_sql)
            if not result.get("ok", False) and result.get("error"):
                # If execution fails, retry once with a fallback prompt that emphasizes the hint constraints
                retry_prompt = (
                    f"Your previous SQL failed with error: {result.get('error')}\n"
                    f"Database schema:\n\n{self.schema}\n\n"
                    f"HARD REQUIREMENTS (must be satisfied):\n{hint_content}\n\n"
                    f"Question: {question}\n\n"
                    f"Write a corrected SQL query that satisfies all hard requirements."
                )
                retry_output = self.llm(retry_prompt, system="", temperature=0.0, n=1)
                final_sql = bridge.extract_sql(retry_output)

        return final_sql