"""Two-stage harness: first LLM drafts an outline of intent + sketch SQL, second LLM refines it into a final executable query."""
# MECHANISM: twostage    -- an earlier LLM stage produces an artifact a later stage consumes
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G2(SQLHarness):
    def _generate(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> list:
        """Helper to call the LLM and return a list of responses."""
        return self.llm(prompt, system=system, temperature=temperature, n=n)

    def solve(self, question: str) -> str:
        # ---------------- Stage 1: Intent + Sketch ----------------
        # The first stage analyzes the schema and question, producing:
        #   1. A natural-language intent statement (what the query must compute).
        #   2. A rough SQL sketch noting relevant tables/columns/JOINs but not full syntax.
        stage1_system = (
            "You are a SQL planning expert. Given a database schema and a natural language "
            "question, you produce a JSON object with two fields: 'intent' (a precise "
            "description of what the SQL must compute, including any filters, aggregations, "
            "and ordering) and 'sketch' (a rough SQL outline listing the FROM clause, "
            "key JOINs, WHERE conditions as comments, and the expected output columns). "
            "Do NOT produce final executable SQL. Output ONLY valid JSON."
        )
        stage1_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Respond with JSON containing 'intent' and 'sketch'."
        )
        stage1_responses = self._generate(stage1_prompt, system=stage1_system, temperature=0.0, n=1)
        artifact = stage1_responses[0] if stage1_responses else ""

        # Best-effort extraction of the JSON-like artifact. We don't fail hard here:
        # if parsing yields something thin we still pass the raw artifact forward,
        # because the second stage LLM can reason over loose text.
        intent_text = artifact
        sketch_text = ""
        try:
            # Tolerant JSON extraction: find first {...} block.
            start = artifact.find("{")
            end = artifact.rfind("}")
            if start != -1 and end != -1 and end > start:
                import json as _json
                parsed = _json.loads(artifact[start:end + 1])
                intent_text = str(parsed.get("intent", artifact))
                sketch_text = str(parsed.get("sketch", ""))
        except Exception:
            # Keep raw artifact as intent_text; sketch stays empty.
            pass

        # ---------------- Stage 2: Refinement into Final SQL ----------------
        # The second stage consumes both the original schema+question AND the stage-1
        # artifact, producing an executable SQL string.
        stage2_system = (
            "You are a SQL synthesis expert. You receive a database schema, a natural "
            "language question, and a planning artifact (intent + sketch) from an earlier "
            "planning step. Produce exactly ONE final SQL query that faithfully realizes "
            "the intent. Use the dialect implied by the schema. Output ONLY the SQL "
            "statement, no prose, no Markdown fences."
        )
        stage2_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Planning artifact:\n"
            f"  Intent: {intent_text}\n"
            f"  Sketch:\n{sketch_text}\n\n"
            "Now produce the final SQL."
        )
        stage2_responses = self._generate(stage2_prompt, system=stage2_system, temperature=0.0, n=1)
        final_text = stage2_responses[0] if stage2_responses else ""

        final_sql = bridge.extract_sql(final_text)

        # Sanity: if extraction returned empty, fall back to the stage-1 sketch (which
        # may already contain valid SQL syntax) or to the raw stage-2 response.
        if not final_sql.strip():
            if sketch_text.strip():
                final_sql = bridge.extract_sql(sketch_text) or sketch_text.strip()
            else:
                final_sql = final_text.strip()

        return final_sql