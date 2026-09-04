"""Generate multiple SQL candidates with diverse prompts, execute them, and vote for the best executable sample."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a precise text-to-SQL generator. Output only one valid SQL query."

        prompts = [
            self._generation_prompt(question, "direct"),
            self._generation_prompt(question, "reasoned"),
            self._generation_prompt(question, "conservative"),
        ]

        candidates = []
        for idx, prompt in enumerate(prompts):
            raw = self._llm_text(prompt, system)
            sql = self._extract_sql(raw)
            if sql:
                candidates.append(
                    {
                        "sql": sql,
                        "source": idx,
                        "freq": 1,
                        "ok": False,
                        "row_count": 0,
                        "error": "",
                        "score": 0,
                    }
                )

        if not candidates:
            raw = self._llm_text(self._generation_prompt(question, "direct"), system)
            return self._extract_sql(raw)

        unique = self._dedupe(candidates)
        if not unique:
            return candidates[0]["sql"] if candidates else ""

        for cand in unique:
            result = self._execute_sql(cand["sql"])
            cand.update(result)
            cand["score"] = self._score_candidate(cand)

        executable = [c for c in unique if c["ok"]]

        if executable:
            if len(executable) == 1:
                return executable[0]["sql"]

            chosen = self._select_best(question, executable)
            if chosen:
                return chosen

            return max(executable, key=lambda c: c["score"])["sql"]

        return max(unique, key=lambda c: c["score"])["sql"]

    def _llm_text(self, prompt: str, system: str = "") -> str:
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(out, bytes):
            return out.decode("utf-8", "ignore")

        if isinstance(out, (list, tuple)):
            out = out[0] if len(out) else ""

        if isinstance(out, dict):
            for key in ("text", "completion", "content", "output", "sql"):
                val = out.get(key)
                if isinstance(val, str):
                    return val
            out = str(out)

        if hasattr(out, "text"):
            text = getattr(out, "text")
            if isinstance(text, str):
                return text

        return "" if out is None else str(out)

    def _generation_prompt(self, question: str, style: str) -> str:
        schema = getattr(self, "schema", "") or ""

        if style == "reasoned":
            instruction = (
                "Briefly identify the needed tables, columns, joins, and filters, "
                "then output the final SQL in a single