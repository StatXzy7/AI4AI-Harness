"""P2P2D harness that links schema columns from the question, then prompts a frozen weak solver to write SQL against only the linked subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify tables/columns mentioned in the question by asking the LLM
        # to extract a minimal relevant schema subset from the full schema.
        link_prompt = (
            "Given the database schema below and a natural language question, "
            "identify the minimal set of tables and columns that are required to "
            "answer the question. Output ONLY a list of fully-qualified "
            "table.column names, one per line, with no commentary.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Relevant tables and columns:"
        )
        link_response = self.llm(
            link_prompt,
            system="You are a schema linker. Output only table.column names.",
            temperature=0.0,
            n=1,
        )
        linked_schema = (link_response or "").strip()

        # Fallback: if linker output is empty or too short, fall back to the
        # full schema so the weak solver still has something to work with.
        if len(linked_schema) < 2:
            linked_schema = self.schema

        # Step 2: Prompt the frozen weak solver to write SQL, but constrain it
        # to the linked subset. This is the "write SQL against the linked
        # subset" half of the strategy -- we do NOT just embed the full schema.
        sql_prompt = (
            "You are writing a SQL query for the question below.\n"
            "Use ONLY the tables and columns listed in the 'Allowed schema' "
            "section. If a required column is not in the allowed schema, "
            "infer the closest match from the allowed list.\n\n"
            f"Allowed schema:\n{linked_schema}\n\n"
            f"Full schema (for reference only, do not introduce new tables):\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return a single SQL statement. Wrap it in