"""Repair-based harness: execute SQL, feed errors back to LLM for iterative regeneration up to N rounds."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G6(SQLHarness):
    MAX_REPAIRS = 4

    def _ask(self, prompt, system=""):
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        return out if isinstance(out, str) else (out[0] if out else "")

    def _generate_initial(self, question):
        system = "You are a precise Text-to-SQL generator. Output only a single SQL statement, no prose."
        user = (
            "Schema:\n" + self.schema + "\n\n"
            "Question: " + question.strip() + "\n\n"
            "Write a single SQLite-compatible SQL query that answers the question.\n"
            "Wrap the final query in