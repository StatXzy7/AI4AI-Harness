"""Majority-vote harness over 3 independent SQL generations with execution-based selection."""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0Vote3(SQLHarness):
    """Sample 3 SQL candidates (temperature=0.7) and pick the majority-vote execution winner.

    Control flow:
      1. Ask the frozen solver for n=3 independent SQL strings.
      2. Extract a SQL candidate from each completion.
      3. Execute every candidate that parses successfully.
      4. Among executed rowsets, pick the one with the highest vote count.
      5. Return the SQL that produced the majority rows (ties broken by first occurrence).
    """

    N_SAMPLES = 3
    TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "")

        prompt = self._build_prompt(question, schema)

        completions = self.llm(
            prompt,
            system="",
            temperature=self.TEMPERATURE,
            n=self.N_SAMPLES,
        )

        candidates: list[str] = []
        for completion in self._as_iterable(completions):
            sql = bridge.extract_sql(completion)
            if sql:
                candidates.append(sql)

        if not candidates:
            return ""

        executed: list[tuple[str, list[Any]]] = []
        seen_sql: dict[tuple, str] = {}
        for sql in candidates:
            result = self.execute(sql)
            if result.get("ok") and isinstance(result.get("rows"), list):
                rows = result["rows"]
                key = self._row_key(rows)
                seen_sql[key] = sql
                executed.append((key, rows))

        if not executed:
            return candidates[0]

        vote_counter: Counter = Counter(key for key, _ in executed)
        winning_key, _ = vote_counter.most_common(1)[0]

        winner_rows = next(rows for key, rows in executed if key == winning_key)
        return seen_sql[winning_key]

    @staticmethod
    def _as_iterable(completions: Any) -> list[str]:
        if isinstance(completions, str):
            return [completions]
        if isinstance(completions, dict):
            for key in ("choices", "completions", "results", "outputs", "data"):
                if key in completions and completions[key]:
                    return P2P2DMinimaxS0Vote3._as_iterable(completions[key])
            return [str(completions)]
        if isinstance(completions, (list, tuple)):
            items: list[str] = []
            for item in completions:
                if isinstance(item, str):
                    items.append(item)
                elif isinstance(item, dict):
                    for key in ("text", "message", "content", "completion", "sql"):
                        if key in item and item[key]:
                            value = item[key]
                            if isinstance(value, str):
                                items.append(value)
                                break
                            items.extend(P2P2DMinimaxS0Vote3._as_iterable(value))
                            break
                else:
                    items.append(str(item))
            return items
        return [str(completions)]

    @staticmethod
    def _row_key(rows: list[Any]) -> tuple:
        normalized: list[Any] = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                normalized.append(tuple(row))
            else:
                normalized.append(row)
        return tuple(normalized)

    def _build_prompt(self, question: str, schema: str) -> str:
        schema_block = f"\n\nSchema:\n{schema}" if schema else ""
        return (
            "You are a Text-to-SQL assistant. "
            "Given the database schema and the user's question, produce exactly one "
            "syntactically correct SQL query that answers the question. "
            "Return only the SQL inside a