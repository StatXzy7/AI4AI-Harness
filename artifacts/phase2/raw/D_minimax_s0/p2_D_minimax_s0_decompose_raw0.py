"""Decompose the text question into ordered sub-questions, solve each via small LLM calls, then assemble the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0Decompose(SQLHarness):
    """Plan-and-solve harness that decomposes a NL question into ordered sub-questions,
    resolves each sub-question with a focused LLM call, then composes the final SQL."""

    def solve(self, question: str) -> str:
        # ------------------------------------------------------------------
        # Step 1: Decompose the question into an ordered list of sub-questions
        # ------------------------------------------------------------------
        decomposition_prompt = f"""You are a SQL planning assistant.
Given a natural language question and a database schema, decompose the question
into an ORDERED list of small, focused sub-questions whose answers, when combined,
will allow the construction of the final SQL query.

Rules:
- Output ONLY a numbered list, each on a separate line.
- Each sub-question must be self-contained and answerable from the schema.
- The ordering must reflect a logical SQL construction order:
    1. Which tables / sources are needed?
    2. Which columns are projected (SELECT)?
    3. What filters / joins / conditions apply (WHERE, JOIN)?
    4. Are there aggregations or groupings (GROUP BY, HAVING)?
    5. Is there ordering or limiting (ORDER BY, LIMIT)?
- Do NOT write SQL. Do NOT include explanations outside the numbered list.

Schema:
{self.schema}

Question:
{question}

Ordered sub-questions:"""

        decomp_text = self.llm(
            decomposition_prompt,
            system="You decompose Text-to-SQL questions into ordered sub-questions.",
            temperature=0.0,
            n=1,
        )

        sub_questions = []
        for line in decomp_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading numbering like "1.", "1)", "- ", etc.
            for prefix in (f"{len(sub_questions)+1}.", f"{len(sub_questions)+1})"):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            if line.startswith("- "):
                line = line[2:].strip()
            if line:
                sub_questions.append(line)

        if not sub_questions:
            # Fallback: use the original question as the only sub-question
            sub_questions = [question]

        # ------------------------------------------------------------------
        # Step 2: Answer every sub-question using a dedicated, schema-aware LLM call
        # ------------------------------------------------------------------
        sub_answers = []  # list of (sub_question, answer) preserving order

        for idx, sub_q in enumerate(sub_questions, start=1):
            answer_prompt = f"""You are answering a single, focused sub-question that is part of
constructing a SQL query. Be precise and reference the schema by exact table and
column names. Output ONLY a concise, factual answer — no SQL yet.

Schema:
{self.schema}

Overall user question:
{question}

Sub-question {idx} of {len(sub_questions)}:
{sub_q}

Answer:"""
            ans_text = self.llm(
                answer_prompt,
                system="You answer SQL planning sub-questions using only the provided schema.",
                temperature=0.0,
                n=1,
            ).strip()
            sub_answers.append((sub_q, ans_text))

        # ------------------------------------------------------------------
        # Step 3: Assemble the final SQL from the ordered sub-answers
        # ------------------------------------------------------------------
        assembled_context = "\n".join(
            f"{i}. Sub-question: {sq}\n   Answer: {sa}"
            for i, (sq, sa) in enumerate(sub_answers, start=1)
        )

        assembly_prompt = f"""You are an expert Text-to-SQL engineer.
Using the schema and the ordered sub-question answers below, write a SINGLE
correct SQL query that answers the user's question.

Rules:
- Output ONLY the final SQL statement. No commentary, no markdown fences.
- Use exact table and column names from the schema.
- Prefer explicit JOIN syntax.
- Do not invent columns or tables not present in the schema.

Schema:
{self.schema}

User question:
{question}

Ordered sub-question answers:
{assembled_context}

Final SQL:"""

        assembled_text = self.llm(
            assembly_prompt,
            system="You compose final SQL from ordered planning sub-answers.",
            temperature=0.0,
            n=1,
        )

        final_sql = bridge.extract_sql(assembled_text)

        # ------------------------------------------------------------------
        # Step 4: Self-repair loop (execute, diagnose, regenerate) up to 2 attempts
        # ------------------------------------------------------------------
        for _ in range(2):
            result = self.execute(final_sql)
            if result.get("ok"):
                break

            error_msg = result.get("error", "unknown error")
            repair_prompt = f"""The SQL below produced an error when executed against the database.
Fix it using the schema and the original question.

Schema:
{self.schema}

User question:
{question}

Ordered sub-question answers (for context):
{assembled_context}

Failing SQL:
{final_sql}

Error message:
{error_msg}

Output ONLY the corrected SQL statement:"""
            repaired_text = self.llm(
                repair_prompt,
                system="You repair faulty SQL queries based on database error messages.",
                temperature=0.0,
                n=1,
            )
            candidate = bridge.extract_sql(repaired_text)
            if candidate:
                final_sql = candidate

        return final_sql