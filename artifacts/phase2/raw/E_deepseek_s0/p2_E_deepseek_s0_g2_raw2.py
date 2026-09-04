from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        candidate_specs = [
            ("conservative", "write a simple and direct SQL SELECT statement"),
            ("optimized", "write an efficient SQL SELECT statement, using joins or subqueries only where they help"),
            ("robust", "write a SQL SELECT statement that handles possible edge cases gracefully"),
        ]

        candidates = []
        for style, instruction in candidate_specs:
            prompt = self._candidate_prompt(question, schema, style, instruction)
            raw = self._generate(
                prompt,
                system="You are an expert text-to-SQL assistant. Return only SQL.",
                temperature=0.4,
            )
            candidates.append(bridge.extract_sql(raw))

        results = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "rows": [], "error": str(exc)}
            results.append(result)

        entries = []
        for sql, result in zip(candidates, results):
            ok = bool(result.get("ok"))
            rows = result.get("rows", [])
            row_count = len(rows) if isinstance(rows, list) else 0
            error = "" if ok else str(result.get("error", "unknown execution error"))
            entries.append(
                {
                    "sql": sql,
                    "ok": ok,
                    "error": error,
                    "row_count": row_count,
                }
            )

        # Canonical ordering so the final prompt is invariant to candidate sample order.
        entries.sort(key=lambda e: e["sql"])

        if all(not e["ok"] for e in entries):
            prompt = self._repair_prompt(question, schema, entries)
            system = "You are an expert text-to-SQL repair assistant. Return only SQL."
            raw = self._generate(prompt, system=system, temperature=0.0)
            return bridge.extract_sql(raw)

        prompt = self._selection_prompt(question, schema, entries)
        system = "You are an expert text-to-SQL selection assistant. Return only SQL."
        raw = self._generate(prompt, system=system, temperature=0.0)
        return bridge.extract_sql(raw)

    def _generate(self, prompt: str, system: str, temperature: float) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            return out[0]
        return out

    def _candidate_prompt(self, question: str, schema: str, style: str, instruction: str) -> str:
        return (
            "Database schema:\n"
            + schema
            + "\n\n"
            + "Question: "
            + question
            + "\n\n"
            + "Task: "
            + instruction
            + " Style: "
            + style
            + ". Return a single SQL SELECT statement without any explanation."
        )

    def _format_entries(self, entries):
        lines = []
        for idx, e in enumerate(entries, 1):
            status = "OK" if e["ok"] else f"ERROR: {e['error']}"
            lines.append(
                f"Candidate {idx}:\nSQL: {e['sql']}\nExecution: {status}; rows returned: {e['row_count']}"
            )
        return "\n".join(lines)

    def _selection_prompt(self, question: str, schema: str, entries) -> str:
        return (
            "Database schema:\n"
            + schema
            + "\n\n"
            + "Question: "
            + question
            + "\n\n"
            + "Below are candidate SQL queries and their execution results.\n\n"
            + self._format_entries(entries)
            + "\n\n"
            + "Choose the best SQL query for the question. Prefer queries that executed successfully and returned a non-empty result set, but do not change a correct query merely to add rows. "
            + "If all candidates are unsuitable, write a corrected SQL. Return only the final SQL SELECT statement without any explanation."
        )

    def _repair_prompt(self, question: str, schema: str, entries) -> str:
        lines = []
        for idx, e in enumerate(entries, 1):
            lines.append(f"Failed candidate {idx}:\nSQL: {e['sql']}\nError: {e['error']}")
        failure_text = "\n".join(lines)
        return (
            "Database schema:\n"
            + schema
            + "\n\n"
            + "Question: "
            + question
            + "\n\n"
            + "All candidate SQL queries failed to execute. Here are the failures:\n\n"
            + failure_text
            + "\n\n"
            + "Write a corrected SQL SELECT statement that answers the question and executes successfully. Return only the final SQL SELECT statement without any explanation."
        )