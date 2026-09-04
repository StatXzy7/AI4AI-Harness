"""Decomposes a natural-language question into ordered sub-questions, answers each with a small LLM call, then assembles the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions.
        decompose_system = (
            "You are a query planner. Given a natural-language question and a database schema, "
            "break the question into a small ordered list of sub-questions that, when answered in "
            "sequence, would let you construct the final SQL query. Each sub-question should focus "
            "on one reasoning step (e.g., identifying relevant tables, determining join conditions, "
            "specifying filters, specifying aggregations, specifying ordering/limits). "
            "Return ONLY a numbered list, one sub-question per line, like:\n"
            "1. <sub-question>\n2. <sub-question>\n..."
        )
        decompose_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Provide the ordered list of sub-questions."
        )
        decomposition_text = self.llm(decompose_prompt, system=decompose_system, temperature=0.0, n=1)

        # Parse the decomposition into an ordered list of sub-questions.
        sub_questions = []
        for line in decomposition_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading numbering like "1.", "1)", "1 -".
            import re
            m = re.match(r"^\d+[\.\)]\s*(.*)$", line)
            if m:
                sub_questions.append(m.group(1).strip())
            else:
                # If a line has no numbering but we haven't collected anything yet, treat as a sub-q.
                if not sub_questions:
                    sub_questions.append(line)

        if not sub_questions:
            # Fallback: treat the original question as the single sub-question.
            sub_questions = [question]

        # Step 2: Answer each sub-question with a small LLM call, building up context.
        context = ""
        answers = []
        answer_system = (
            "You are a careful SQL reasoning assistant. Given the schema, the original question, "
            "previously answered sub-questions, and the next sub-question, answer the next "
            "sub-question concisely and precisely. Use concrete table/column names from the schema. "
            "Do NOT write SQL yet; only provide the reasoning answer for this sub-question."
        )
        for i, sub_q in enumerate(sub_questions, start=1):
            prior = "\n".join(
                [f"Q{a_i}: {a_q}\nA{a_i}: {a_a}" for a_i, (a_q, a_a) in enumerate(answers, start=1)]
            ) if answers else "(none)"
            answer_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Previous sub-questions and answers:\n{prior}\n\n"
                f"Next sub-question ({i}/{len(sub_questions)}): {sub_q}\n\n"
                "Answer concisely."
            )
            ans_text = self.llm(answer_prompt, system=answer_system, temperature=0.0, n=1).strip()
            answers.append((sub_q, ans_text))

        # Step 3: Assemble the final SQL from the accumulated sub-question answers.
        assembly = "\n".join(
            [f"Sub-question {i}: {q}\nAnswer {i}: {a}" for i, (q, a) in enumerate(answers, start=1)]
        )
        assembly_system = (
            "You are an expert SQL writer. Given the schema, the original question, and a list of "
            "answered sub-questions, synthesize these into ONE correct SQL query that answers the "
            "original question. Output ONLY the final SQL statement (no prose, no explanation, no "
            "markdown fences)."
        )
        assembly_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Answered sub-questions:\n{assembly}\n\n"
            "Final SQL:"
        )
        final_text = self.llm(assembly_prompt, system=assembly_system, temperature=0.0, n=1)

        final_sql = bridge.extract_sql(final_text)

        # Step 4: Validate by execution; if it fails, attempt a single corrective retry.
        result = self.execute(final_sql)
        if not result.get("ok"):
            repair_system = (
                "You are an expert SQL debugger. The previous SQL query failed when executed. "
                "Given the schema, original question, the reasoning sub-questions, and the error "
                "message, produce a corrected SQL query. Output ONLY the corrected SQL statement "
                "(no prose, no markdown fences)."
            )
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Answered sub-questions:\n{assembly}\n\n"
                f"Previous SQL:\n{final_sql}\n\n"
                f"Execution error: {result.get('error', '')}\n\n"
                "Corrected SQL:"
            )
            repaired_text = self.llm(repair_prompt, system=repair_system, temperature=0.0, n=1)
            repaired_sql = bridge.extract_sql(repaired_text)
            if repaired_sql:
                final_sql = repaired_sql

        return final_sql