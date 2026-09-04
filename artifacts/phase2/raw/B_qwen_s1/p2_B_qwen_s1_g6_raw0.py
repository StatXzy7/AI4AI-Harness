"""Harness samples multiple SQL candidates and selects the best executable query."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are a precise Text-to-SQL engine. "
            "Return only one valid SQLite SQL SELECT statement."
        )

        base_prompt = self._candidate_prompt(question, "")
        variants = [
            (base_prompt, 0.0),
            (
                self._candidate_prompt(
                    question,
                    "Prefer the simplest SQL that answers the question.",
                ),
                0.2,
            ),
            (
                self._candidate_prompt(
                    question,
                    "Double-check that every table and column exists in the schema.",
                ),
                0.4,
            ),
        ]

        candidates = []
        for prompt, temperature in variants:
            raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            text = raw if isinstance(raw, str) else str(raw)
            sql = (bridge.extract_sql(text) or "").strip()
            if sql:
                candidates.append(sql)

        if not candidates:
            raw = self.llm(base_prompt, system=system, temperature=0.0, n=1)
            text = raw if isinstance(raw, str) else str(raw)
            sql = (bridge.extract_sql(text) or "").strip()
            return sql or "SELECT 1"

        unique = self._deduplicate(candidates)

        best_sql = None
        best_key = None

        for index, sql in enumerate(unique):
            score = 1

            if self._looks_like_select(sql):
                score += 3
                try:
                    result = self.execute(sql)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                if isinstance(result, dict) and result.get("ok"):
                    score += 10
                else:
                    score -= 1

            length = len(sql)
            key = (-score, length, index)

            if best_key is None or key < best_key:
                best_key = key
                best_sql = sql

        return best_sql or "SELECT 1"

    def _candidate_prompt(self, question: str, hint: str) -> str:
        parts = []
        if hint:
            parts.append(hint)

        parts.extend(
            [
                "Schema:",
                self.schema,
                "",
                f"Question: {question}",
                "",
                "Return only one valid SQLite SQL SELECT statement.",
            ]
        )
        return "\n".join(parts)

    def _deduplicate(self, candidates):
        unique = []
        seen = set()

        for sql in candidates:
            key = " ".join(sql.lower().split())
            if key not in seen:
                seen.add(key)
                unique.append(sql)

        return unique

    def _looks_like_select(self, sql: str) -> bool:
        s = sql.strip()

        while True:
            if s.startswith("--"):
                newline = s.find("\n")
                if newline == -1:
                    return False
                s = s[newline + 1 :].strip()
            elif s.startswith("/*"):
                end = s.find("*/")
                if end == -1:
                    return False
                s = s[end + 2 :].strip()
            else:
                break

        s = s.lower()
        return s.startswith("select") or s.startswith("with")