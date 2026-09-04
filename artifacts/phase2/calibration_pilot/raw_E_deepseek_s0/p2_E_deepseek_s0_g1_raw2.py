from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        candidates = self._generate_initial_candidates(question)

        results = []
        for sql in candidates:
            try:
                res = self.execute(sql)
            except Exception as exc:
                res = {"ok": False, "rows": [], "error": str(exc)}

            ok = bool(res.get("ok", False))
            results.append({
                "sql": sql,
                "ok": ok,
                "rows": res.get("rows", []),
                "error": res.get("error", "")
            })

        successful = [r for r in results if r["ok"]]
        if successful:
            final_prompt = self._make_success_prompt(question, successful)
        else:
            final_prompt = self._make_failure_prompt(question, results)

        raw_final = self._generate(final_prompt, n=1)[0]
        final_sql = self._extract_sql(raw_final)
        if not final_sql:
            final_sql = raw_final.strip()
        return final_sql

    def _generate(self, prompt: str, system: str = "", n: int = 1):
        res = self.llm(prompt, system=system, temperature=0.0, n=n)
        if isinstance(res, str):
            return [res]
        if res is None:
            return [""]
        return list(res)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                return sql.strip()
        except Exception:
            pass
        return text.strip()

    def _generate_initial_candidates(self, question: str):
        base = f"Schema:\n{self.schema}\n\nQuestion: {question}"
        variants = [
            ("Write a SQL query that answers the question directly.", "You are a concise SQL expert."),
            ("Write an alternative SQL query that answers the question robustly and handles edge cases.", "You are a careful SQL expert."),
            ("Write a different SQL query that answers the question.", "You are a SQL specialist."),
            ("Write another valid SQL query that answers the question.", "You are an expert SQL writer."),
        ]

        candidates = []
        for instruction, system in variants:
            if len(candidates) >= 2:
                break
            prompt = f"{base}\n\n{instruction}\nOutput only SQL."
            raw = self._generate(prompt, system=system, n=1)[0]
            sql = self._extract_sql(raw)
            if not sql:
                sql = raw.strip()
            if sql and sql not in candidates:
                candidates.append(sql)

        # Defensive fallback to ensure at least two distinct execution paths.
        if not candidates:
            candidates.append("SELECT 1")
        while len(candidates) < 2:
            first = candidates[0].rstrip(";")
            wrapped = f"SELECT * FROM ({first}) AS fallback_query"
            if wrapped not in candidates:
                candidates.append(wrapped)
            else:
                candidates.append(first + " /* fallback */")

        return candidates

    def _format_rows(self, rows):
        if rows is None:
            return "[]"
        try:
            if isinstance(rows, list):
                return repr(rows[:10])
            return repr(rows)
        except Exception:
            return str(rows)

    def _make_success_prompt(self, question: str, successful):
        blocks = []
        for idx, r in enumerate(successful, 1):
            blocks.append(
                f"Candidate {idx}:\n{r['sql']}\nExecution result: OK\nRows: {self._format_rows(r['rows'])}"
            )
        return (
            f"Schema:\n{self.schema}\n\nQuestion: {question}\n\n"
            "The following candidate SQL queries executed successfully:\n\n"
            + "\n\n".join(blocks) +
            "\n\nWrite a final SQL query that best answers the question. Output only SQL."
        )

    def _make_failure_prompt(self, question: str, results):
        blocks = []
        for idx, r in enumerate(results, 1):
            error = r["error"] or "unknown error"
            blocks.append(
                f"Candidate {idx}:\n{r['sql']}\nExecution error: {error}"
            )
        return (
            f"Schema:\n{self.schema}\n\nQuestion: {question}\n\n"
            "All candidate SQL queries failed. Here are the failed queries and errors:\n\n"
            + "\n\n".join(blocks) +
            "\n\nWrite a corrected SQL query that answers the question. Output only SQL."
        )