"""Generate a SQL query, execute it, classify any failure (syntax/schema/semantics) and apply a targeted fix for up to two attempts."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS1ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Attempt to answer the question with a SQL query.
        - First attempt: generate SQL from schema + question.
        - If execution fails, classify the error and retry with a
          strategy‑specific prompt (syntax, schema, or semantic fix).
        - At most two attempts are performed; the last generated SQL
          is returned.
        """
        max_attempts = 2
        previous_sql = None
        previous_error = None

        for attempt in range(max_attempts):
            # Build prompt
            if attempt == 0:
                prompt = (
                    f"Given the following database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Generate a SQL query that answers the question. "
                    f"Return only the SQL query."
                )
            else:
                # Include previous attempt information
                hint = ""
                if previous_error:
                    # Classify the previous error
                    err_lower = previous_error.lower()
                    if any(tok in err_lower for tok in ("syntax", "near", "sqlite")):
                        hint = (
                            "The previous SQL had a syntax error. "
                            "Please correct the syntax while keeping the intended logic. "
                        )
                    elif any(tok in err_lower for tok in ("no such table", "no such column")):
                        hint = (
                            "The previous SQL referenced a non‑existent table or column. "
                            "Please adjust the query to use correct table/column names from the schema. "
                        )
                    else:
                        hint = (
                            "The previous SQL executed but produced an unexpected result or error. "
                            "Please revise the query to correctly answer the question, considering data types and logic. "
                        )
                prompt = (
                    f"Given the following database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Previous SQL attempt:\n{previous_sql}\n\n"
                    f"Error from previous attempt:\n{previous_error}\n\n"
                    f"{hint}"
                    f"Generate a corrected SQL query. Return only the SQL query."
                )

            # Generate SQL
            raw_output = self.llm(prompt, system="", temperature=0.0, n=1)
            extracted_sql = bridge.extract_sql(raw_output).strip()

            # If extraction fails, treat as a syntax problem and retry with hint
            if not extracted_sql:
                previous_sql = raw_output
                previous_error = "Extraction failed (empty SQL)."
                continue

            # Execute the query
            result = self.execute(extracted_sql)

            # Success case
            if result.get("ok", False):
                return extracted_sql

            # Failure case – store and continue to next attempt
            previous_sql = extracted_sql
            previous_error = result.get("error", "Unknown error")

        # If we exit the loop without success, return the last generated SQL
        return previous_sql if previous_sql else ""