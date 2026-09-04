"""Decomposes a Text-to-SQL question into ordered sub-questions, solves each with a small LLM call, then assembles the final SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the original question into ordered sub-questions
        decompose_prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"And the following question:\n\n"
            f"{question}\n\n"
            f"Decompose this question into 2-4 ordered sub-questions that, when answered "
            f"and combined, would fully answer the original question. Each sub-question "
            f"should be simpler and focus on one aspect of the data (e.g., filtering, "
            f"joining, aggregation). Return the sub-questions as a numbered list, one per line.\n\n"
            f"Sub-questions:\n1."
        )
        decompose_response = self.llm(decompose_prompt, system="", temperature=0.0, n=1)
        sub_questions = self._parse_subquestions(decompose_response)

        # Step 2: Solve each sub-question independently to get SQL fragments
        sql_fragments = []
        for i, sub_q in enumerate(sub_questions):
            fragment_prompt = (
                f"Given the following database schema:\n\n"
                f"{self.schema}\n\n"
                f"And the following sub-question (part {i + 1} of {len(sub_questions)}):\n\n"
                f"{sub_q}\n\n"
                f"Write a SQL query that answers this sub-question. Return only the SQL, no explanation.\n\n"
                f"SQL:"
            )
            fragment_response = self.llm(fragment_prompt, system="", temperature=0.0, n=1)
            sql_fragment = bridge.extract_sql(fragment_response)
            sql_fragments.append(sql_fragment)

        # Step 3: Assemble fragments into a single coherent final SQL
        assemble_prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"And the following SQL fragments from sub-questions:\n\n"
            + "\n".join(f"Fragment {i + 1}: {frag}" for i, frag in enumerate(sql_fragments))
            + f"\n\nOriginal question: {question}\n\n"
            f"Combine these fragments into a single coherent SQL query that fully answers "
            f"the original question. Return only the final SQL.\n\n"
            f"SQL:"
        )
        assemble_response = self.llm(assemble_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(assemble_response)

        # Step 4: Execute the assembled SQL and validate
        result = self.execute(final_sql)
        if result.get("ok"):
            return final_sql

        # Step 5: If execution fails, refine with error feedback
        refine_prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"The following SQL query failed with error: {result.get('error', 'Unknown error')}\n\n"
            f"SQL that failed:\n{final_sql}\n\n"
            f"Fix the SQL query so it executes successfully and answers the original question. "
            f"Return only the corrected SQL.\n\n"
            f"SQL:"
        )
        refine_response = self.llm(refine_prompt, system="", temperature=0.0, n=1)
        refined_sql = bridge.extract_sql(refine_response)

        # Verify the refined query works; if not, return it anyway as best effort
        refined_result = self.execute(refined_sql)
        if refined_result.get("ok"):
            return refined_sql

        return refined_sql

    def _parse_subquestions(self, text: str) -> list:
        """Parse numbered sub-questions from the LLM decomposition response."""
        lines = text.strip().split("\n")
        sub_questions = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Strip leading numbering like "1.", "2)", "-", etc.
            cleaned = line
            for prefix in ("1.", "2.", "3.", "4.", "5.", "1)", "2)", "3)", "4)", "5)", "- ", "* "):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip()
                    break
            if cleaned:
                sub_questions.append(cleaned)
        # Fallback: if parsing yielded nothing, return the raw text as a single sub-question
        if not sub_questions:
            return [text.strip()]
        return sub_questions