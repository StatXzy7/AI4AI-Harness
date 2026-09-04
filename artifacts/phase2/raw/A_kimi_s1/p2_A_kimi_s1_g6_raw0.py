"""Bounded self-repair Text-to-SQL harness: generate SQL, execute it, and feed execution errors back to the frozen LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G6(SQLHarness):
    """Generate -> execute -> feed the database error back -> regenerate (bounded).

    Improvement over a single greedy call: every candidate query is actually
    executed against the database. On failure, the failing SQL together with
    the real database error is appended to the prompt and the frozen solver is
    asked to diagnose and correct it. Repairs use a slowly rising temperature
    so the model can escape the failure mode that the deterministic first
    attempt fell into. The loop is bounded and always returns the best-effort
    final query if no attempt executes cleanly.
    """

    MAX_ATTEMPTS = 4       # 1 initial greedy attempt + up to 3 repairs
    ERROR_HISTORY = 3      # how many recent failures to show the model
    ERROR_CHAR_LIMIT = 600 # keep fed-back error messages bounded

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, you output exactly one valid SQL query "
        "that answers the question. Output only the SQL query: no markdown "
        "fences, no commentary, no explanation."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question."
        )

        failures = []   # list of (sql, error) from attempts rejected by the database
        last_sql = ""   # best-effort fallback if nothing ever executes

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(base_prompt, failures)
            # Deterministic first try; add diversity only for repairs.
            temperature = 0.0 if attempt == 0 else min(0.2 + 0.2 * attempt, 0.8)

            raw = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=temperature,
                n=1,
            )
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            candidate = bridge.extract_sql(str(raw)).strip() or str(raw).strip()

            if not candidate:
                failures.append(("<empty output>", "model returned no SQL"))
                continue

            last_sql = candidate
            outcome = self.execute(candidate)
            if outcome.get("ok"):
                return candidate

            error = str(outcome.get("error") or "unknown execution error")
            failures.append((candidate, error[: self.ERROR_CHAR_LIMIT]))

        return last_sql

    def _build_prompt(self, base_prompt: str, failures: list) -> str:
        """Initial prompt, or a repair prompt carrying recent execution feedback."""
        if not failures:
            return base_prompt

        blocks = []
        for i, (bad_sql, error) in enumerate(failures[-self.ERROR_HISTORY:], start=1):
            blocks.append(f"Failed attempt {i}:\n{bad_sql}\nDatabase error: {error}")
        history = "\n\n".join(blocks)

        return (
            f"{base_prompt}\n\n"
            "The following previously generated queries failed when executed "
            "against the database. Diagnose each error (wrong table or column "
            "names, bad joins, invalid syntax, type mismatches, ambiguous "
            "references) and write a corrected query that fixes the problem "
            "while still answering the original question. Do not repeat a "
            "previous failing query verbatim.\n\n"
            f"{history}\n\n"
            "Return only the corrected SQL query."
        )