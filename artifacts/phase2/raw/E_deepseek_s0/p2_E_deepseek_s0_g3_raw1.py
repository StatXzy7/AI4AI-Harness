"""Uses execution feedback and multiple candidate generation to iteratively produce a valid SQL query for a given question."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        generated = []

        # First try several independent generations at different temperatures.
        for temp in (0.0, 0.3, 0.6):
            prompt = self._initial_prompt(question, schema)
            text = self.llm(prompt, temperature=temp)
            sql = self._extract(text)

            if not sql or sql in generated:
                continue

            generated.append(sql)
            result = self._execute_safely(sql)
            if result.get("ok"):
                return sql

        candidate = generated[0] if generated else ""
        last_error = "No SQL generated"

        # Repair loop using execution feedback.
        for _ in range(3):
            if not candidate:
                prompt = self._initial_prompt(question, schema)
                text = self.llm(prompt, temperature=0.0)
                candidate = self._extract(text)
                if not candidate:
                    break

            result = self._execute_safely(candidate)
            if result.get("ok"):
                return candidate

            last_error = result.get("error") or "Unknown error"

            repair_prompt = self._repair_prompt(question, schema, candidate, last_error)
            repair_text = self.llm(repair_prompt, temperature=0.2)
            new_candidate = self._extract(repair_text)

            if not new_candidate or new_candidate == candidate:
                alternative_prompt = self._alternative_prompt(
                    question, schema, candidate, last_error
                )
                alternative_text = self.llm(alternative_prompt, temperature=0.4)
                new_candidate = self._extract(alternative_text)

            candidate = new_candidate

        if candidate and self._execute_safely(candidate).get("ok"):
            return candidate

        return candidate or "SELECT NULL LIMIT 0"

    def _initial_prompt(self, question: str, schema: str) -> str:
        return f"""You are an expert SQL writer. Given the following database schema and natural language question, write a single SQL query that answers the question.

Schema:
{schema}

Question:
{question}

Return only the SQL query, without any explanation or markdown fences."""

    def _repair_prompt(self, question: str, schema: str, previous: str, error: str) -> str:
        return f"""You are an expert SQL writer. The following SQL query was generated for the given question, but it failed with an error.

Schema:
{schema}

Question:
{question}

Previous SQL:
{previous}

Error:
{error}

Write a corrected SQL query that answers the question. Return only the SQL query, without any explanation or markdown fences."""

    def _alternative_prompt(self, question: str, schema: str, previous: str, error: str) -> str:
        return f"""You are an expert SQL writer. The following SQL query was generated for the given question, but it failed.

Schema:
{schema}

Question:
{question}

Previous SQL:
{previous}

Error:
{error}

Generate a different SQL query that answers the question. Avoid the same mistake. Return only the SQL query, without any explanation or markdown fences."""

    def _execute_safely(self, sql: str):
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _extract(self, text: str) -> str:
        if not text:
            return ""
        try:
            return (bridge.extract_sql(text) or "").strip()
        except Exception:
            return text.strip()