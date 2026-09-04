"""Harness that first schema-links the question to the relevant tables/columns (heuristic token matching fused with one solver linking pass, then foreign-key expansion) and afterwards generates SQL against only that linked subset, with a single execution-based repair pass."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1SchemaLink(SQLHarness):
    """P2P2C two-stage pipeline over the frozen solver (Kimi-S1 style).

    The strategy lives in the control flow, not only in the prompts:

    Stage 1 (LINK):  parse ``self.schema`` into tables/columns, then
        (a) match question tokens/phrases against every table and column
            name (with plural / camelCase / snake_case normalisation), and
        (b) ask the frozen solver to list the needed ``table.column`` items.
        Fuse both link sets and expand one hop along foreign keys so that
        joins remain expressible.
    Stage 2 (CODE):  re-prompt the frozen solver with ONLY the DDL of the
        linked subset plus the question, then extract the SQL.
    Stage 3 (CHECK): execute once; on database error, issue exactly one
        corrective re-prompt still restricted to the linked subset.
    """

    _CONSTRAINT_WORDS = {
        "primary", "foreign", "unique", "check", "constraint",
        "key", "index", "like", "exclude",
    }
    _LOOSE_HEADER_WORDS = {
        "table", "tables", "column", "columns", "schema", "database",
    }

    _CREATE_TABLE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"[\"'`\[]?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)[\"'`\]]?\s*\(",
        re.IGNORECASE,
    )
    _REF_RE = re.compile(
        r"REFERENCES\s+[\"'`\[]?([A-Za-z_][\w$]*)", re.IGNORECASE
    )
    _COL_RE = re.compile(r"^[\"'`\[]?([A-Za-z_][\w$]*)[\"'`\]]?")
    _DOTTED_RE = re.compile(r"\b([A-Za-z_][\w$]*)\s*\.\s*([A-Za-z_][\w$]*|\*)")
    _WORD_RE = re.compile(r"[A-Za-z_][\w$]*")
    _NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
    _CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

    # ------------------------------------------------------------------ #
    # entry point                                                         #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        model = self._parse_schema(self.schema or "")

        # ---- Stage 1: schema linking, done in the control flow ----
        if model:
            heuristic = self._heuristic_link(question, model)
            solver_links = self._solver_link(question, model)
            linked_tables = self._fuse_and_expand(heuristic, solver_links, model)
            linked_schema = self._render_linked_schema(model, linked_tables)
        else:
            linked_schema = self.schema  # unparseable schema: keep it whole

        # ---- Stage 2: SQL written against the linked subset only ----
        sql = self._generate_sql(question, linked_schema)

        # ---- Stage 3: execute once; a single repair attempt on failure ----
        result = self.execute(sql)
        if not result.get("ok"):
            repaired = self._repair_sql(
                question, linked_schema, sql, result.get("error", "")
            )
            if repaired and repaired != sql:
                retry = self.execute(repaired)
                if retry.get("ok"):
                    sql = repaired
        return sql

    # ------------------------------------------------------------------ #
    # Stage 1a: schema parsing                                            #
    # ------------------------------------------------------------------ #

    def _parse_schema(self, schema_text):
        """Build {table_lower: {name, columns{col_lower: col}, refs, raw}}."""
        model = {}
        for name, body, raw in self._iter_create_tables(schema_text):
            columns, refs = self._parse_table_body(body)
            model[name.lower()] = {
                "name": name,
                "columns": columns,
                "refs": refs,
                "raw": raw.strip(),
            }
        if not model:
            model = self._parse_loose_schema(schema_text)
        # inferred references from "<table>_id" columns (helps loose schemas)
        for tkey, info in model.items():
            for ckey in info["columns"]:
                if ckey.endswith("_id") and len(ckey) > 3:
                    base = ckey[:-3]
                    for cand in (base, base + "s", base + "es"):
                        if cand in model and cand != tkey:
                            info["refs"].add(cand)
        return model

    def _iter_create_tables(self, text):
        """Yield (table_name, body_text, raw_ddl) with balanced-paren scan."""
        for m in self._CREATE_TABLE_RE.finditer(text):
            name = m.group(1).split(".")[-1]
            depth, j = 1, m.end()
            while j < len(text) and depth:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                j += 1
            body = text[m.end():j - 1]
            k = j
            while k < len(text) and text[k] != ";":
                k += 1
            raw = text[m.start():k + 1] if k < len(text) else text[m.start():j]
            yield name, body, raw

    def _parse_table_body(self, body):
        columns, refs = {}, set()
        for part in self._split_top_level(body):
            m = self._COL_RE.match(part)
            if not m:
                continue
            first = m.group(1)
            if first.lower() in self._CONSTRAINT_WORDS:
                for r in self._REF_RE.findall(part):  # table-level FOREIGN KEY
                    refs.add(r.lower())
                continue
            columns[first.lower()] = first
            for r in self._REF_RE.findall(part):      # inline ... REFERENCES t
                refs.add(r.lower())
        return columns, refs

    def _split_top_level(self, body):
        parts, buf, depth = [], [], 0
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        if buf:
            parts.append("".join(buf))
        return [p.strip() for p in parts if p.strip()]

    def _parse_loose_schema(self, text):
        """Fallback for 'table(col, col)' or 'table: col, col' line formats."""
        model = {}
        line_re = re.compile(
            r"^\s*(?:table\s+)?[\"'`]?([A-Za-z_][\w$]*)[\"'`]?\s*"
            r"(?:\(([^)]*)\)|[:=]\s*(.+?))\s*$",
            re.IGNORECASE,
        )
        for line in text.splitlines():
            m = line_re.match(line)
            if not m:
                continue
            name = m.group(1)
            if name.lower() in self._LOOSE_HEADER_WORDS:
                continue
            blob = m.group(2) if m.group(2) is not None else m.group(3)
            columns = {}
            for piece in blob.split(","):
                cm = self._COL_RE.match(piece.strip())
                if cm:
                    columns[cm.group(1).lower()] = cm.group(1)
            if columns:
                model[name.lower()] = {
                    "name": name,
                    "columns": columns,
                    "refs": set(),
                    "raw": line.strip(),
                }
        return model

    # ------------------------------------------------------------------ #
    # Stage 1b: heuristic linking of question tokens to schema names      #
    # ------------------------------------------------------------------ #

    def _heuristic_link(self, question, model):
        q_space = " " + self._NON_ALNUM_RE.sub(" ", question.lower()) + " "
        tables, columns = set(), set()
        for tkey, info in model.items():
            if self._name_mentioned(info["name"], q_space):
                tables.add(tkey)
            for ckey, corig in info["columns"].items():
                if self._name_mentioned(corig, q_space):
                    columns.add((tkey, ckey))
                    tables.add(tkey)  # a mentioned column links its table
        return {"tables": tables, "columns": columns}

    def _name_mentioned(self, name, q_space):
        padded = q_space  # word-boundary matching via surrounding spaces
        for variant in self._name_variants(name):
            if " " + variant + " " in padded:
                return True
        return False

    def _name_variants(self, name):
        name = self._CAMEL_RE.sub(" ", name)            # orderItems -> order Items
        base = self._NON_ALNUM_RE.sub(" ", name.lower()).strip()
        words = base.split()
        variants = {base, base.replace(" ", "")}
        for i, w in enumerate(words):
            for s in self._singulars(w):
                variants.add(" ".join(words[:i] + [s] + words[i + 1:]))
        return {v for v in variants if len(v) >= 2}

    @staticmethod
    def _singulars(word):
        outs = set()
        if len(word) > 3 and word.endswith("s"):
            outs.add(word[:-1])
        if len(word) > 4 and word.endswith("ies"):
            outs.add(word[:-3] + "y")
        if len(word) > 3 and word.endswith("es"):
            outs.add(word[:-2])
        return outs

    # ------------------------------------------------------------------ #
    # Stage 1c: one solver pass that picks the needed table.column items  #
    # ------------------------------------------------------------------ #

    def _solver_link(self, question, model):
        catalog = [
            f"{info['name']}({', '.join(info['columns'].values())})"
            for info in model.values()
        ]
        prompt = (
            "Database catalog (table(columns)):\n"
            + "\n".join(catalog)
            + "\n\nQuestion: " + question
            + "\n\nList ONLY the tables and columns required to answer the "
            "question, one per line, in the form table_name.column_name "
            "(write table_name.* if every column of a table is needed). "
            "Do not explain."
        )
        response = self._ask(
            prompt,
            system="You are a meticulous schema-linking assistant for "
                   "Text-to-SQL. Output only table.column lines.",
        )
        return self._parse_link_response(response, model)

    def _parse_link_response(self, response, model):
        tables, columns = set(), set()
        for line in str(response).splitlines():
            dotted = self._DOTTED_RE.findall(line)
            if dotted:
                for t, c in dotted:
                    tl, cl = t.lower(), c.lower()
                    info = model.get(tl)
                    if info is None:
                        continue
                    tables.add(tl)
                    if cl == "*":
                        columns.update((tl, ck) for ck in info["columns"])
                    elif cl in info["columns"]:
                        columns.add((tl, cl))
            else:  # tolerate answers that name bare tables
                for tok in self._WORD_RE.findall(line):
                    if tok.lower() in model:
                        tables.add(tok.lower())
        return {"tables": tables, "columns": columns}

    # ------------------------------------------------------------------ #
    # Stage 1d: fuse link sets and expand along foreign keys              #
    # ------------------------------------------------------------------ #

    def _fuse_and_expand(self, heuristic, solver_links, model):
        linked = set(heuristic["tables"]) | set(solver_links["tables"])
        if not linked:
            return set(model)  # nothing linked: keep the full schema (safe)
        for tkey in list(linked):  # one hop, forward direction only
            for ref in model[tkey]["refs"]:
                if ref in model:
                    linked.add(ref)
        return linked

    def _render_linked_schema(self, model, linked_tables):
        chunks = [info["raw"] for key, info in model.items()
                  if key in linked_tables]
        if not chunks:
            return self.schema
        header = (
            "-- Schema subset chosen by schema linking "
            f"({len(chunks)} of {len(model)} tables)."
        )
        return header + "\n\n" + "\n\n".join(chunks)

    # ------------------------------------------------------------------ #
    # Stage 2: constrained SQL generation                                 #
    # ------------------------------------------------------------------ #

    def _generate_sql(self, question, linked_schema):
        prompt = (
            "The following DDL is the schema subset that schema linking "
            "identified as relevant. Use ONLY these tables and columns.\n\n"
            f"{linked_schema}\n\n"
            f"Question: {question}\n\n"
            "Write one syntactically valid SQL query that answers the "
            "question. Output only the SQL."
        )
        response = self._ask(
            prompt,
            system="You are an expert Text-to-SQL engine. Given a linked "
                   "schema subset and a question, output exactly one SQL "
                   "query and nothing else.",
        )
        sql = bridge.extract_sql(response)
        return sql if sql else str(response).strip()

    # ------------------------------------------------------------------ #
    # Stage 3: single execution-based repair, still on the linked subset  #
    # ------------------------------------------------------------------ #

    def _repair_sql(self, question, linked_schema, bad_sql, error):
        prompt = (
            "The following SQL query failed against the linked schema "
            "subset.\n\n"
            f"{linked_schema}\n\n"
            f"Question: {question}\n"
            f"Failing SQL:\n{bad_sql}\n"
            f"Database error: {error}\n\n"
            "Rewrite the query so it executes correctly, still using ONLY "
            "the tables and columns above. Output only the corrected SQL."
        )
        response = self._ask(
            prompt,
            system="You are an expert SQL debugger. Output only the fixed "
                   "SQL query.",
        )
        return bridge.extract_sql(response) or ""

    # ------------------------------------------------------------------ #
    # frozen-solver call wrapper                                          #
    # ------------------------------------------------------------------ #

    def _ask(self, prompt, system=""):
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        return response if isinstance(response, str) else str(response)