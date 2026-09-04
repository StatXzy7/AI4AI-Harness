"""P2P2C schema-linking harness: first identify relevant tables/columns, then write SQL against the linked subset."""
import json
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # ---- Step 1: Schema linking via LLM ----
        # Force the weak solver to identify ONLY the tables/columns it will need,
        # producing a narrowed subset of the full schema to ground SQL generation.
        link_system = (
            "You are a schema linker. Given a database schema and a natural "
            "language question, output a JSON object listing only the tables and "
            "columns required to answer the question. Use this exact format:\n"
            '{"tables": [{"name": "table_name", "columns": ["col1", "col2"]}, ...]}\n'
            "Do not include any prose. Output JSON only."
        )
        link_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Linked tables/columns (JSON only):"
        )
        link_raw = self.llm(link_prompt, system=link_system, temperature=0.0, n=1)
        link_text = link_raw if isinstance(link_raw, str) else str(link_raw)

        # Parse the JSON; fall back to the full schema on any failure.
        linked_subset = self.schema
        try:
            # Strip code fences if the model wrapped the JSON.
            cleaned = link_text.strip()
            if cleaned.startswith("