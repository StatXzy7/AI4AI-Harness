"""Schema-linking harness that first identifies tables/columns from the question, then writes SQL against the linked schema subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Schema linking - identify relevant tables/columns from the question
        linking_prompt = (
            "You are a schema linking assistant. Given the database schema and a natural language question, "
            "identify only the tables and columns that are required to answer the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Output a concise list of the relevant table names and column names needed. "
            "Format: Table.column relevant because ..."
        )
        linked_items = self.llm(
            linking_prompt,
            system="You are an expert at schema linking for Text-to-SQL.",
            temperature=0.0,
            n=1,
        )
        linked_items = bridge.extract_sql(linked_items) or linked_items

        # Step 2: Filter/extract a schema subset from the linked items
        linked_schema = self._build_linked_schema(linked_items)

        # Step 3: Write SQL against the linked schema subset
        sql_prompt = (
            "You are an expert SQL writer. Write a SQLite-compatible SQL query that answers the question "
            "using ONLY the tables and columns listed below.\n\n"
            f"Linked Schema (tables/columns relevant to this question):\n{linked_schema}\n\n"
            f"Full Schema (for reference):\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL query, no prose, no markdown fences."
        )
        raw_response = self.llm(
            sql_prompt,
            system="You write precise SQL queries against a small, linked schema subset.",
            temperature=0.0,
            n=1,
        )

        # Step 4: Extract the SQL text
        sql = bridge.extract_sql(raw_response)
        if not sql:
            sql = raw_response.strip()

        # Step 5: Validate via execution; on failure, retry once with an error-aware prompt
        result = self.execute(sql)
        if not result.get("ok"):
            error_msg = result.get("error", "unknown error")
            retry_prompt = (
                "You are an expert SQL writer. The previous query failed to execute. "
                "Fix it using only the linked schema subset.\n\n"
                f"Linked Schema:\n{linked_schema}\n\n"
                f"Question: {question}\n\n"
                f"Failed SQL: {sql}\n"
                f"Error: {error_msg}\n\n"
                "Return ONLY the corrected SQL query."
            )
            retry_response = self.llm(
                retry_prompt,
                system="You write and repair precise SQL queries.",
                temperature=0.0,
                n=1,
            )
            sql = bridge.extract_sql(retry_response) or retry_response.strip()

        return sql

    def _build_linked_schema(self, linked_items: str) -> str:
        """
        Build a compact representation of the schema subset identified by the linker.
        Falls back gracefully if parsing fails.
        """
        if not linked_items:
            return self.schema

        # Light-weight pass: pull any token of shape word.word or word and keep lines that
        # mention identifiers present in the full schema. This keeps the subset focused.
        tokens = set()
        for token in linked_items.replace(",", " ").split():
            token = token.strip(".,;:()[]\"'`")
            if "." in token:
                tokens.add(token.split(".")[0])
                tokens.add(token)
            else:
                tokens.add(token)

        keep_lines = []
        for line in self.schema.splitlines():
            stripped = line.strip()
            if not stripped:
                keep_lines.append(line)
                continue
            if any(tok and (tok in stripped) for tok in tokens):
                keep_lines.append(line)

        return "\n".join(keep_lines) if keep_lines else self.schema