"""Generates several SQL candidates and chooses one by execution-based voting."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        variants = [
            {
                "temperature": 0.0,
                "instruction": "Write the SQL query that answers the question. Output only SQL.",
            },
            {
                "temperature": 0.2,
                "instruction": "Identify the needed tables and filters mentally, then output only the final SQL query.",
            },
            {
                "temperature": 0.5,
                "instruction": "Produce the most likely correct SQL query for the question. Output only SQL.",
            },
        ]

        candidates = []
        for idx, variant in enumerate(variants):
            prompt = self._generation_prompt(question, variant["instruction"])
            raw = self._llm_text(prompt, self._system_prompt(), variant["temperature"])
            sql = self._clean_sql(self._extract_sql(raw))
            result = self._execute_candidate(sql)

            rows = result.get("rows") if isinstance(result, dict) else []
            if rows is None:
                rows = []
            if not isinstance(rows, list):
                try:
                    rows = list(rows)
                except Exception:
                    rows = []

            candidates.append(
                {
                    "idx": idx,
                    "sql": sql,
                    "raw": raw,
                    "ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
                    "error": str(result.get("error", "")) if isinstance(result, dict) else "",
                    "row_count": len(rows),
                    "signature": self._rows_signature(rows),
                }
            )

        return self._select_best(candidates)

    def _system_prompt(self) -> str:
        return "You are an expert text-to-SQL system. Return only a single executable SQL statement."

    def _generation_prompt(self, question: str, instruction: str) -> str:
        return (
            f"{instruction}\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"SQL:"
        )

    def _llm_text(self, prompt: str, system: str, temperature: float) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system=system, n=1)
            except Exception:
                return ""
        except Exception:
            return ""

        return self._coerce_text(response)

    def _coerce_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, (list, tuple)):
            if not response:
                return ""
            return self._coerce_text(response[0])

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "response", "output"):
                if key in response:
                    return self._coerce_text(response[key])
            return str(response)

        return str(response)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted:
            return str(extracted)

        return str(text)

    def _clean_sql(self, sql: str) -> str:
        if not sql:
            return ""

        sql = str(sql).strip()

        if sql.startswith("