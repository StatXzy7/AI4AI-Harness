from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        # Phase 1: sample three candidate SQL queries.
        candidates = []
        for i in range(3):
            prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Write a SQL query that answers the question. Output only SQL. Candidate {i + 1}."
            )
            raw = self._llm_str(
                prompt,
                system="You are an expert SQL writer. Output only SQL.",
                temperature=0.1 + 0.2 * i,
            )
            sql = bridge.extract_sql(raw) or raw
            candidates.append(sql.strip() or "SELECT 1")

        # Sort candidates before execution so execution order is independent of sampling order.
        candidates.sort()

        # Phase 2: execute every sampled candidate and record observations.
        observations = []
        for sql in candidates:
            exec_result = self.execute(sql)
            observations.append({"sql": sql, "exec": exec_result})

        # Sort observations again by SQL text to make final prompt invariant to sample order.
        observations.sort(key=lambda item: item["sql"])

        successful = [item for item in observations if item["exec"].get("ok")]
        failed = [item for item in observations if not item["exec"].get("ok")]

        # Phase 3: branch on whether any candidate executed cleanly.
        if successful:
            final_prompt = self._make_success_prompt(question, successful)
            final_system = "You are an expert SQL writer. Choose or improve the SQL. Output only SQL."
        else:
            final_prompt = self._make_repair_prompt(question, failed)
            final_system = "You are an expert SQL writer. Fix the SQL. Output only SQL."

        raw_final = self._llm_str(final_prompt, system=final_system, temperature=0.0)
        final_sql = bridge.extract_sql(raw_final) or raw_final
        return final_sql.strip()

    def _llm_str(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        result = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else ""
        return str(result)

    def _make_success_prompt(self, question: str, items: list) -> str:
        lines = [
            "Database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "Here are candidate SQL queries that executed successfully:",
        ]
        for item in items:
            rows = item["exec"].get("rows") or []
            lines.append(f"- SQL: {item['sql']}")
            lines.append(f"  Row count: {len(rows)}")
            lines.append(f"  Rows preview: {self._preview_rows(rows)}")
        lines.append("")
        lines.append("Return the best SQL query for the question. Output only SQL.")
        return "\n".join(lines)

    def _make_repair_prompt(self, question: str, items: list) -> str:
        lines = [
            "Database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "Here are candidate SQL queries that failed to execute:",
        ]
        for item in items:
            error = item["exec"].get("error", "Unknown error")
            lines.append(f"- SQL: {item['sql']}")
            lines.append(f"  Error: {error}")
        lines.append("")
        lines.append("Return a corrected SQL query for the question. Output only SQL.")
        return "\n".join(lines)

    @staticmethod
    def _preview_rows(rows: list, limit: int = 3) -> str:
        if not rows:
            return "[]"
        return repr(rows[:limit])