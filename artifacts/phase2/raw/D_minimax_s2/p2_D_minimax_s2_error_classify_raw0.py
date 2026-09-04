"""Prompt-twice, classify execution errors into syntax/schema/semantics, then apply targeted fixes up to 2 rounds."""
from __future__ import annotations
from typing import Any, Dict, Optional

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2ErrorClassify(SQLHarness):
    """Two-pass prompt harness with error-class taxonomy (S2 = syntax/schema/semantics)."""

    # ----------------------------- prompts -----------------------------
    _SYSTEM = (
        "You are a precise Text-to-SQL generator. Use only the provided schema. "
        "Output ONLY a single SQL statement and nothing else."
    )

    _PROMPT_V1 = (
        "Schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Write exactly one SQLite-compatible SQL query that answers the question.\n"
        "Reply with ONLY the SQL."
    )

    _PROMPT_V2 = (
        "Schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Previous attempt produced this SQL:\n{prev_sql}\n\n"
        "It failed with this error:\n{error}\n\n"
        "Error category: {category}\n\n"
        "Diagnosis hint: {hint}\n\n"
        "Rewrite the SQL to fix the error. Reply with ONLY the corrected SQL."
    )

    # -------------------------- error classifiers -----------------------
    @staticmethod
    def _classify(err: str) -> str:
        """Return one of: 'syntax', 'schema', 'semantics'."""
        e = (err or "").lower()
        # Syntax-ish: parser/tokenizer complaints
        if any(tok in e for tok in (
            "syntax error", "near \"", "unexpected", "incomplete input",
            "unrecognized token", "parse error", "unterminated",
            "misuse of", "no viable alternative",
        )):
            return "syntax"
        # Schema-ish: missing/unknown tables or columns
        if any(tok in e for tok in (
            "no such table", "no such column", "no such function",
            "ambiguous column", "unknown column", "does not exist",
            "table not found", "column not found",
        )):
            return "schema"
        # Otherwise treat as semantic/runtime/logic
        return "semantics"

    @staticmethod
    def _hint_for(category: str) -> str:
        if category == "syntax":
            return (
                "Check quoting, parentheses, trailing commas, missing FROM/WHERE/GROUP BY keywords, "
                "and valid SQLite dialect."
            )
        if category == "schema":
            return (
                "Verify every table and column actually exists in the provided schema; use only listed names; "
                "use schema-qualified table names if needed and double-check column spellings."
            )
        # semantics
        return (
            "Check JOIN conditions, GROUP BY/HAVING aggregation coverage, filter predicates, "
            "subquery aliases, and that the query actually answers the question."
        )

    # ----------------------------- harness ------------------------------
    def solve(self, question: str) -> str:
        schema: str = getattr(self, "schema", "") or ""

        # ---- Pass 1: direct generation ----
        prompt1 = self._PROMPT_V1.format(schema=schema, question=question)
        text1 = self.llm(prompt1, system=self._SYSTEM, temperature=0.0, n=1)
        sql1 = bridge.extract_sql(text1) or ""
        sql1 = sql1.strip()
        if not sql1:
            return ""

        res1 = self.execute(sql1)
        if res1.get("ok"):
            return sql1

        # ---- Pass 2: classify and ask for a targeted fix ----
        err = res1.get("error") or "unknown error"
        category = self._classify(err)
        hint = self._hint_for(category)

        prompt2 = self._PROMPT_V2.format(
            schema=schema,
            question=question,
            prev_sql=sql1,
            error=err,
            category=category,
            hint=hint,
        )
        text2 = self.llm(prompt2, system=self._SYSTEM, temperature=0.0, n=1)
        sql2 = (bridge.extract_sql(text2) or "").strip()
        if not sql2:
            return sql1  # nothing better to do than return the previous attempt

        res2 = self.execute(sql2)
        if res2.get("ok"):
            return sql2

        # ---- Round 2: re-classify the new error and retry once more ----
        err2 = res2.get("error") or "unknown error"
        category2 = self._classify(err2)
        hint2 = self._hint_for(category2)

        prompt3 = self._PROMPT_V2.format(
            schema=schema,
            question=question,
            prev_sql=sql2,
            error=err2,
            category=category2,
            hint=hint2,
        )
        text3 = self.llm(prompt3, system=self._SYSTEM, temperature=0.0, n=1)
        sql3 = (bridge.extract_sql(text3) or "").strip()
        if not sql3:
            return sql2

        # Final return: prefer a successful result, else last attempt.
        res3 = self.execute(sql3)
        if res3.get("ok"):
            return sql3
        return sql3