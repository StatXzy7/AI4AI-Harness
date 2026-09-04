"""Generate multiple SQL candidates and select the best executable query."""
# MECHANISM: vote
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        candidates = self._generate_candidates(question)

        if not candidates:
            return self._fallback(question)

        scored = self._score_candidates(candidates)
        executable = [item[2] for item in scored if item[3]]

        if executable:
            if len(executable) == 1:
                return executable[0]

            chosen = self._judge_best(question, executable)
            if chosen in executable:
                return chosen

            return scored[0][2]

        chosen = self._judge_best(question, candidates)
        if chosen in candidates:
            return chosen

        return scored[0][2]

    def _generate_candidates(self, question: str):
        schema = getattr(self, "schema", "") or ""
        base_prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Output only SQL."
        )

        variants = [
            (
                "Return the most direct single SQL query.",
                "You are a precise SQL engine. Output only one SQL query.",
                0.0,
            ),
            (
                "Return a valid single SQL query using explicit columns, correct filters, and appropriate aggregation.",
                "You are an expert data analyst. Write exactly one SQL query and no explanation.",
                0.2,
            ),
            (
                "Return a conservative single SQL query in standard SQL; avoid unnecessary columns or clauses.",
                "You are a careful database administrator. Reply with only one SQL query.",
                0.4,
            ),
        ]

        candidates = []
        seen = set()

        for instruction, system, temperature in variants:
            prompt = base_prompt + "\n\n" + instruction
            try:
                response = self.llm(
                    prompt,
                    system=system,
                    temperature=temperature,
                    n=1,
                )
            except Exception:
                continue

            sql = self._extract_sql(response)
            if not sql:
                continue

            key = self._normalize_sql(sql)
            if key and key not in seen:
                seen.add(key)
                candidates.append(sql)

        return candidates

    def _score_candidates(self, candidates):
        scored = []

        for idx, sql in enumerate(candidates):
            score = 0.0
            ok = False

            try:
                result = self.execute(sql)
                if isinstance(result, dict):
                    ok = bool(result.get("ok"))
                else:
                    ok = bool(result)
            except Exception:
                ok = False

            if ok:
                score += 100.0
                score -= len(sql) / 2000.0
            else:
                score -= 100.0
                score -= len(sql) / 5000.0

            scored.append((score, idx, sql, ok))

        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return scored

    def _judge_best(self, question: str, candidates):
        if not candidates:
            return None

        schema = getattr(self, "schema", "") or ""
        lines = [f"{i}: {sql}" for i, sql in enumerate(candidates)]

        prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Candidate SQL queries:\n"
            + "\n".join(lines)
            + "\n\n"
            "Select the single candidate that best answers the question. "
            "Respond with only the integer index."
        )

        try:
            response = self.llm(
                prompt,
                system="You are an impartial SQL judge. Output only an integer index.",
                temperature=0.0,
                n=1,
            )
        except Exception:
            return None

        text = self._coerce_text(response)
        match = re.search(r"\d+", text)
        if not match:
            return None

        try:
            idx = int(match.group(0))
        except Exception:
            return None

        if 0 <= idx < len(candidates):
            return candidates[idx]

        return None

    def _fallback(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Output only SQL."
        )

        try:
            response = self.llm(
                prompt,
                system="You are a precise SQL engine.",
                temperature=0.0,
                n=1,
            )
        except Exception:
            return ""

        return self._extract_sql(response)

    def _extract_sql(self, response) -> str:
        text = self._coerce_text(response)
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if not sql:
            sql = text.strip()

        sql = sql.strip()

        if sql.startswith("