"""Harness that first extracts referenced tables/columns via LLM then generates SQL constrained to that subset."""

from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2DErnieS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Solve the Text‑to‑SQL task by:
        1. Asking the LLM to list the tables and columns mentioned in the question.
        2. Using that information to guide a second LLM call that writes SQL
           referencing only the identified tables/columns.
        3. Extracting the final SQL string with bridge.extract_sql.
        """
        # ---------- Step 1: Identify tables and columns ----------
        identify_prompt = (
            f"Question: {question}\n\n"
            "Identify the tables and columns mentioned in the question. "
            "Return your answer in the following format (do not add extra text):\n"
            "TABLES: [table1, table2, ...]\n"
            "COLUMNS: [table1.col1, table2.col2, ...]"
        )
        identify_resp = self.llm(
            identify_prompt,
            system="",
            temperature=0.0,
            n=1,
        )

        # Simple parser – extracts the two bracketed lists.
        # If parsing fails we fall back to using the whole schema.
        tables = []
        columns = []
        try:
            # Find the two [...] sections.
            matches = re.findall(r"\[(.*?)\]", identify_resp, re.DOTALL)
            if len(matches) >= 2:
                tables = [t.strip() for t in matches[0].split(",") if t.strip()]
                columns = [c.strip() for c in matches[1].split(",") if c.strip()]
        except Exception:
            tables, columns = [], []

        # ---------- Step 2: Generate SQL constrained to the subset ----------
        # Build a concise description of the identified subset.
        subset_desc = ""
        if tables:
            subset_desc += f"Tables to use: {', '.join(tables)}\n"
        if columns:
            subset_desc += f"Columns to use: {', '.join(columns)}\n"

        sql_prompt = (
            f"Given the question and the identified tables/columns, write the SQL query.\n"
            f"Question: {question}\n"
            f"{subset_desc}"
            f"Schema:\n{self.schema}\n\n"
            "Write a SQL query that uses ONLY the identified tables and columns. "
            "Return ONLY the SQL statement, no extra commentary."
        )
        sql_resp = self.llm(
            sql_prompt,
            system="",
            temperature=0.0,
            n=1,
        )

        # ---------- Step 3: Extract the final SQL ----------
        final_sql = bridge.extract_sql(sql_resp)

        # Optional sanity‑check: try to execute; if it fails we could retry,
        # but for this harness we simply return the extracted SQL.
        # (Uncomment the following lines if you want a simple verification.)
        # exec_result = self.execute(final_sql)
        # if not exec_result.get("ok"):
        #     # Very simple fallback: retry once with a more generic prompt.
        #     fallback_prompt = (
        #         f"Question: {question}\nSchema:\n{self.schema}\n"
        #         "Write the SQL query. Return ONLY the SQL."
        #     )
        #     fallback_resp = self.llm(fallback_prompt, system="", temperature=0.0, n=1)
        #     final_sql = bridge.extract_sql(fallback_resp)

        return final_sql