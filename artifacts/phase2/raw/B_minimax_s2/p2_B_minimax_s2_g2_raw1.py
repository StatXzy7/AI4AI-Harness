"""Two-stage harness: an LLM first drafts a skeleton/spec, then a second LLM expands it into a final SQL query using the schema and skeleton as focused context."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        # ---- Stage 1: produce a compact query skeleton (spec) ----
        skeleton_prompt = (
            "You are a Text-to-SQL skeleton planner.\n"
            "Given a natural language question and a database schema, "
            "produce a SHORT execution plan / skeleton of the SQL query.\n"
            "The skeleton should specify, in plain English with minimal SQL tokens:\n"
            "  - the target table(s)\n"
            "  - the relevant columns (SELECT / WHERE / GROUP BY / ORDER BY)\n"
            "  - any joins and their keys\n"
            "  - the type of operation (aggregation, filter, top-k, etc.)\n"
            "Do NOT write the final SQL. Do NOT use SELECT, FROM, WHERE as code. "
            "Be terse (3-8 lines).\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Skeleton:"
        )
        skeleton = self.llm(
            skeleton_prompt,
            system="You produce concise, schema-grounded query plans.",
            temperature=0.0,
            n=1,
        ).strip()
        if not skeleton:
            skeleton = "No skeleton produced; default to direct translation."

        # ---- Stage 2: expand the skeleton into final executable SQL ----
        sql_prompt = (
            "You are a Text-to-SQL generator.\n"
            "You are given a database schema, a natural language question, "
            "and a previously drafted query skeleton / plan.\n"
            "Your job: emit ONE valid SQL query that answers the question, "
            "strictly using the provided schema.\n"
            "Rules:\n"
            "  - Output ONLY the SQL (no prose, no markdown fences).\n"
            "  - Follow the skeleton faithfully, but you may add minor details "
            "(aliases, exact function names, NULL handling) needed for valid SQL.\n"
            "  - Use only tables/columns present in the schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Skeleton plan:\n{skeleton}\n\n"
            "Final SQL:"
        )
        raw = self.llm(
            sql_prompt,
            system="You translate questions + query plans into precise SQL.",
            temperature=0.0,
            n=1,
        )
        sql = bridge.extract_sql(raw)

        # Light self-check / single repair pass using execution feedback,
        # implemented as a structural follow-up stage rather than a true repair loop.
        if sql and self.execute(sql).get("ok"):
            return sql

        repair_prompt = (
            "Re-emit a single corrected SQL query.\n"
            "The previous attempt failed to execute or was empty. "
            "Given the schema, the question, and the skeleton plan, "
            "produce a valid SQL query that will execute successfully.\n"
            "Output ONLY the SQL.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Skeleton plan:\n{skeleton}\n\n"
            f"Previous attempt (possibly invalid):\n{sql}\n\n"
            "Corrected SQL:"
        )
        raw2 = self.llm(
            repair_prompt,
            system="You fix SQL to be syntactically and semantically valid.",
            temperature=0.0,
            n=1,
        )
        sql2 = bridge.extract_sql(raw2)
        if sql2:
            return sql2
        return sql or ""