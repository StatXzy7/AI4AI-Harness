"""Schema-linking harness that first identifies referenced tables/columns, then constrains SQL generation to the linked subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Ask the LLM to extract referenced tables and columns from the question
        link_prompt = (
            "You are performing schema linking for a Text-to-SQL task.\n"
            "Given the database schema below and the user's natural language question, "
            "identify ONLY the tables and columns that are necessary to answer the question.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            "Output format (strict):\n"
            "TABLES: <comma-separated table names>\n"
            "COLUMNS: <table.column, table.column, ...>\n"
            "REASON: <one short sentence explaining the linkage>"
        )
        link_response = self.llm(link_prompt, system="", temperature=0.0, n=1)

        # Step 2: Parse the link response to obtain the linked subset
        linked_tables = []
        linked_columns = []
        for raw in (link_response or "").splitlines():
            line = raw.strip()
            if line.upper().startswith("TABLES:"):
                linked_tables = [
                    t.strip().strip("`").strip()
                    for t in line.split(":", 1)[1].split(",")
                    if t.strip()
                ]
            elif line.upper().startswith("COLUMNS:"):
                linked_columns = [
                    c.strip().strip("`").strip()
                    for c in line.split(":", 1)[1].split(",")
                    if c.strip()
                ]

        # Step 3: Build a constrained schema view using only the linked subset
        constrained_lines = []
        schema_lines = self.schema.splitlines()
        keep_table = None
        for line in schema_lines:
            stripped = line.strip()
            upper = stripped.upper()
            # Heuristic: treat lines that look like CREATE TABLE or table headers as table markers
            if upper.startswith("CREATE TABLE") or upper.endswith("(") and "TABLE" in upper:
                # Extract table name naively
                token = stripped.split()[2] if upper.startswith("CREATE TABLE") else stripped.split()[0]
                token = token.strip("(").strip()
                if any(t.lower() == token.lower() for t in linked_tables):
                    keep_table = token
                    constrained_lines.append(line)
                else:
                    keep_table = None
            elif keep_table is not None:
                # Keep lines that reference any linked column (or are structural)
                if not linked_columns or any(col.split(".")[-1].lower() in stripped.lower()
                                             for col in linked_columns):
                    constrained_lines.append(line)
                # Preserve closing paren / trailing structural lines
                elif stripped.startswith(")") or stripped.endswith(");"):
                    constrained_lines.append(line)

        constrained_schema = "\n".join(constrained_lines) if constrained_lines else self.schema

        # Step 4: Generate the SQL against the linked/constrained schema
        sql_prompt = (
            "You are an expert SQL generator. Given the (already linked) schema subset and the user's "
            "question, produce ONE executable SQL query. Only use the tables and columns shown.\n\n"
            f"LINKED TABLES: {', '.join(linked_tables) if linked_tables else '(all relevant tables)'}\n"
            f"SCHEMA SUBSET:\n{constrained_schema}\n\n"
            f"QUESTION: {question}\n\n"
            "Return ONLY the SQL statement, no prose, no markdown fences."
        )
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(sql_response)

        # Step 5: Fallback / refinement if no result -- attempt a full-schema pass
        if not final_sql or not final_sql.strip().rstrip(";").lower().startswith(("select", "with")):
            fallback_prompt = (
                "You are an expert SQL generator. Using the FULL schema below, answer the question "
                "with a single SQL statement. Output ONLY SQL, no commentary.\n\n"
                f"SCHEMA:\n{self.schema}\n\n"
                f"QUESTION: {question}"
            )
            fallback_response = self.llm(fallback_prompt, system="", temperature=0.0, n=1)
            final_sql = bridge.extract_sql(fallback_response)

        return final_sql if final_sql else ""