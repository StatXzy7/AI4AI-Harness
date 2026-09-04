"""Decomposes a natural-language question into ordered sub-questions, answers each with a small LLM call, and assembles the final SQL from the chain of responses."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Decompose the original question into ordered sub-questions.
        # We use a single, cheap LLM call that is restricted to producing a
        # numbered list. The list is then parsed into a Python list of strings
        # that drives the rest of the pipeline.
        decomposition_system = (
            "You are a query planner. Given a natural-language question and a "
            "database schema, output ONLY an ordered numbered list of minimal "
            "sub-questions whose answers together provide every fact needed to "
            "write the final SQL. Each sub-question must be short, atomic, and "
            "answerable from the schema. Do not include the SQL itself."
        )
        decomposition_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Output an ordered numbered list of sub-questions, one per line, "
            "like:\n1. ...\n2. ...\n3. ..."
        )
        decomposition_raw = self.llm(
            decomposition_prompt,
            system=decomposition_system,
            temperature=0.0,
            n=1,
        )
        sub_questions = self._parse_numbered_list(decomposition_raw)
        # Fallback: if the LLM failed to produce a list, treat the original
        # question as the only sub-question so the pipeline still produces a
        # result.
        if not sub_questions:
            sub_questions = [question]

        # Step 2: Answer each sub-question independently with a small LLM call.
        # We accumulate (question, answer) pairs so the assembler has full
        # provenance. This is the actual "minimax-S2" style: many small,
        # targeted generations rather than one large monolithic generation.
        qa_pairs = []
        answer_system = (
            "You answer a single, narrowly-scoped question about a database "
            "schema. Be concise and factual. Quote relevant table/column names "
            "verbatim from the schema. Do not write SQL."
        )
        for idx, sub_q in enumerate(sub_questions, start=1):
            answer_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Sub-question {idx}: {sub_q}\n\n"
                "Answer in 1-3 short sentences."
            )
            sub_a = self.llm(
                answer_prompt,
                system=answer_system,
                temperature=0.0,
                n=1,
            ).strip()
            qa_pairs.append((sub_q, sub_a))

        # Step 3: Assemble the final SQL from the collected answers. The
        # assembler is given the original question, the schema, and the full
        # ordered Q/A trace so it can stitch the fragments together.
        assembly_system = (
            "You are a SQL writer. Using the schema and the provided ordered "
            "answers to sub-questions, write a single correct SQLite-compatible "
            "SQL query that answers the original question. Output ONLY the SQL "
            "statement, no prose, no markdown fences."
        )
        trace_text = "\n".join(
            f"Q{i+1}: {q}\nA{i+1}: {a}" for i, (q, a) in enumerate(qa_pairs)
        )
        assembly_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Original question: {question}\n\n"
            f"Sub-question answers (in order):\n{trace_text}\n\n"
            "Final SQL:"
        )
        assembled_raw = self.llm(
            assembly_prompt,
            system=assembly_system,
            temperature=0.0,
            n=1,
        )

        # Step 4: Normalise / extract the SQL. bridge.extract_sql handles
        # fenced code blocks, stray prose, and trailing semicolons uniformly.
        final_sql = bridge.extract_sql(assembled_raw)

        # Step 5: Cheap self-repair loop. If the query fails to execute, we
        # feed the error back to the assembler once or twice. This keeps the
        # harness robust without re-decomposing the question.
        for _ in range(2):
            result = self.execute(final_sql)
            if result.get("ok"):
                break
            error_msg = result.get("error", "unknown error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Sub-question answers (in order):\n{trace_text}\n\n"
                f"Previous SQL:\n{final_sql}\n\n"
                f"Execution error:\n{error_msg}\n\n"
                "Produce a corrected SQL query. Output ONLY the SQL."
            )
            repaired_raw = self.llm(
                repair_prompt,
                system=assembly_system,
                temperature=0.0,
                n=1,
            )
            candidate = bridge.extract_sql(repaired_raw)
            if candidate:
                final_sql = candidate

        return final_sql

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        """Parse an LLM-produced numbered list into a clean list of strings.

        Accepts lines like '1. foo', '2) bar', ' 3 - baz '. Stops at the first
        blank line or non-list content. Returns [] on failure.
        """
        items = []
        if not text:
            return items
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if items:
                    # Allow trailing blanks but not gaps mid-list.
                    continue
                continue
            # Match "N." or "N)" or "- " style leaders after an optional digit.
            import re
            m = re.match(r"^\d+[\.\)]\s*(.+)$", stripped)
            if m:
                items.append(m.group(1).strip())
            elif stripped[:2].lower() in {"- ", "* "}:
                items.append(stripped[2:].strip())
            else:
                # Stray non-list content: stop parsing.
                if items:
                    break
        return items