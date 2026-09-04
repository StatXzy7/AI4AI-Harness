"""Identifies relevant tables and columns from the question via a frozen LLM call, then generates SQL against the linked subset schema with optional error-driven retry."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns from the question
        identify_prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"And the following question: \"{question}\"\n\n"
            f"Identify which tables and columns are relevant to answering this question. "
            f"Return ONLY in this exact format:\n"
            f"TABLES: table1, table2, ... | COLUMNS: table1.col1, table2.col2, ...\n"
            f"If no tables seem relevant, return: TABLES: none | COLUMNS: none"
        )
        identify_response = self.llm(identify_prompt, system="", temperature=0.0, n=1)
        identified_text = bridge.extract_sql(identify_response)

        # Parse identified tables and columns
        tables_part = ""
        columns_part = ""
        if "TABLES:" in identified_text and "COLUMNS:" in identified_text:
            try:
                tables_part = identified_text.split("TABLES:")[1].split("|")[0].strip()
                columns_part = identified_text.split("COLUMNS:")[1].strip()
            except IndexError:
                pass

        # Step 2: Build linked subset schema from identified tables/columns
        if tables_part.lower() == "none" or not tables_part:
            subset_schema = self.schema
        else:
            table_names = [t.strip() for t in tables_part.split(",") if t.strip()]
            subset_schema = self._build_subset_schema(table_names, columns_part)

        # Step 3: Generate SQL against the subset schema
        sql_prompt = (
            f"Given the following database schema (only relevant tables and columns):\n\n"
            f"{subset_schema}\n\n"
            f"And the following question: \"{question}\"\n\n"
            f"Write a single SQL query that answers the question. "
            f"Return ONLY the SQL query, nothing else. "
            f"Use standard SQL syntax. Do not add explanations or markdown."
        )
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(sql_response)

        # Step 4: Execute and validate; retry once on error
        result = self.execute(final_sql)
        if not result["ok"] and result.get("error"):
            retry_prompt = (
                f"The following SQL query failed with error: \"{result['error']}\"\n\n"
                f"SQL: {final_sql}\n\n"
                f"Schema (subset):\n{subset_schema}\n\n"
                f"Question: \"{question}\"\n\n"
                f"Fix the SQL query to resolve the error. Return ONLY the corrected SQL query."
            )
            retry_response = self.llm(retry_prompt, system="", temperature=0.0, n=1)
            final_sql = bridge.extract_sql(retry_response)
            # Second attempt execution (result not re-checked per frozen-solver contract)
            self.execute(final_sql)

        return final_sql

    def _build_subset_schema(self, table_names: list, columns_part: str) -> str:
        """Extract only the specified tables and their listed columns from the full schema."""
        lines = self.schema.strip().split("\n")
        subset_lines = []
        in_table = False
        current_table = None

        for line in lines:
            stripped = line.strip()
            # Detect table header lines
            if stripped.upper().startswith("CREATE TABLE") or stripped.upper().startswith("TABLE "):
                # Extract table name from line
                found_table = None
                for t in table_names:
                    if t.lower() in stripped.lower():
                        found_table = t
                        break
                if found_table:
                    current_table = found_table
                    in_table = True
                    subset_lines.append(line)
                else:
                    in_table = False
                    current_table = None
            elif in_table and current_table:
                # This is a column/constraint line inside a relevant table
                if columns_part:
                    # Only keep columns that were identified
                    col_names = [c.strip() for c in columns_part.split(",")]
                    for col in col_names:
                        if col.lower() in stripped.lower():
                            subset_lines.append(line)
                            break
                else:
                    # Keep all columns for the table
                    subset_lines.append(line)

        return "\n".join(subset_lines) if subset_lines else self.schema