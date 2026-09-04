"""Schema-linking harness: the frozen LLM first identifies the tables/columns mentioned in the question, then the SQL is generated against only that linked schema subset."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1SchemaLink(SQLHarness):
    """Two-stage text-to-SQL pipeline: (1) LLM-based schema linking over the
    full schema to select the question-relevant tables/columns, (2) SQL
    generation prompted with only that linked subset."""

    LINK_SYSTEM = (
        "You are a precise database schema linker. Given a question and a "
        "database schema, output only the schema items needed to answer the "
        "question, one per line, formatted as table.column (or table.* to "
        "take a whole table). No explanations, no markdown."
    )

    GEN_SYSTEM = (
        "You are an expert SQLite programmer. Given a question and the "
        "relevant schema subset, write one correct SQLite query. Output SQL "
        "only: no explanations, no markdown fences."
    )

    # ================================================================ solve
    def solve(self, question: str) -> str:
        # Parse the full schema into a structured table -> columns map.
        table_map = self._parse_schema(self.schema)

        # ---- Stage 1: schema linking ----------------------------------
        # Ask the frozen LLM which tables/columns the question mentions,
        # then parse that answer into a concrete linked subset.
        link_prompt = self._build_link_prompt(question, table_map)
        link_text = self._ask(link_prompt, system=self.LINK_SYSTEM)
        linked_tables, linked_cols = self._parse_link_output(link_text, table_map)

        # Deterministic recall boost: any table literally named in the
        # question is also part of the linked subset.
        self._augment_from_question(question, table_map, linked_tables, linked_cols)

        # ---- Stage 2: prune the schema to the linked subset -----------
        linked_schema = self._render_linked_schema(table_map, linked_tables, linked_cols)
        if not linked_schema.strip():
            linked_schema = self.schema  # safety fallback: never generate blind

        # ---- Stage 3: generate SQL against the linked subset ----------
        gen_prompt = (
            "Relevant database schema:\n"
            f"{linked_schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question, using "
            "only the tables and columns shown above."
        )
        gen_text = self._ask(gen_prompt, system=self.GEN_SYSTEM)

        try:
            sql = bridge.extract_sql(gen_text)
        except Exception:
            sql = ""
        if not sql or not sql.strip():
            sql = gen_text
        return sql.strip()

    # =========================================================== LLM helper
    def _ask(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    # ======================================================= schema parsing
    _HEADER_RE = re.compile(
        r"^\s*(?:#|--)?\s*table\s*[:\-]\s*[`\"\[]?([A-Za-z0-9_\. ]+?)[`\"\]]?\s*:?\s*$",
        re.IGNORECASE,
    )
    _CREATE_RE = re.compile(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?([A-Za-z0-9_\.]+)[`\"\]]?",
        re.IGNORECASE,
    )
    _STOPWORDS = {
        "create", "table", "primary", "foreign", "constraint", "unique",
        "check", "key", "references", "not", "null", "default", "columns",
    }

    def _parse_schema(self, schema_text):
        """Best-effort parse of self.schema into
        {table_name: {"block": original text, "columns": [...]}}.

        Handles both 'Table: name / Columns: ...' and 'CREATE TABLE ...'
        layouts; each table keeps its original text block so it can be
        re-rendered verbatim in the linked subset.
        """
        tables = {}
        lines = (schema_text or "").splitlines()
        i = 0
        while i < len(lines):
            m = self._HEADER_RE.match(lines[i]) or self._CREATE_RE.search(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1).strip().strip('`"[]')
            block = [lines[i]]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if self._HEADER_RE.match(nxt) or self._CREATE_RE.search(nxt):
                    break
                if not nxt.strip() and len(block) > 1:
                    break
                block.append(nxt)
                i += 1
            block_text = "\n".join(block).rstrip()
            tables[name] = {
                "block": block_text,
                "columns": self._extract_columns(block_text),
            }
        return tables

    def _extract_columns(self, block_text):
        first = block_text.splitlines()[0] if block_text.splitlines() else ""
        if self._CREATE_RE.search(first):
            return self._extract_columns_ddl(block_text)
        cols = []
        for ln in block_text.splitlines()[1:]:
            s = ln.strip().rstrip(",")
            if not s:
                continue
            m = re.match(r"(?i)columns\s*:\s*(.+)$", s)
            if m:  # "Columns: a (t), b (t)" style
                for part in m.group(1).split(","):
                    cm = re.match(r"\s*[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)", part)
                    if cm:
                        cols.append(cm.group(1))
                continue
            cm = re.match(r"[-*]?\s*[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)[`\"\]]?", s)
            if cm and cm.group(1).lower() not in self._STOPWORDS:
                cols.append(cm.group(1))
        return self._dedupe(cols)

    def _extract_columns_ddl(self, block_text):
        start = block_text.find("(")
        end = block_text.rfind(")")
        if start == -1 or end <= start:
            return []
        body = block_text[start + 1:end]
        # Split top-level commas (ignore commas inside type parentheses).
        parts, cur, depth = [], [], 0
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        if cur:
            parts.append("".join(cur))
        cols = []
        for p in parts:
            m = re.match(r"\s*[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)", p)
            if m and m.group(1).lower() not in self._STOPWORDS:
                cols.append(m.group(1))
        return self._dedupe(cols)

    @staticmethod
    def _dedupe(items):
        seen, out = set(), []
        for x in items:
            if x.lower() not in seen:
                seen.add(x.lower())
                out.append(x)
        return out

    # ====================================================== stage 1: linking
    def _build_link_prompt(self, question, table_map):
        if table_map:
            catalog = "\n".join(
                f"{t}: {', '.join(info['columns'])}" if info["columns"] else t
                for t, info in table_map.items()
            )
        else:
            catalog = self.schema
        return (
            "Database schema catalog (table: columns):\n"
            f"{catalog}\n\n"
            f"Question: {question}\n\n"
            "List every table and column needed to answer the question, one "
            "per line, as table.column (or table.* for a whole table). "
            "Output nothing else."
        )

    def _parse_link_output(self, link_text, table_map):
        """Turn the LLM's linking answer into (linked_tables, linked_cols)."""
        linked_tables, linked_cols = set(), {}
        if not table_map:
            return linked_tables, linked_cols
        canon_t = {t.lower(): t for t in table_map}
        canon_c = {
            t.lower(): {c.lower(): c for c in info["columns"]}
            for t, info in table_map.items()
        }
        for raw in (link_text or "").splitlines():
            s = raw.strip().lstrip("-*•0123456789. )").strip().strip('`"')
            if not s or s.endswith(":"):
                continue
            if "." in s:
                t_part, c_part = s.rsplit(".", 1)
            else:
                t_part, c_part = s, "*"
            tl = t_part.strip().strip('`"[] ').lower()
            c = c_part.strip().strip('`"[] ').rstrip(",;")
            if tl not in canon_t:
                # Prose line: look for any known table name inside it.
                tl = next(
                    (cand for cand in canon_t
                     if re.search(r"\b" + re.escape(cand) + r"\b", s.lower())),
                    None,
                )
                if tl is None:
                    continue
            real_t = canon_t[tl]
            linked_tables.add(real_t)
            if c in ("", "*"):
                linked_cols.setdefault(real_t, set()).update(table_map[real_t]["columns"])
            elif c.lower() in canon_c.get(tl, {}):
                linked_cols.setdefault(real_t, set()).add(canon_c[tl][c.lower()])
            else:
                # Unknown column: keep the whole table rather than lose recall.
                linked_cols.setdefault(real_t, set()).update(table_map[real_t]["columns"])
        # Fallback: whole-word scan of the raw linking output.
        if not linked_tables:
            low = (link_text or "").lower()
            for tl, real_t in canon_t.items():
                if re.search(r"\b" + re.escape(tl) + r"\b", low):
                    linked_tables.add(real_t)
                    linked_cols.setdefault(real_t, set()).update(table_map[real_t]["columns"])
        return linked_tables, linked_cols

    def _augment_from_question(self, question, table_map, linked_tables, linked_cols):
        """Add tables whose names literally appear in the question."""
        if not table_map:
            return
        q = question or ""
        for t, info in table_map.items():
            if re.search(r"(?i)\b" + re.escape(t) + r"\b", q):
                linked_tables.add(t)
                linked_cols.setdefault(t, set()).update(info["columns"])

    # ==================================================== stage 2: rendering
    def _render_linked_schema(self, table_map, linked_tables, linked_cols):
        """Render only the linked tables (original order preserved)."""
        if not table_map or not linked_tables:
            return ""
        parts = []
        for t, info in table_map.items():
            if t not in linked_tables:
                continue
            block = info["block"].strip()
            cols = sorted(linked_cols.get(t, set()), key=str.lower)
            if cols and info["columns"] and len(cols) < len(info["columns"]):
                block += "\n-- linked columns: " + ", ".join(cols)
            parts.append(block)
        return "\n\n".join(parts)