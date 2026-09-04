"""Two-stage SQL generation: schema-aware sketch then executable refinement."""
# MECHANISM: twostage

class P2P2AMinimaxS2G2:
    def solve(self, question):
        # Stage 1: produce a schema-aware sketch (identifies tables/columns + intent)
        sketch_prompt = (
            "You are designing a SQL query plan.\n"
            "Given the schema and the question, produce a brief sketch that lists:\n"
            "  - which tables are needed\n"
            "  - which columns are needed\n"
            "  - join conditions\n"
            "  - filter conditions (WHERE)\n"
            "  - aggregations / GROUP BY\n"
            "  - ordering / limits\n"
            "Do NOT write SQL yet. Just a structured plan.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n"
            "SKETCH:"
        )
        sketch = self.llm(sketch_prompt, system="", temperature=0.0, n=1)

        # Stage 2: consume the sketch artifact and write executable SQL
        sql_prompt = (
            "You are a Text-to-SQL generator.\n"
            "Use the provided PLAN (from a prior reasoning stage) to write ONE "
            "executable SQLite-compatible SQL query that answers the question.\n"
            "Use only tables/columns mentioned in the schema or plan.\n"
            "Output ONLY the SQL, no prose, no markdown fences.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"PLAN:\n{sketch}\n\n"
            f"QUESTION: {question}\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Cheap consistency sanity check: if it fails to execute, fall back to
        # a plain generation that uses only the schema + question. This keeps
        # the harness robust if the sketch misled the second stage.
        result = self.execute(sql)
        if not result["ok"]:
            fallback_raw = self.llm(
                "Write ONE executable SQLite SQL query for the question.\n"
                "Output ONLY the SQL.\n\n"
                f"SCHEMA:\n{self.schema}\n\n"
                f"QUESTION: {question}\nSQL:",
                system="", temperature=0.0, n=1,
            )
            sql = bridge.extract_sql(fallback_raw)

        return sql