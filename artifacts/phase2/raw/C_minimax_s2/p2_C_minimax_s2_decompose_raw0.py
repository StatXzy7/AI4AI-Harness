"""Decompose the question into ordered sub-questions, solve each with a small LLM call, then assemble the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions.
        decompose_prompt = (
            "You are a Text-to-SQL planning assistant.\n"
            "Given a natural language question and a database schema, break the question "
            "into an ordered list of small sub-questions. Each sub-question should address "
            "one logical step (e.g., identify tables, identify columns, identify filters, "
            "identify joins, identify aggregations, identify ordering/limits).\n\n"
            "Schema:\n"
            f"{self.schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Output the sub-questions as a numbered list, one per line, with no extra commentary."
        )
        decomposition_text = self.llm(
            decompose_prompt,
            system="You decompose SQL questions into ordered sub-questions.",
            temperature=0.0,
            n=1,
        )
        sub_questions = self._parse_numbered_list(decomposition_text)

        # If decomposition failed, fall back to the original question.
        if not sub_questions:
            sub_questions = [question]

        # Step 2: Answer each sub-question individually using the weak solver.
        sub_answers = []
        for idx, sub_q in enumerate(sub_questions, start=1):
            answer_prompt = (
                f"You are answering sub-question {idx} of {len(sub_questions)} for a Text-to-SQL task.\n\n"
                "Schema:\n"
                f"{self.schema}\n\n"
                "Overall question:\n"
                f"{question}\n\n"
                "Sub-question to answer now:\n"
                f"{sub_q}\n\n"
                "Provide a concise, factual answer that helps construct the final SQL. "
                "If the sub-question asks for a specific SQL fragment (e.g., a WHERE clause, "
                "a JOIN condition, a column list), output that fragment directly. "
                "Do not write the full SQL yet; only answer this sub-question."
            )
            answer_text = self.llm(
                answer_prompt,
                system="You answer one sub-question at a time for SQL synthesis.",
                temperature=0.0,
                n=1,
            )
            sub_answers.append((sub_q, answer_text.strip()))

        # Step 3: Assemble the final SQL from the sub-answers.
        assembly_prompt_parts = [
            "You are assembling a final SQL query from previously computed sub-answers.",
            "",
            "Schema:",
            self.schema,
            "",
            "Original question:",
            question,
            "",
            "Sub-questions and their answers:",
        ]
        for i, (sq, sa) in enumerate(sub_answers, start=1):
            assembly_prompt_parts.append(f"{i}. Sub-question: {sq}")
            assembly_prompt_parts.append(f"   Answer: {sa}")
            assembly_prompt_parts.append("")

        assembly_prompt_parts.extend([
            "Using the above sub-answers, write the complete final SQL query that answers the original question.",
            "Return ONLY the SQL, with no explanation, no markdown, and no code fences."
        ])
        assembly_prompt = "\n".join(assembly_prompt_parts)

        assembled_text = self.llm(
            assembly_prompt,
            system="You assemble SQL from sub-answers.",
            temperature=0.0,
            n=1,
        )
        final_sql = bridge.extract_sql(assembled_text)

        # Step 4: If extract_sql returned nothing useful, try a direct fallback.
        if not final_sql:
            final_sql = assembled_text.strip()

        return final_sql

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        """Parse a numbered list like '1. ...\n2. ...' into a list of strings."""
        items = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Strip common numbering patterns: "1.", "1)", "1 -", "(1)"
            stripped = line
            for prefix_len in (0,):
                pass
            # Remove leading number + separator
            i = 0
            while i < len(stripped) and stripped[i].isdigit():
                i += 1
            if i > 0 and i < len(stripped) and stripped[i] in {".", ")"}:
                stripped = stripped[i + 1:].strip()
            elif i > 0 and i < len(stripped) and stripped[i] == "-" and (
                i + 1 >= len(stripped) or stripped[i + 1] == " "
            ):
                stripped = stripped[i + 1:].strip()
            else:
                # Not a numbered line; keep original.
                stripped = line
            if stripped:
                items.append(stripped)
        return items