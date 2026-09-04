"""Harness that iteratively generates and executes SQL, classifying errors to apply targeted fixes over up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate an initial SQL query, execute it, and if it fails, classify the error
        (syntax, schema, or semantics) and apply a targeted fix in a second round.
        Returns the final SQL string (successful or last attempt).
        """
        # Helper to classify error type from the execution error string
        def classify_error(error: str) -> str:
            low = error.lower()
            if any(w in low for w in ["syntax", "near", "expected", "unrecognized"]):
                return "syntax"
            elif any(w in low for w in ["no such table", "no such column"]):
                return "schema"
            else:
                return "semantics"

        # Initial prompt for first SQL generation
        initial_prompt = f"""Given the following database schema:
{self.schema}

Question: {question}

Generate a SQL query that answers the question. Return only the SQL query."""

        # Variables to hold state between rounds
        current_sql = None
        error_str = None
        error_type = None

        for attempt in range(2):  # up to two rounds
            if attempt == 0:
                prompt = initial_prompt
            else:
                # Build fix instruction based on the previous error type
                if error_type == "syntax":
                    fix_instr = ("Fix the SQL syntax error. Ensure the SQL is valid SQLite syntax. "
                                 "Do not change the intended meaning.")
                elif error_type == "schema":
                    fix_instr = ("Fix the schema error. The table or column referenced does not exist. "
                                 "Use only tables and columns from the provided schema. "
                                 "Do not change the intended meaning.")
                else:  # semantics
                    fix_instr = ("Fix the semantic error. The SQL runs but produces an error or incorrect result. "
                                 "Adjust the query logic to match the question's intent while using the schema correctly.")

                prompt = f"""Given the following database schema:
{self.schema}

Question: {question}

Previous SQL attempt:
{current_sql}

Error: {error_str}

{fix_instr}

Generate a corrected SQL query that addresses the error. Return only the SQL query."""

            # Generate SQL text and extract the SQL
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(sql_text)

            # Execute the SQL
            result = self.execute(current_sql)

            if result["ok"]:
                return current_sql

            # If execution failed and this is the first attempt, record error for the next round
            if attempt == 0:
                error_str = result["error"]
                error_type = classify_error(error_str)
            else:
                # Second attempt failed; return the last generated SQL
                return current_sql

        # Fallback (should not be reached due to loop logic, but for safety)
        return current_sql if current_sql is not None else ""