"""Two-stage Text-to-SQL: first stage produces a focused schema subset, second stage generates SQL conditioned on it."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G2(SQLHarness):
    """Two-stage pipeline.

    Stage 1: an LLM call inspects the natural-language question against the full
    database schema and emits a compact "focused schema" -- only the tables and
    columns that look relevant, with a brief rationale. This reduces noise the
    weak solver has to attend to.

    Stage 2: a second LLM call receives the original question, the focused
    schema, and a few worked examples, and emits the final SQL. The SQL is
    extracted with the shared bridge helper and validated with a cheap syntactic
    check (a SELECT/keyword sanity probe); if extraction fails we fall back to a
    plain single-shot generation so the harness always returns *something*.
    """

    _FALLBACK_SYSTEM = (
        "You are a careful Text-to-SQL expert. Given a question and a database "
        "schema, output exactly one SQL statement and nothing else."
    )

    _STAGE1_SYSTEM = (
        "You analyze a natural-language question and a database schema, and "
        "output a JSON object with two keys: 'tables' (a list of fully-qualified "
        "table names that are likely needed) and 'columns' (a list of "
        "fully-qualified column names that are likely needed). Only include "
        "items that are present in the schema. Output JSON only, no prose."
    )

    _STAGE2_SYSTEM = (
        "You are a careful Text-to-SQL expert. You are given a natural-language "
        "question, a focused subset of the database schema, and a few example "
        "question/SQL pairs. Produce exactly one SQL statement that answers the "
        "question against the schema. Output the SQL and nothing else -- no "
        "fences, no commentary."
    )

    _FEW_SHOTS = (
        "Example 1:\n"
        "Question: How many students are enrolled in course CS101?\n"
        "Schema excerpt: students(sid, name), enrollments(sid, course_id), "
        "courses(course_id, title)\n"
        "SQL: SELECT COUNT(*) FROM enrollments e JOIN courses c "
        "ON e.course_id = c.course_id WHERE c.title = 'CS101';\n\n"
        "Example 2:\n"
        "Question: List the names of employees in the Sales department.\n"
        "Schema excerpt: employees(eid, name, dept_id), departments(dept_id, name)\n"
        "SQL: SELECT e.name FROM employees e JOIN departments d "
        "ON e.dept_id = d.dept_id WHERE d.name = 'Sales';\n\n"
        "Example 3:\n"
        "Question: What is the average salary of full-time workers?\n"
        "Schema excerpt: workers(wid, status, salary)\n"
        "SQL: SELECT AVG(salary) FROM workers WHERE status = 'full-time';\n"
    )

    def _focus_schema(self, question: str) -> str:
        """Stage 1: ask the LLM to pick the relevant tables/columns, then
        reconstruct a smaller schema string from the original self.schema."""
        import json
        import re

        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Output JSON describing which tables and columns are required."
        )
        raw = self.llm(prompt, system=self._STAGE1_SYSTEM, temperature=0.0, n=1)

        keep_tables: set[str] = set()
        keep_columns: set[str] = set()
        try:
            m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if m:
                obj = json.loads(m.group(0))
                for t in obj.get("tables", []) or []:
                    if isinstance(t, str):
                        keep_tables.add(t.strip().lower())
                for c in obj.get("columns", []) or []:
                    if isinstance(c, str):
                        keep_columns.add(c.strip().lower())
        except Exception:
            keep_tables = set()
            keep_columns = set()

        # If parsing failed or the model returned nothing useful, keep the full
        # schema so stage 2 still has something to work with.
        if not keep_tables and not keep_columns:
            return self.schema

        # Re-emit the original schema, but keep only lines that mention a
        # kept table or column. This is conservative: we never invent schema
        # content, we only filter what the model flagged.
        keep_lines: list[str] = []
        schema_lines = self.schema.splitlines()
        for line in schema_lines:
            low = line.lower()
            if any(t in low for t in keep_tables) or any(c in low for c in keep_columns):
                keep_lines.append(line)

        if not keep_lines:
            return self.schema
        return "\n".join(keep_lines)

    @staticmethod
    def _looks_like_sql(text: str) -> bool:
        """Cheap syntactic sanity check: starts with a verb and is non-empty."""
        if not text:
            return False
        head = text.lstrip().split(None, 1)
        if not head:
            return False
        verb = head[0].upper().rstrip(";,")
        return verb in {"SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE"}

    def solve(self, question: str) -> str:
        # ---- Stage 1: produce a focused schema ----
        focused = self._focus_schema(question)

        # ---- Stage 2: generate SQL conditioned on the focused schema ----
        stage2_prompt = (
            f"{self._FEW_SHOTS}\n"
            f"Database schema (focused):\n{focused}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw2 = self.llm(stage2_prompt, system=self._STAGE2_SYSTEM, temperature=0.0, n=1)
        sql2 = bridge.extract_sql(raw2) or raw2.strip()

        if self._looks_like_sql(sql2):
            return sql2

        # ---- Fallback: plain single-shot generation ----
        plain_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw1 = self.llm(plain_prompt, system=self._FALLBACK_SYSTEM, temperature=0.0, n=1)
        sql1 = bridge.extract_sql(raw1) or raw1.strip()
        return sql1