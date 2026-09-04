"""A harness that uses multi-candidate generation and execution-guided self-repair for Text-to-SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: generate multiple candidate SQL queries using diverse prompts.
        candidates = self._generate_candidates(question, num_candidates=3)
        best_sql = candidates[0] if candidates else ""
        first_ok_empty = None
        errors = []

        # Stage 2: execute each candidate; prefer a successful query with non-empty rows.
        for sql in candidates:
            if not sql:
                continue
            result = self._safe_execute(sql)
            if result is None:
                errors.append("Execution raised an exception")
                continue
            if result.get("ok"):
                if result.get("rows"):
                    return sql
                if first_ok_empty is None:
                    first_ok_empty = sql
            else:
                errors.append(result.get("error", "Unknown error"))

        # If any syntactically valid but empty query executed, return it as a safe fallback.
        if first_ok_empty:
            return first_ok_empty

        # If no candidate was generated, produce a single zero-shot candidate.
        if not best_sql:
            best_sql = self._generate_single(question)

        # Stage 3: execution-guided repair loop.
        last_error = errors[0] if errors else "Unknown error"
        for _ in range(3):
            if not best_sql:
                break
            repaired = self._repair(question, best_sql, last_error)
            if not repaired:
                break
            best_sql = repaired
            result = self._safe_execute(best_sql)
            if result is None:
                last_error = "Execution raised an exception"
                continue
            if result.get("ok"):
                return best_sql
            last_error = result.get("error", "Unknown error")

        # Stage 4: final fallback with a simpler prompt to avoid complex SQL errors.
        fallback_sql = self._generate_single(question, simple=True)
        if fallback_sql:
            result = self._safe_execute(fallback_sql)
            if result is not None and result.get("ok"):
                return fallback_sql
            if result is not None:
                return fallback_sql

        return best_sql or fallback_sql or "SELECT 1"

    def _safe_execute(self, sql):
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _call_llm(self, prompt, system="", temperature=0.0):
        try:
            out = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            # Fall back if a custom base class does not accept all keyword arguments.
            out = self.llm(prompt)
        if isinstance(out, list):
            return out[0] if out else ""
        return out or ""

    def _extract_sql(self, text):
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
            return sql.strip() if sql else ""
        except Exception:
            return ""

    def _generate_candidates(self, question, num_candidates=3):
        prompts = [
            self._build_initial_prompt(question, 0),
            self._build_initial_prompt(question, 1),
            self._build_initial_prompt(question, 2),
        ]
        candidates = []
        for prompt in prompts[:num_candidates]:
            raw = self._call_llm(
                prompt,
                system="You are an expert SQL writer.",
                temperature=0.2,
            )
            sql = self._extract_sql(raw)
            if sql:
                candidates.append(sql)

        # Remove duplicates while preserving order.
        seen = set()
        unique = []
        for sql in candidates:
            if sql not in seen:
                seen.add(sql)
                unique.append(sql)
        return unique

    def _generate_single(self, question, simple=False):
        prompt = (
            self._build_simple_prompt(question)
            if simple
            else self._build_initial_prompt(question, 0)
        )
        raw = self._call_llm(
            prompt,
            system="You are a careful SQL expert.",
            temperature=0.0,
        )
        return self._extract_sql(raw)

    def _repair(self, question, previous_sql, error):
        prompt = self._build_repair_prompt(question, previous_sql, error)
        raw = self._call_llm(
            prompt,
            system="You fix SQL errors.",
            temperature=0.0,
        )
        return self._extract_sql(raw)

    def _build_initial_prompt(self, question, style):
        schema = self.schema or "No schema provided."
        if style == 0:
            instruction = "Write a single SQL query that answers the question. Return only SQL."
        elif style == 1:
            instruction = (
                "Think about the tables and columns needed, then write a single SQL query. "
                "Return only SQL."
            )
        else:
            instruction = "Write a compact SQL query using the schema. Return only SQL."

        return f"{instruction}\n\nDatabase schema:\n{schema}\n\nQuestion: {question}\nSQL:"

    def _build_repair_prompt(self, question, previous_sql, error):
        schema = self.schema or "No schema provided."
        return (
            f"The following SQL query failed. Fix the SQL and return only the corrected SQL.\n\n"
            f"Database schema:\n{schema}\n\nQuestion: {question}\n\n"
            f"Previous SQL:\n{previous_sql}\nError: {error}\nCorrected SQL:"
        )

    def _build_simple_prompt(self, question):
        schema = self.schema or "No schema provided."
        return (
            f"Write a very simple SQL query that answers the question. "
            f"Use basic SELECT, FROM, WHERE, and avoid complex constructs. Return only SQL.\n\n"
            f"Database schema:\n{schema}\n\nQuestion: {question}\nSQL:"
        )