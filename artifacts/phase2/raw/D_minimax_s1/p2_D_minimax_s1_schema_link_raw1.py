"""Schema-linking harness that explicitly identifies referenced tables/columns before writing SQL against that subset."""
from __future__ import annotations

import json
import re
from typing import Any

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1SchemaLink(SQLHarness):
    """Plan-to-SQL pipeline with an explicit schema-linking first stage."""

    # ------------------------------------------------------------------ #
    #  Helpers                                                          #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise(text: str) -> list[str]:
        return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())

    def _snippets(self) -> list[tuple[str, str]]:
        """Return a list of (qualified_name, definition_snippet) from self.schema."""
        snippets: list[tuple[str, str]] = []
        if not self.schema:
            return snippets
        # split on CREATE TABLE statements
        for stmt in re.split(r";\s*\n", self.schema):
            head = stmt.strip().splitlines()[0] if stmt.strip() else ""
            m = re.match(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([^\s(]+)",
                         head, re.IGNORECASE)
            if not m:
                continue
            tbl = m.group(1).strip('"`.')
            # column lines
            for line in stmt.splitlines()[1:]:
                col = line.strip().rstrip(",").split()
                if not col or col[0].upper() in {"PRIMARY", "FOREIGN", "UNIQUE",
                                                "CHECK", "KEY", "INDEX",
                                                "CONSTRAINT"}:
                    continue
                if col[0].startswith("--"):
                    continue
                col_name = col[0].strip('"`,')
                snippets.append((f"{tbl}.{col_name}", line.strip()))
        return snippets

    # ------------------------------------------------------------------ #
    #  Stage 1: schema linking                                         #
    # ------------------------------------------------------------------ #
    def _link_schema(self, question: str) -> list[str]:
        """Return the linked table.column identifiers for the question."""
        catalog = self._snippets()
        if not catalog:
            return []

        tokens = set(self._normalise(question))

        def _score(qualified: str, snippet: str) -> int:
            tbl, col = qualified.split(".", 1)
            score = 0
            if tbl.lower() in tokens:
                score += 3
            if col.lower() in tokens:
                score += 3
            # partial match on column
            for t in tokens:
                if len(t) >= 3 and t in col.lower():
                    score += 2
                if len(t) >= 3 and t in tbl.lower():
                    score += 1
            return score

        ranked = sorted(catalog, key=lambda p: -_score(p[0], p[1]))
        # keep candidates with a positive heuristic score
        candidates = [p for p in ranked if _score(p[0], p[1]) > 0]

        # ask the LLM to confirm / prune the linked schema
        slim_lines = [f"{q}: {s}" for q, s in candidates[:40]]
        ask_prompt = (
            "Given the user question and a candidate list of database columns, "
            "return ONLY a JSON array of the exact identifiers (table.column) "
            "that are needed to answer the question.\n\n"
            f"Question: {question}\n\n"
            "Candidates:\n" + "\n".join(slim_lines)
        )
        try:
            raw = self.llm(ask_prompt, system="You are a schema-linking module.",
                           temperature=0.0, n=1)
        except TypeError:
            raw = self.llm(ask_prompt)

        linked = re.findall(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*",
                            raw or "")
        # fallback to heuristic top-K
        if not linked:
            linked = [q for q, _ in candidates[:6]]
        return linked

    # ------------------------------------------------------------------ #
    #  Stage 2: schema subset builder                                  #
    # ------------------------------------------------------------------ #
    def _subset_ddl(self, identifiers: list[str]) -> str:
        """Re-emit just the CREATE TABLE statements for the linked columns."""
        # group identifiers by table
        tables: dict[str, set[str]] = {}
        for ident in identifiers:
            if "." not in ident:
                continue
            tbl, col = ident.split(".", 1)
            tables.setdefault(tbl, set()).add(col)

        # map full_column -> line-snippet for quick lookup
        col_lookup: dict[str, list[str]] = {}
        table_sql: dict[str, str] = {}
        for stmt in re.split(r";\s*\n", self.schema or ""):
            head = stmt.strip().splitlines()[0] if stmt.strip() else ""
            m = re.match(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([^\s(]+)",
                         head, re.IGNORECASE)
            if not m:
                continue
            tbl = m.group(1).strip('"`.')
            table_sql[tbl] = stmt
            for line in stmt.splitlines()[1:]:
                col = line.strip().rstrip(",").split()
                if col and col[0].upper() not in {"PRIMARY", "FOREIGN", "UNIQUE",
                                                  "CHECK", "KEY", "INDEX",
                                                  "CONSTRAINT"}:
                    col_lookup[f"{tbl}.{col[0].strip('"`,')}"] = line

        blocks: list[str] = []
        for tbl, cols in tables.items():
            if tbl not in table_sql:
                continue
            head_line = table_sql[tbl].splitlines()[0]
            lines = [head_line]
            for c in cols:
                src = col_lookup.get(f"{tbl}.{c}")
                if src:
                    lines.append("    " + src.strip().rstrip(","))
            blocks.append(";\n".join(lines) + ";")
        return "\n\n".join(blocks)

    # ------------------------------------------------------------------ #
    #  Stage 3: SQL generation                                         #
    # ------------------------------------------------------------------ #
    def _draft_sql(self, question: str, subset: str) -> str:
        prompt = (
            "You are a SQL expert. Using ONLY the schema subset provided below, "
            "write a single SQLite-compatible SELECT statement that answers the "
            "question. Reply with only the SQL.\n\n"
            f"Schema subset:\n{subset or self.schema}\n\n"
            f"Question: {question}\n"
            "SQL:"
        )
        try:
            text = self.llm(prompt, system="You write precise SQL.",
                            temperature=0.0, n=1)
        except TypeError:
            text = self.llm(prompt)

        sql = bridge.extract_sql(text or "")
        if not sql:
            sql = text or ""
        return sql.strip()

    # ------------------------------------------------------------------ #
    #  Self-correction loop                                            #
    # ------------------------------------------------------------------ #
    def _repair(self, question: str, subset: str, sql: str,
                err: str) -> str:
        prompt = (
            "The following SQL produced an error. Rewrite it to fix the error "
            "while preserving intent. Use only the schema subset shown.\n\n"
            f"Question: {question}\n"
            f"Schema subset:\n{subset}\n"
            f"Failed SQL: {sql}\n"
            f"Error: {err}\n"
            "Fixed SQL:"
        )
        try:
            text = self.llm(prompt, system="You debug SQL.",
                            temperature=0.0, n=1)
        except TypeError:
            text = self.llm(prompt)
        fixed = bridge.extract_sql(text or "") or (text or "").strip()
        return fixed.strip()

    # ------------------------------------------------------------------ #
    #  Public entry point                                              #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        try:
            # 1. schema link ------------------------------------------------
            linked = self._link_schema(question)
            subset = self._subset_ddl(linked)

            # 2. draft SQL --------------------------------------------------
            sql = self._draft_sql(question, subset)

            # 3. execute & optionally repair --------------------------------
            for attempt in range(2):
                result: dict[str, Any] = self.execute(sql)
                if result.get("ok"):
                    return sql
                repaired = self._repair(question, subset, sql,
                                        result.get("error", ""))
                if not repaired or repaired == sql:
                    break
                sql = repaired
            return sql
        except Exception:
            # Last-resort: ask the LLM with the full schema, no repair loop.
            try:
                text = self.llm(
                    f"Write a SQLite SELECT for: {question}\n"
                    f"Schema:\n{self.schema}\nSQL:",
                    system="", temperature=0.0, n=1,
                )
            except TypeError:
                text = self.llm(
                    f"Write a SQLite SELECT for: {question}\n"
                    f"Schema:\n{self.schema}\nSQL:"
                )
            return (bridge.extract_sql(text) or text).strip()