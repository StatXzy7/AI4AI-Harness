"""Generate SQL, execute it, and repair failures by feeding SQLite error messages back up to two times."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQLite query generator. Return only a single SQL query."

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that answers the question. Return only the SQL query, no explanation."
        )

        resp = self.llm(prompt, system=system, temperature=0.0, n=1)
        if not isinstance(resp, str):
            if isinstance(resp, (list, tuple)):
                resp = "\n".join(resp)
            else:
                resp = str(resp)
        sql = bridge.extract_sql(resp) or ""

        result = self.execute(sql)
        if result.get("ok", False):
            return sql

        for _ in range(2):
            error = result.get("error", "Unknown SQLite error")
            repair_prompt = (
                f"The SQL query below failed with the following SQLite error.\n\n"
                f"SQL:\n{sql}\n\n"
                f"Error:\n{error}\n\n"
                f"Original question:\n{question}\n\n"
                f"Database schema:\n{self.schema}\n\n"
                f"Please fix the SQL query. Return only the corrected SQL query, no explanation."
            )
            resp = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            if not isinstance(resp, str):
                if isinstance(resp, (list, tuple)):
                    resp = "\n".join(resp)
                else:
                    resp = str(resp)
            new_sql = bridge.extract_sql(resp)
            if new_sql:
                sql = new_sql
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

        return sql