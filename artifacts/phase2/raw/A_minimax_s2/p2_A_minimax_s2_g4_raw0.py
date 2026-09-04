"""Two-stage Text-to-SQL: generate schema-grounded sketch, then expand to executable SQL with repair fallback."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # ---- Stage 1: extract a compact "sketch": likely tables/columns/conditions, no SELECT/UPDATE body ----
        sketch_system = (
            "You analyze a natural language question against a SQL schema and produce a concise JSON "
            "sketch identifying relevant tables, columns, joins, filters, aggregations, and ordering. "
            "Do NOT write SQL. Output only valid JSON with keys: tables (list), columns (list), "
            "joins (list of {left,right,on}), filters (list of {column,op,value}), group_by (list), "
            "order_by (list of {column,direction}), limit (int or null)."
        )
        sketch_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Produce the JSON sketch now."
        )
        sketch_raw = self.llm(sketch_prompt, system=sketch_system, temperature=0.0, n=1)
        sketch_text = sketch_raw if isinstance(sketch_raw, str) else str(sketch_raw)

        # ---- Stage 2a: expand the sketch into a concrete SQL query (greedy) ----
        expand_system = (
            "You are a Text-to-SQL expert. Given a schema, a natural language question, and a JSON "
            "sketch of intent, write ONE valid SQL query that answers the question. "
            "Use only tables/columns that appear in the schema. "
            "Return ONLY the SQL statement (no prose, no markdown fences)."
        )
        expand_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Sketch:\n{sketch_text}\n\n"
            "SQL:"
        )
        first_sql = self.llm(expand_prompt, system=expand_system, temperature=0.0, n=1)
        first_sql = bridge.extract_sql(first_sql if isinstance(first_sql, str) else str(first_sql))
        first_sql = (first_sql or "").strip().rstrip(";").strip()

        # Validate by execution; if it works, keep it.
        if first_sql:
            probe = self.execute(first_sql)
            if probe.get("ok"):
                return first_sql

        # ---- Stage 2b (repair): feed execution feedback back for a single targeted fix ----
        err = ""
        if first_sql:
            res = self.execute(first_sql)
            err = (res.get("error") or "") if isinstance(res, dict) else ""
        if not err and not first_sql:
            err = "Empty or unparseable SQL produced in stage 2a."

        repair_system = (
            "You are a Text-to-SQL repair expert. You receive a schema, a question, a previous SQL "
            "attempt, and an execution error. Produce a corrected SQL query that fixes the error "
            "while still answering the question. Use only schema-valid identifiers. "
            "Return ONLY the corrected SQL statement (no prose, no markdown fences)."
        )
        repair_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{first_sql}\n\n"
            f"Execution error:\n{err}\n\n"
            "Corrected SQL:"
        )
        repaired = self.llm(repair_prompt, system=repair_system, temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repaired if isinstance(repaired, str) else str(repaired))
        repaired_sql = (repaired_sql or "").strip().rstrip(";").strip()

        # Final validation; fall back to the first attempt if repair is empty/broken.
        if repaired_sql:
            res2 = self.execute(repaired_sql)
            if res2.get("ok"):
                return repaired_sql
            return repaired_sql

        return first_sql