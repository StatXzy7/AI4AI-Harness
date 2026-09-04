"""Two-stage control flow: an analyst LLM call first emits a structured schema-linking/plan artifact that a second synthesizer LLM call consumes to produce the final SQL."""

# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G4(SQLHarness):
    """Text-to-SQL harness with a two-stage pipeline.

    Stage 1 ("analyst"): a greedy LLM call links the question to the schema and
    emits a structured plan artifact (tables, columns, filters, aggregation,
    ordering, pitfalls, goal).  Stage 2 ("synthesizer"): a second greedy LLM
    call consumes that plan artifact and writes the final SQLite SELECT
    statement.  The stage-2 prompt depends on stage-1 output, so this is a real
    pipeline, not a single longer prompt.
    """

    MAX_PLAN_CHARS = 4000
    MAX_SYNTH_ATTEMPTS = 2

    ANALYST_SYSTEM = (
        "You are a meticulous data analyst. Given a database schema and a "
        "natural-language question, you produce a precise, structured plan for "
        "answering the question with SQL. You never write SQL yourself."
    )

    SYNTHESIZER_SYSTEM = (
        "You are an expert SQLite programmer. You turn an analysis plan plus a "
        "schema into exactly one correct SQLite SELECT statement. You output "
        "only SQL."
    )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _schema_text(self) -> str:
        return str(self.schema) if self.schema else ""

    def _generate(self, prompt: str, system: str) -> str:
        """One greedy LLM call, normalised to a plain string."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out).strip() if out is not None else ""

    # ------------------------------------------------------------------ #
    # stage 1: analyst -> plan artifact
    # ------------------------------------------------------------------ #
    def _analyst_prompt(self, question: str) -> str:
        return (
            "DATABASE SCHEMA:\n"
            f"{self._schema_text()}\n"
            "\n"
            f"QUESTION:\n{question}\n"
            "\n"
            "TASK: Analyse how this question must be answered against the "
            "schema. Do NOT write SQL. Reply using EXACTLY these seven header "
            "lines, each on its own line, in this order:\n"
            "TABLES: <tables needed, comma separated>\n"
            "COLUMNS: <columns needed as table.column, comma separated>\n"
            "FILTERS: <row-level conditions that must hold, or 'none'>\n"
            "AGGREGATION: <GROUP BY / COUNT / SUM / AVG / MIN / MAX steps, or "
            "'none'>\n"
            "ORDERING: <ORDER BY / top-N / LIMIT requirements, or 'none'>\n"
            "PITFALLS: <subtle traps such as DISTINCT vs duplicates, NULL "
            "handling, date formats, join fan-out, negated wording, or 'none'>\n"
            "GOAL: <one short sentence stating exactly what the result must "
            "contain>"
        )

    def _make_plan(self, question: str) -> str:
        """Stage 1: emit the structured plan artifact for stage 2 to consume."""
        plan = self._generate(self._analyst_prompt(question), self.ANALYST_SYSTEM)
        if len(plan) > self.MAX_PLAN_CHARS:
            # Truncate on a line boundary so the artifact stays well-formed.
            plan = plan[: self.MAX_PLAN_CHARS].rsplit("\n", 1)[0]
        if not plan:
            plan = (
                "TABLES: (analysis unavailable)\n"
                "COLUMNS: (analysis unavailable)\n"
                "GOAL: answer the question with one SQLite SELECT statement."
            )
        return plan

    # ------------------------------------------------------------------ #
    # stage 2: synthesizer consumes the plan artifact
    # ------------------------------------------------------------------ #
    def _synthesizer_prompt(self, question: str, plan: str, strict: bool) -> str:
        prompt = (
            "DATABASE SCHEMA:\n"
            f"{self._schema_text()}\n"
            "\n"
            f"QUESTION:\n{question}\n"
            "\n"
            "ANALYST PLAN (produced by an earlier analysis stage):\n"
            f"{plan}\n"
            "\n"
            "TASK: Using the analyst plan above, write ONE SQLite SELECT "
            "statement that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that exist in the schema.\n"
            "- Implement the FILTERS, AGGREGATION and ORDERING lines of the "
            "plan.\n"
            "- Heed the PITFALLS line (DISTINCT, NULL handling, date handling, "
            "join fan-out, negation) exactly where the plan calls for it.\n"
            "- Output the statement inside a