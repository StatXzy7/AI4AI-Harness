"""Decomposes a natural-language question into ordered sub-questions, solves each with a small LLM call, and assembles the final SQL by stitching the sub-solutions together."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # ------------------------------------------------------------------
        # STAGE 1: Decompose the question into ordered sub-questions.
        # ------------------------------------------------------------------
        decompose_system = (
            "You are a query-planning assistant. Given a natural language "
            "question and a database schema, you break the question into a "
            "small, ordered list of sub-questions that, when answered in "
            "sequence, fully describe the SQL query needed.\n\n"
            "Rules:\n"
            "  - Each sub-question must be a self-contained, minimal NL step.\n"
            "  - Sub-questions must be ordered (the answer to one may feed "
            "    into the next).\n"
            "  - Cover: identifying tables/columns, filters/joins, "
            "    aggregations/grouping, ordering/limits.\n"
            "  - Output ONLY the numbered list, one sub-question per line. "
            "    No prose, no SQL.\n\n"
            "Schema:\n{schema}\n\n"
            "Question:\n{question}\n\n"
            "Sub-questions:"
        ).format(schema=self.schema, question=question)

        decompose_text = self.llm(decompose_system, system="", temperature=0.0, n=1)

        sub_questions = []
        for line in decompose_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip common leading enumerators like "1.", "1)", "-", "*".
            for prefix in ("- ", "* "):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            # Remove numeric prefixes like "1." or "1)".
            if len(line) > 2 and line[0].isdigit():
                # Find the first non-digit/non-dot/non-paren character.
                idx = 0
                while idx < len(line) and (line[idx].isdigit() or line[idx] in ".)"):
                    idx += 1
                line = line[idx:].strip()
            if line:
                sub_questions.append(line)

        # Defensive fallback: if decomposition yielded nothing useful, treat
        # the whole question as a single step so downstream still runs.
        if not sub_questions:
            sub_questions = [question]

        # ------------------------------------------------------------------
        # STAGE 2: Solve each sub-question individually with a focused call.
        # ------------------------------------------------------------------
        accumulated_context = []
        sub_solutions = []
        for idx, sub_q in enumerate(sub_questions, start=1):
            context_block = ""
            if accumulated_context:
                context_block = (
                    "Previously resolved steps (use these as ground truth, "
                    "do not change them):\n"
                    + "\n".join(accumulated_context)
                    + "\n\n"
                )

            sub_system = (
                "You are a precise Text-to-SQL assistant. You are answering "
                "ONE sub-question at a time that, together with the previous "
                "sub-answers, will build the final SQL.\n\n"
                "Schema:\n{schema}\n\n"
                "{context}"
                "Current sub-question ({idx} of {total}):\n{sub_q}\n\n"
                "Respond with a SHORT explanation followed by the SQL "
                "fragment (SELECT clause, WHERE clause, JOIN, etc.) that "
                "answers THIS sub-question. Wrap the SQL fragment in "
                "