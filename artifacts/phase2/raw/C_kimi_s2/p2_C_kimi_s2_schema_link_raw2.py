"""Harness that first LLM-links the question to relevant tables/columns, prunes the schema to that linked subset in code, then generates and execution-repairs SQL against only the linked schema."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2SchemaLink(SQLHarness):
    """Schema-link-then-generate Text-to-SQL harness.

    Control flow:
      1. Link:  ask the frozen LLM which tables/columns the question mentions.
      2. Prune: rebuild the schema text from only the linked tables/columns.
      3. Generate: produce SQL constrained to the linked subset.
      4. Repair: execute; on error, regenerate against the same linked subset.
    """

    LINK_SYSTEM = (
        "You are a meticulous database schema linker for Text-to-SQL. "
        "Given a database schema and a question, select exactly the tables and "
        "columns required to answer it, including columns used for joins, "
        "filters, grouping, ordering, and the final output. "
        'Respond with ONLY a JSON object shaped as '
        '{"tables": {"table_name": ["column_a", "column_b"]}} and nothing else.'
    )

    GEN_SYSTEM = (
        "You are an expert SQLite programmer. Write ONE syntactically valid "
        "SQLite query that answers the question using ONLY the tables and "
        "columns shown in the provided linked schema. Output just the SQL, "
        "optionally inside a single fenced code block."
    )

    MAX_REPAIR_ROUNDS = 2

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        # Steps 1+2: schema linking, then prune the schema to the linked subset.
        linked = self._link_schema(question)
        linked_schema = self._prune_schema(self.schema, linked)
        if not linked_schema.strip():
            linked_schema = self.schema  # linking yielded nothing usable

        # Step 3: generate SQL against the linked subset.
        sql = self._generate(linked_schema, question)
        best = sql

        # Step 4: execution-guided repair, still against the linked subset.
        for _ in range(self.MAX_REPAIR_ROUNDS + 1):
            if not sql:
                break
            ok, err = self._run(sql)
            if ok:
                return sql
            sql = self._repair(linked_schema, question, sql, err)
            if sql:
                best = sql

        # Safety net: if the linked subset was misleading, try the full schema once.
        fallback = self._generate(self.schema, question)
        if fallback:
            ok, _ = self._run(fallback)
            if ok:
                return fallback
        return best or fallback or ""

    # ------------------------------------------------------- step 1: linking
    def _link_schema(self, question: str) -> dict:
        prompt = (
            "Database schema:\n" + self.schema +
            "\n\nQuestion: " + question +
            "\n\nWhich tables and columns are needed to answer this question? "
            "Reply with JSON only."
        )
        try:
            raw = self.llm(prompt, system=self.LINK_SYSTEM, temperature=0.0, n=1)
        except Exception:
            return {}
        return self._parse_linking(self._as_text(raw))

    @staticmethod
    def _parse_linking(text: str) -> dict:
        """Parse the linker's answer into {table: {col, ...}} (order kept)."""
        linked: dict = {}

        def add(table, cols):
            slots = linked.setdefault(str(table), {})
            for c in cols or []:
                slots[str(c)] = None

        # Preferred: JSON object somewhere in the reply.
        candidate = None
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            candidate = text[start:end + 1]
        data = None
        if candidate:
            try:
                data = json.loads(candidate)
            except Exception:
                data = None
        if isinstance(data, dict):
            tables = data.get("tables", data)
            if isinstance(tables, dict):
                for t, cols in tables.items():
                    if isinstance(cols, str):
                        cols = [cols]
                    if isinstance(cols, (list, tuple)):
                        add(t, cols)
                    else:
                        add(t, [])
            elif isinstance(tables, (list, tuple)):
                for t in tables:
                    add(t, [])

        # Supplement: dotted "table.column" mentions (covers non-JSON replies).
        for t, c in re.findall(r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)", text):
            add(t, [c])

        return {t: list(cols.keys()) for t, cols in linked.items()}

    # ------------------------------------------------------- step 2: pruning
    def _prune_schema(self, schema: str, linked: dict) -> str:
        """Rebuild the schema text using only linked tables/columns."""
        if not linked:
            return ""
        linked_lower = {
            str(t).lower(): {str(c).lower() for c in cols}
            for t, cols in linked.items()
        }

        # Primary path: CREATE TABLE DDL blocks.
        blocks = self._split_create_blocks(schema)
        if blocks:
            kept = []
            for tname, block in blocks:
                cols = linked_lower.get(tname.lower())
                if cols is None:
                    continue
                kept.append(self._filter_block_columns(block, cols))
            return "\n\n".join(kept)

        # Fallback: blank-line-separated "table(...)" / "Table: name" chunks.
        kept = []
        for chunk in re.split(r"\n\s*\n", schema):
            tname = self._guess_table_name(chunk)
            if tname and tname.lower() in linked_lower:
                kept.append(chunk.strip())
        return "\n\n".join(kept)

    @staticmethod
    def _split_create_blocks(schema: str):
        """Return [(table_name, full CREATE TABLE statement), ...]."""
        blocks = []
        pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"[\"'`\[]?([A-Za-z_]\w*)[\"'`\]]?",
            re.IGNORECASE,
        )
        for m in pattern.finditer(schema):
            open_idx = schema.find("(", m.end())
            if open_idx == -1:
                continue
            depth, j = 0, open_idx
            while j < len(schema):
                ch = schema[j]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            end = j + 1
            k = end
            while k < len(schema) and schema[k] in " \t\r\n":
                k += 1
            if k < len(schema) and schema[k] == ";":
                end = k + 1
            blocks.append((m.group(1), schema[m.start():end]))
        return blocks

    @staticmethod
    def _split_items(body: str):
        """Split a CREATE TABLE body into top-level comma-separated items."""
        items, depth, cur = [], 0, []
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                items.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        tail = "".join(cur)
        if tail.strip():
            items.append(tail)
        return [i.strip() for i in items if i.strip()]

    @staticmethod
    def _column_name_from_item(item: str):
        """Column name if the item is a column definition, else None."""
        s = item.strip().rstrip(",").strip()
        if not s:
            return None
        first = s.split(None, 1)[0].strip("\"'`[]")
        if first.upper() in {
            "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT",
            "KEY", "INDEX", "EXCLUDE", "LIKE",
        }:
            return None
        return first

    def _filter_block_columns(self, block: str, cols_lower: set) -> str:
        """Drop non-linked column definitions from one CREATE TABLE block."""
        if not cols_lower:
            return block  # table linked without column detail: keep as-is
        open_idx = block.find("(")
        close_idx = block.rfind(")")
        if open_idx == -1 or close_idx <= open_idx:
            return block
        head, body, tail = (
            block[:open_idx + 1],
            block[open_idx + 1:close_idx],
            block[close_idx:],
        )
        items = self._split_items(body)
        defined = {
            n.lower()
            for n in (self._column_name_from_item(i) for i in items)
            if n
        }
        kept = []
        for item in items:
            name = self._column_name_from_item(item)
            if name is not None:
                if name.lower() in cols_lower:
                    kept.append(item)
            else:
                # Table constraint: keep only if every local column it
                # references survived the linking cut.
                mentioned = {
                    tok.lower()
                    for tok in re.findall(r"[A-Za-z_]\w*", item)
                } & defined
                if mentioned and mentioned <= cols_lower:
                    kept.append(item)
        if not kept:
            return block  # linker hallucinated names: keep block intact
        return head + "\n  " + ",\n  ".join(kept) + "\n" + tail

    @staticmethod
    def _guess_table_name(chunk: str):
        m = re.search(r"[Tt]able\s*:?\s*[\"'`]?([A-Za-z_]\w*)", chunk)
        if m:
            return m.group(1)
        m = re.match(r"\s*[\"'`]?([A-Za-z_]\w*)[\"'`]?\s*[(:]", chunk)
        return m.group(1) if m else None

    # ------------------------------------------- steps 3+4: generate/repair
    def _generate(self, schema_text: str, question: str) -> str:
        prompt = (
            "Linked schema (only these tables/columns are relevant):\n"
            + schema_text +
            "\n\nQuestion: " + question +
            "\n\nWrite a single SQLite query that answers the question using "
            "only the linked schema above."
        )
        raw = self.llm(prompt, system=self.GEN_SYSTEM, temperature=0.0, n=1)
        return self._extract(raw)

    def _repair(self, schema_text: str, question: str, bad_sql: str, error: str) -> str:
        prompt = (
            "Linked schema:\n" + schema_text +
            "\n\nQuestion: " + question +
            "\n\nThis SQL query failed:\n" + bad_sql +
            "\n\nExecution error:\n" + (error or "unknown error") +
            "\n\nRewrite ONE corrected SQLite query using only the linked "
            "schema above. Output only the corrected SQL."
        )
        try:
            raw = self.llm(prompt, system=self.GEN_SYSTEM, temperature=0.0, n=1)
        except Exception:
            return bad_sql
        return self._extract(raw) or bad_sql

    # -------------------------------------------------------------- helpers
    def _run(self, sql: str):
        try:
            res = self.execute(sql)
        except Exception as exc:  # defensive: executor itself blew up
            return False, str(exc)
        if isinstance(res, dict):
            return bool(res.get("ok")), str(res.get("error", "") or "")
        return bool(res), ""

    def _extract(self, raw) -> str:
        text = self._as_text(raw)
        try:
            sql = (bridge.extract_sql(text) or "").strip()
        except Exception:
            sql = ""
        if sql:
            return sql
        m = re.search(r"(?is)\b(?:SELECT|WITH)\b.*", text)
        return m.group(0).strip() if m else ""

    @staticmethod
    def _as_text(raw) -> str:
        if isinstance(raw, (list, tuple)):
            return "\n".join(str(x) for x in raw)
        return "" if raw is None else str(raw)