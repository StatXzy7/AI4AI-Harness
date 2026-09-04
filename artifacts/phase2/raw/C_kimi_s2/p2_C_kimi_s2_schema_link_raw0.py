"""Schema-link-then-generate Text-to-SQL harness: an explicit schema-linking stage first selects the tables/columns relevant to the question, then SQL is generated and execution-repaired strictly against that linked schema subset."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2SchemaLink(SQLHarness):
    """Two-stage pipeline: (1) link the question to a subset of schema tables/columns
    (LLM linker + lexical mention matching), (2) generate SQL constrained to that
    linked subset, with a bounded execution-feedback repair loop."""

    _CONSTRAINT_WORDS = {
        "primary", "foreign", "unique", "check", "constraint", "key",
        "index", "references", "exclude",
    }
    # overly generic column names must not trigger lexical table linking on their own
    _COLUMN_STOPWORDS = {
        "id", "name", "type", "date", "time", "year", "month", "day", "count",
        "number", "value", "amount", "code", "state", "city", "status", "text",
    }

    # ------------------------------------------------------------------ #
    # entry point: the strategy lives here in the control flow
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        schema_obj = self._parse_schema(self.schema)

        # ---- Stage 1: schema linking ----------------------------------
        # Identify the tables/columns mentioned by the question BEFORE any
        # SQL is written, and physically prune the schema down to that subset.
        linked = self._link_schema(question, schema_obj)
        pruned_schema = self._build_pruned_schema(schema_obj, linked)

        # ---- Stage 2: SQL written against the linked subset only ------
        sql = self._generate_sql(question, pruned_schema)

        # ---- Stage 3: execution check + bounded repair ----------------
        return self._execute_and_repair(question, pruned_schema, sql, max_rounds=3)

    # ------------------------------------------------------------------ #
    # LLM wrapper
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            resp = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            resp = self.llm(prompt, system=system, temperature=temperature)
        if isinstance(resp, (list, tuple)):
            resp = resp[0] if resp else ""
        return resp if isinstance(resp, str) else str(resp)

    # ------------------------------------------------------------------ #
    # schema parsing
    # ------------------------------------------------------------------ #
    def _parse_schema(self, schema_text: str) -> dict:
        """Return {table_name: {"columns": [...], "block": original DDL text}}."""
        tables = {}
        if not schema_text:
            return tables

        pattern = re.compile(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`"\[\]\w. ]+?)\s*\(',
            re.IGNORECASE,
        )
        for m in pattern.finditer(schema_text):
            raw = m.group(1).strip().strip('`"[] ')
            name = raw.split(".")[-1].strip().strip('`"[] ')
            if not name:
                continue
            open_idx = m.end() - 1  # position of the opening '('
            depth = 0
            close_idx = len(schema_text) - 1
            for i in range(open_idx, len(schema_text)):
                ch = schema_text[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        close_idx = i
                        break
            body = schema_text[open_idx + 1:close_idx]
            block_end = close_idx + 1
            semi = schema_text.find(";", block_end, block_end + 16)
            if semi != -1:
                block_end = semi + 1
            block = schema_text[m.start():block_end].strip()

            columns = []
            for part in self._split_top_level(body):
                part = part.strip()
                if not part:
                    continue
                ident = self._first_identifier(part)
                if not ident or ident.lower() in self._CONSTRAINT_WORDS:
                    continue
                columns.append(ident)

            if name.lower() not in {t.lower() for t in tables}:
                tables[name] = {"columns": columns, "block": block}

        if tables:
            return tables

        # Fallback for line-oriented schemas: "table(col1, col2)" or "table: col1, col2"
        for line in schema_text.splitlines():
            line = line.strip().rstrip(";")
            if not line or line.startswith(("--", "#", "/*")):
                continue
            m = re.match(r'^[`"\[]?(\w+)[`"\]]?\s*\(([^()]*)\)$', line)
            if not m:
                m = re.match(r'^[`"\[]?(\w+)[`"\]]?\s*:\s*(.+)$', line)
            if m:
                name = m.group(1)
                cols = [c.strip().strip('`"[]') for c in m.group(2).split(",") if c.strip()]
                tables.setdefault(name, {"columns": cols, "block": line})
        return tables

    @staticmethod
    def _split_top_level(text: str) -> list:
        """Split on commas that are not nested inside parentheses."""
        parts, depth, cur = [], 0, []
        for ch in text:
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
        return parts

    @staticmethod
    def _first_identifier(definition: str) -> str:
        definition = definition.strip()
        if not definition:
            return ""
        for pat in (r'^"([^"]+)"', r"^`([^`]+)`", r"^\[([^\]]+)\]"):
            m = re.match(pat, definition)
            if m:
                return m.group(1).strip()
        return definition.split(None, 1)[0].strip('`"[]')

    # ------------------------------------------------------------------ #
    # Stage 1: schema linking
    # ------------------------------------------------------------------ #
    def _link_schema(self, question: str, schema_obj: dict) -> dict:
        """Return {table_name: set(relevant_columns)} for tables deemed relevant."""
        if not schema_obj:
            return {}
        catalog = "\n".join(
            f"- {t} ({', '.join(meta['columns'])})" for t, meta in schema_obj.items()
        )
        system = "You are a precise database schema-linking assistant."
        prompt = (
            "Identify exactly which tables and columns of the database are needed to "
            "answer the natural-language question with a SQL query. Include tables "
            "needed for joins even if they are not explicitly named.\n\n"
            f"### Schema\n{catalog}\n\n"
            f"### Question\n{question}\n\n"
            "Respond ONLY in this format:\n"
            "TABLES: table1, table2\n"
            "COLUMNS: table1.columnA, table2.columnB\n"
        )
        response = self._ask(prompt, system=system, temperature=0.0)

        linked = self._parse_linking_response(response, schema_obj)
        # union with deterministic lexical mentions found directly in the question
        for t, cols in self._direct_mentions(question, schema_obj).items():
            linked.setdefault(t, set()).update(cols)
        return linked

    def _parse_linking_response(self, response: str, schema_obj: dict) -> dict:
        linked = {}
        if not response:
            return linked
        canon_tables = {t.lower(): t for t in schema_obj}
        canon_cols = {}
        for t, meta in schema_obj.items():
            for c in meta["columns"]:
                canon_cols.setdefault(c.lower(), (t, c))

        def add_table(tkey):
            tname = canon_tables.get(tkey)
            if tname:
                linked.setdefault(tname, set())

        def add_column(tkey, ckey):
            tname = canon_tables.get(tkey)
            if not tname:
                return
            entry = linked.setdefault(tname, set())
            for col in schema_obj[tname]["columns"]:
                if col.lower() == ckey:
                    entry.add(col)

        # (a) structured "TABLES:" / "COLUMNS:" lines
        for line in response.splitlines():
            m = re.match(r"(?i)\s*tables?\s*[:\-]\s*(.+?)\s*$", line)
            if m:
                for tok in re.split(r"[,;]", m.group(1)):
                    add_table(tok.strip().strip('`"[]').lower())
                continue
            m = re.match(r"(?i)\s*columns?\s*[:\-]\s*(.+?)\s*$", line)
            if m:
                for tok in re.split(r"[,;]", m.group(1)):
                    tok = tok.strip().strip('`"[]')
                    if "." in tok:
                        t, c = tok.rsplit(".", 1)
                        add_column(t.strip().strip('`"[]').lower(),
                                   c.strip().strip('`"[]').lower())
                    else:
                        hit = canon_cols.get(tok.lower())
                        if hit:
                            tname, col = hit
                            linked.setdefault(tname, set()).add(col)

        # (b) inline table.column mentions anywhere in the text
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\b", response):
            add_column(m.group(1).lower(), m.group(2).lower())

        # (c) bare table names mentioned anywhere in the text
        low = response.lower()
        for tkey, tname in canon_tables.items():
            if re.search(r"(?<![\w])" + re.escape(tkey) + r"(?![\w])", low):
                linked.setdefault(tname, set())
        return linked

    def _direct_mentions(self, question: str, schema_obj: dict) -> dict:
        """Deterministic linker: tables/columns whose (de-underscored) names literally
        appear in the question. Guards against a malformed LLM linking response."""
        linked = {}
        q = question.lower()

        def mentioned(name):
            variants = {name.lower(), name.lower().replace("_", " ")}
            return any(
                v and re.search(r"(?<![\w])" + re.escape(v) + r"(?![\w])", q)
                for v in variants
            )

        for tname, meta in schema_obj.items():
            if mentioned(tname):
                linked.setdefault(tname, set())
            for col in meta["columns"]:
                cl = col.lower()
                if cl in self._COLUMN_STOPWORDS or len(cl) < 4:
                    continue
                if mentioned(col):
                    linked.setdefault(tname, set()).add(col)
        return linked

    def _build_pruned_schema(self, schema_obj: dict, linked: dict) -> str:
        """Materialize the linked subset; fall back to the full schema if linking
        produced nothing usable."""
        if not schema_obj:
            return self.schema
        blocks = []
        for tname in linked:
            meta = schema_obj.get(tname)
            if meta is None:
                continue
            block = meta["block"].rstrip()
            cols = sorted(linked[tname])
            if cols:
                block += f"\n-- linker-highlighted columns: {', '.join(cols)}"
            blocks.append(block)
        if not blocks:
            return self.schema
        text = "-- schema subset selected by the schema-linking stage\n" + "\n\n".join(blocks)
        omitted = [t for t in schema_obj if t not in linked]
        if omitted:
            text += "\n-- tables omitted as irrelevant by schema linking: " + ", ".join(omitted)
        return text

    # ------------------------------------------------------------------ #
    # Stage 2: SQL generation against the linked subset
    # ------------------------------------------------------------------ #
    def _generate_sql(self, question: str, schema_text: str, error_hint: str = "") -> str:
        system = (
            "You are an expert Text-to-SQL engine. You answer with exactly one "
            "syntactically valid SQL query and nothing else."
        )
        prompt = (
            "The database schema below has ALREADY been reduced by a schema-linking "
            "step to the tables/columns relevant to the question. Use ONLY these "
            "tables and columns; do not reference anything else.\n\n"
            f"### Linked schema\n{schema_text}\n\n"
            f"### Question\n{question}\n\n"
        )
        if error_hint:
            prompt += f"### Repair context\n{error_hint}\n\n"
        prompt += "### Task\nWrite the single SQL query that answers the question. Output SQL only."

        raw = self._ask(prompt, system=system, temperature=0.0)
        try:
            sql = bridge.extract_sql(raw) or ""
        except Exception:
            sql = ""
        if not sql.strip():
            sql = self._fallback_extract(raw)
        return sql.strip()

    @staticmethod
    def _fallback_extract(text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        m = re.search(r"