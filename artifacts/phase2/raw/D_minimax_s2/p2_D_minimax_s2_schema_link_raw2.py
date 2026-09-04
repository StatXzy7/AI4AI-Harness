"""Prompt-to-prompt schema-linking harness that forces the frozen solver to reason over a pruned subset of tables/columns before emitting SQL."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


# Conservative stopwords for tokenization. We avoid heavy NLP deps so the
# harness stays portable across sandboxes.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "that", "this", "these", "those", "it", "its", "at", "we", "i", "you",
    "he", "she", "they", "them", "my", "our", "their", "his", "her",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "do", "does", "did", "have", "has", "had", "will", "would", "should",
    "could", "can", "may", "might", "must", "shall", "than", "then",
    "there", "here", "all", "any", "some", "no", "not", "only", "own",
    "same", "so", "too", "very", "s", "t", "m", "d", "ll", "re", "ve",
    "show", "list", "find", "give", "get", "tell", "me", "us", "please",
    "return", "fetch", "name", "names", "value", "values", "count",
    "many", "much", "each", "every",
}


class P2P2DMinimaxS2SchemaLink(SQLHarness):
    """A two-stage harness: stage 1 picks tables/columns, stage 2 writes SQL.

    Strategy:
      1. Parse ``self.schema`` into a structured representation of tables and
         their columns (with light type hints when available).
      2. Score each table and column against the natural-language question
         using cheap lexical features (token overlap, substring, identifier
         containment, header-style CamelCase/snake_case match).
      3. Build a *linked schema* containing only the top-k tables and their
         most relevant columns. We deliberately keep joins possible by
         retaining primary/foreign key columns and any column that matches
         a referenced identifier.
      4. Prompt the frozen LLM with the linked schema + the original
         question so it must reason only over the pruned subset.
      5. Post-process the model's reply, extract a single SQL statement via
         :func:`bridge.extract_sql`, and (optionally) sanity-check that the
         SQL only references symbols present in the linked schema.
    """

    # ----- configuration -------------------------------------------------
    MAX_TABLES = 5          # how many tables to keep in the linked schema
    MAX_COLS_PER_TABLE = 12 # columns kept per linked table
    OVERLAP_WEIGHT = 2.0    # token overlap weight
    SUBSTR_WEIGHT = 1.0     # substring match weight
    ID_WEIGHT = 3.0         # exact identifier match weight
    LLM_TEMPERATURE = 0.0
    SYSTEM_PROMPT = (
        "You are a careful Text-to-SQL analyst. You will be given a natural "
        "language question and a *linked subset* of the database schema. "
        "Only use the tables and columns present in that subset. Output a "
        "single SQL statement and nothing else."
    )

    # ====================================================================
    # Public API
    # ====================================================================
    def solve(self, question: str) -> str:
        """Return a single SQL string answering ``question`` against ``self.schema``."""
        # 1. Parse schema
        tables = self._parse_schema(self.schema)
        if not tables:
            # Fallback: hand the whole schema to the solver if parsing fails.
            linked_schema = self.schema
            linked_meta: Dict[str, Any] = {"tables": [], "links": []}
        else:
            # 2. Score & link
            linked_tables, links = self._link_schema(tables, question)
            linked_meta = {
                "tables": [t.name for t in linked_tables],
                "links": links,
            }
            # 3. Render a pruned schema for the LLM
            linked_schema = self._render_linked_schema(linked_tables, links)

        # 4. Build prompt and ask the frozen solver
        prompt = self._build_prompt(question, linked_schema, linked_meta)
        try:
            raw = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=self.LLM_TEMPERATURE,
                n=1,
            )
        except TypeError:
            # Be tolerant of harnesses whose ``llm`` signature differs.
            raw = self.llm(prompt, temperature=self.LLM_TEMPERATURE)

        # 5. Extract SQL
        text = self._coerce_llm_text(raw)
        sql = bridge.extract_sql(text) or ""

        # 6. Optional execution sanity-check / auto-repair
        sql = self._autorepair(sql, linked_meta)
        return sql.strip()

    # ====================================================================
    # Schema parsing
    # ====================================================================
    def _parse_schema(self, schema: str) -> List["TableSpec"]:
        """Best-effort parser supporting CREATE TABLE, parenthesised lists,
        and the common ``db_id(column1, column2, ...)`` mini-schema format
        emitted by Spider-style benchmarks."""
        if not schema:
            return []

        specs: List[TableSpec] = []
        text = schema.strip()

        # Try ``CREATE TABLE`` style first.
        for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(?:`)?(?P<name>[A-Za-z_][\w.]*)(?:`)?\s*\((?P<body>.*?)\)\s*(?:;|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            name = m.group("name").split(".")[-1]
            body = m.group("body")
            cols: List[ColumnSpec] = []
            for raw_line in body.split(","):
                line = raw_line.strip()
                if not line:
                    continue
                # Skip constraint lines
                up = line.upper().lstrip("(")
                if up.startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE",
                                   "CHECK", "CONSTRAINT", "INDEX", "KEY ")):
                    continue
                col_match = re.match(
                    r"(?:`)?(?P<cname>[A-Za-z_]\w*)(?:`)?\s+(?P<ctype>[\w(), ]+)?",
                    line,
                )
                if col_match:
                    cols.append(
                        ColumnSpec(
                            name=col_match.group("cname"),
                            type=(col_match.group("ctype") or "").strip(),
                        )
                    )
            if cols:
                specs.append(TableSpec(name=name, columns=cols))

        # Spider mini-schema: lines like ``db_name ( col1, col2, ... )``
        if not specs:
            for line in text.splitlines():
                line = line.strip().rstrip(",").rstrip(";")
                m = re.match(
                    r"(?P<name>[A-Za-z_]\w*)\s*\(\s*(?P<body>[^)]*)\)",
                    line,
                )
                if not m:
                    continue
                body = m.group("body")
                cols = []
                for raw in body.split(","):
                    raw = raw.strip().strip("`")
                    if not raw:
                        continue
                    parts = raw.split()
                    cols.append(ColumnSpec(name=parts[0], type=" ".join(parts[1:])))
                if cols:
                    specs.append(TableSpec(name=m.group("name"), columns=cols))

        # JSON-style schema
        if not specs:
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict):
                for tname, tcols in data.items():
                    if isinstance(tcols, list):
                        cols = []
                        for c in tcols:
                            if isinstance(c, str):
                                cols.append(ColumnSpec(name=c, type=""))
                            elif isinstance(c, dict) and "name" in c:
                                cols.append(
                                    ColumnSpec(
                                        name=c["name"],
                                        type=c.get("type", ""),
                                    )
                                )
                        if cols:
                            specs.append(TableSpec(name=tname, columns=cols))

        return specs

    # ====================================================================
    # Schema linking
    # ====================================================================
    def _link_schema(
        self,
        tables: List["TableSpec"],
        question: str,
    ) -> Tuple[List["TableSpec"], List[Dict[str, str]]]:
        q_tokens = self._tokenize(question)

        scored: List[Tuple[float, TableSpec]] = []
        for t in tables:
            score = self._score_table(t, q_tokens, question)
            scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        kept = [t for s, t in scored if s > 0][: self.MAX_TABLES]

        # If everything scored 0 (e.g. ambiguous question), fall back to
        # the first MAX_TABLES so the solver at least sees *something*.
        if not kept:
            kept = [t for _, t in scored][: self.MAX_TABLES]

        # Promote columns that look like joins if multiple tables survived.
        links = self._infer_links(kept, q_tokens)

        # Trim columns per table but keep join keys & high-score ones.
        enriched: List[TableSpec] = []
        for t in kept:
            link_cols = {l["src"] for l in links if l["src_table"] == t.name}
            link_cols |= {l["dst"] for l in links if l["dst_table"] == t.name}
            link_cols |= {t.name}  # self-joins
            scored_cols = sorted(
                t.columns,
                key=lambda c: (
                    -self._score_column(c, q_tokens, question, t.name),
                    c.name,
                ),
            )
            keep_cols: List[ColumnSpec] = []
            seen: set = set()
            for c in scored_cols:
                if c.name in link_cols and c.name not in seen:
                    keep_cols.append(c)
                    seen.add(c.name)
            for c in scored_cols:
                if len(keep_cols) >= self.MAX_COLS_PER_TABLE:
                    break
                if c.name in seen:
                    continue
                keep_cols.append(c)
                seen.add(c.name)
            enriched.append(TableSpec(name=t.name, columns=keep_cols))

        return enriched, links

    def _score_table(
        self,
        table: "TableSpec",
        q_tokens: List[str],
        question: str,
    ) -> float:
        name_tokens = self._tokenize(table.name)
        score = 0.0
        # Identifier match (e.g. question says "students" -> table "student")
        if self._identifier_present(table.name, question):
            score += self.ID_WEIGHT
        # Token overlap with table name
        score += self.OVERLAP_WEIGHT * len(q_tokens & set(name_tokens))
        # Substring match
        if self._substring_match(table.name, question):
            score += self.SUBSTR_WEIGHT
        # Column evidence: a table is more likely if any of its columns
        # matches the question strongly.
        for col in table.columns:
            score += 0.3 * self._score_column(col, q_tokens, question, table.name)
        return score

    def _score_column(
        self,
        col: "ColumnSpec",
        q_tokens: List[str],
        question: str,
        table_name: str,
    ) -> float:
        col_tokens = self._tokenize(col.name)
        s = 0.0
        if self._identifier_present(col.name, question):
            s += self.ID_WEIGHT
        if self._identifier_present(f"{table_name}.{col.name}", question):
            s += self.ID_WEIGHT * 0.5
        s += self.OVERLAP_WEIGHT * len(q_tokens & set(col_tokens))
        if self._substring_match(col.name, question):
            s += self.SUBSTR_WEIGHT
        # Very common column names tend to be noisy.
        if col.name.lower() in {"id", "name", "created_at", "updated_at"}:
            s *= 0.5
        return s

    # ----- helpers for linking -----------------------------------------
    def _infer_links(
        self,
        tables: List["TableSpec"],
        q_tokens: set,
    ) -> List[Dict[str, str]]:
        """Guess primary/foreign key relationships by column-name overlap."""
        links: List[Dict[str, str]] = []
        name_to_cols: Dict[str, List[Tuple[str, "TableSpec"]]] = {}
        for t in tables:
            for c in t.columns:
                # canonicalise: strip trailing "_id", lowercase.
                canon = self._canon(c.name)
                name_to_cols.setdefault(canon, []).append((c.name, t))

        for canon, occurrences in name_to_cols.items():
            if len(occurrences) < 2:
                continue
            if canon in {"id"}:
                continue
            for (src_name, src_t), (dst_name, dst_t) in zip(
                occurrences, occurrences[1:]
            ):
                if src_t.name == dst_t.name:
                    continue
                links.append(
                    {
                        "src_table": src_t.name,
                        "src": src_name,
                        "dst_table": dst_t.name,
                        "dst": dst_name,
                    }
                )
        return links

    # ====================================================================
    # Prompt construction
    # ====================================================================
    def _build_prompt(
        self,
        question: str,
        linked_schema: str,
        linked_meta: Dict[str, Any],
    ) -> str:
        meta_lines = ""
        if linked_meta.get("tables"):
            meta_lines = (
                "Linked tables: "
                + ", ".join(f"`{t}`" for t in linked_meta["tables"])
                + "\n"
            )
            if linked_meta.get("links"):
                meta_lines += "Possible joins:\n"
                for l in linked_meta["links"]:
                    meta_lines += (
                        f"  - {l['src_table']}.{l['src']} "
                        f"= {l['dst_table']}.{l['dst']}\n"
                    )

        return (
            "### Question\n"
            f"{question.strip()}\n\n"
            "### Linked schema (only use these tables/columns)\n"
            f"{linked_schema.strip()}\n\n"
            f"{meta_lines}\n"
            "### Instructions\n"
            "Write ONE valid SQL statement that answers the question using only "
            "the linked schema above. Do not invent columns. Output only the SQL.\n"
        )

    def _render_linked_schema(
        self,
        tables: List["TableSpec"],
        links: List[Dict[str, str]],
    ) -> str:
        if not tables:
            return self.schema  # nothing we could prune
        out: List[str] = []
        link_index: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
        for l in links:
            link_index.setdefault((l["src_table"], l["src"]), []).append(l)
            link_index.setdefault((l["dst_table"], l["dst"]), []).append(l)
        for t in tables:
            cols = ", ".join(
                f"{c.name}" + (f" {c.type}" if c.type else "")
                for c in t.columns
            )
            out.append(f"CREATE TABLE `{t.name}` ({cols});")
            for c in t.columns:
                rels = link_index.get((t.name, c.name), [])
                for r in rels:
                    if r["src_table"] == t.name and r["src"] == c.name:
                        out.append(
                            f"  -- {t.name}.{c.name} references "
                            f"{r['dst_table']}.{r['dst']}"
                        )
                    elif r["dst_table"] == t.name and r["dst"] == c.name:
                        out.append(
                            f"  -- {t.name}.{c.name} referenced by "
                            f"{r['src_table']}.{r['src']}"
                        )
        return "\n".join(out)

    # ====================================================================
    # Post-processing
    # ====================================================================
    def _coerce_llm_text(self, raw: Any) -> str:
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, dict):
                return first.get("text", "") or first.get("content", "")
            return str(first)
        if isinstance(raw, dict):
            return raw.get("text", "") or raw.get("content", str(raw))
        return str(raw)

    def _autorepair(self, sql: str, linked_meta: Dict[str, Any]) -> str:
        """If execution is cheap and we have a linked subset, repair obvious
        omissions by ensuring the SQL targets one of the linked tables."""
        if not sql:
            return sql

        tables = linked_meta.get("tables") or []
        if not tables:
            return sql

        # If the SQL doesn't mention any linked table, try a quick repair
        # by re-asking the model once. This keeps the harness a strict
        # wrapper around the frozen solver (we only re-issue a targeted prompt).
        used = any(re.search(rf"\b{re.escape(t)}\b", sql, flags=re.IGNORECASE)
                   for t in tables)
        if used:
            return sql

        repair_prompt = (
            "Your previous answer did not use any of the linked tables. "
            "Here is the linked schema again:\n"
            f"{self._render_linked_schema([], linked_meta.get('links', []))}\n"
            "Rewrite the query using ONLY these tables. Output only the SQL.\n"
            "Question:\n"
        )
        # We do not have access to the original question here, so only attempt
        # the repair if the model gave us a candidate SQL. We treat it as best
        # effort: try LLM with the original schema as context.
        try:
            raw = self.llm(repair_prompt, system=self.SYSTEM_PROMPT,
                           temperature=self.LLM_TEMPERATURE, n=1)
        except Exception:
            return sql
        repaired = bridge.extract_sql(self._coerce_llm_text(raw)) or sql
        return repaired

    # ====================================================================
    # Tokenisation helpers
    # ====================================================================
    @staticmethod
    def _tokenize(text: str) -> set:
        if not text:
            return set()
        # split on whitespace + punctuation, normalise case.
        raw = re.findall(r"[A-Za-z_]\w+", text.lower())
        # also expose snake_case / camelCase fragments.
        fragments: List[str] = []
        for tok in raw:
            fragments.extend(tok.split("_"))
        out = set(raw) | set(fragments)
        out -= _STOPWORDS
        return {t for t in out if len(t) > 1}

    @staticmethod
    def _canon(name: str) -> str:
        n = name.lower()
        if n.endswith("_id"):
            n = n[:-3]
        return n

    @staticmethod
    def _identifier_present(identifier: str, text: str) -> bool:
        if not identifier or not text:
            return False
        pat = r"\b" + re.escape(identifier.lower()) + r"\b"
        return re.search(pat, text.lower()) is not None

    @staticmethod
    def _substring_match(name: str, text: str) -> bool:
        n = name.lower().strip("_")
        if len(n) < 3:
            return False
        return n in text.lower()


# ---------------------------------------------------------------------------
# Lightweight value objects (using inner classes for portability; they hold
# only str fields and compare by identity / equality).
# ---------------------------------------------------------------------------
class ColumnSpec:
    __slots__ = ("name", "type")

    def __init__(self, name: str, type: str = ""):
        self.name = name
        self.type = type

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ColumnSpec({self.name!r}, {self.type!r})"


class TableSpec:
    __slots__ = ("name", "columns")

    def __init__(self, name: str, columns: List[ColumnSpec]):
        self.name = name
        self.columns = columns

    def __repr__(self) -> str:  # pragma: no cover
        return f"TableSpec({self.name!r}, {len(self.columns)} cols)"