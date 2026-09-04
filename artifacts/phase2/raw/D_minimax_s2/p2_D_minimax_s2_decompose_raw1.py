"""Decompose the question into ordered sub-questions, answer each with a small LLM call, then assemble the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the question into ordered sub-questions.
        decomp_system = (
            "You are a query planner. Given a natural language question and a database schema, "
            "break it down into an ordered list of atomic sub-questions needed to construct the SQL. "
            "Each sub-question should target one logical piece (identifying tables, identifying columns, "
            "filter conditions, aggregations, ordering, limits, etc.). "
            "Output ONLY a numbered list, one sub-question per line, nothing else."
        )
        decomp_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Sub-questions:"
        )
        decomp_text = self.llm(decomp_prompt, system=decomp_system, temperature=0.0, n=1)

        # Parse the decomposition into ordered sub-questions.
        sub_questions = []
        for line in decomp_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading numbering like "1.", "1)", "- ", etc.
            stripped = line
            for prefix in ("1)", "2)", "3)", "4)", "5)", "6)", "7)", "8)", "9)"):
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):].strip()
                    break
            # Handle "1.", "2.", etc.
            if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)":
                stripped = stripped[2:].strip()
            elif stripped.startswith("- "):
                stripped = stripped[2:].strip()
            if stripped:
                sub_questions.append(stripped)

        # Step 2: Answer each sub-question with a small LLM call.
        answers = []
        ans_system = (
            "You are a SQL planning assistant. Given the schema, the overall question, "
            "previously resolved sub-questions and their answers, and the current sub-question, "
            "answer the current sub-question concisely in plain English. Focus on identifying "
            "specific tables, columns, conditions, functions, or clauses relevant to that step. "
            "Be precise and do not include explanations beyond what is asked."
        )

        prev_qa = ""
        for sq in sub_questions:
            ans_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Overall Question: {question}\n\n"
                f"Previous Resolutions:\n{prev_qa if prev_qa else '(none)'}\n\n"
                f"Current Sub-question: {sq}\n\n"
                "Answer:"
            )
            a = self.llm(ans_prompt, system=ans_system, temperature=0.0, n=1)
            a = a.strip()
            answers.append(a)
            prev_qa += f"Q: {sq}\nA: {a}\n\n"

        # Step 3: Assemble the final SQL from the resolved sub-answers.
        assembly_system = (
            "You are an expert SQL writer. Given a database schema, a natural language question, "
            "and an ordered set of resolved sub-questions with answers, synthesize a single, "
            "executable SQL query that answers the question. "
            "Output ONLY the SQL statement, no prose, no markdown fences."
        )
        assembly_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Resolved Sub-questions:\n{prev_qa}\n\n"
            "Final SQL:"
        )
        assembled_text = self.llm(assembly_prompt, system=assembly_system, temperature=0.0, n=1)

        final_sql = bridge.extract_sql(assembled_text)

        # Step 4: Validate execution; if it fails, retry once with an error-aware prompt.
        result = self.execute(final_sql)
        if not result["ok"]:
            repair_system = (
                "You are an expert SQL debugger. Given a schema, question, a previously generated "
                "SQL that failed, and the error message, produce a corrected SQL query. "
                "Output ONLY the corrected SQL, no prose, no markdown fences."
            )
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Resolved Sub-questions:\n{prev_qa}\n\n"
                f"Failed SQL:\n{final_sql}\n\n"
                f"Error:\n{result['error']}\n\n"
                "Corrected SQL:"
            )
            repaired_text = self.llm(repair_prompt, system=repair_system, temperature=0.0, n=1)
            final_sql = bridge.extract_sql(repaired_text)

        return final_sql