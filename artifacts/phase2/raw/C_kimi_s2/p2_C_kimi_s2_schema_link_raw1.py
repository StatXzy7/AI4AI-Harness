"""Link the question to schema tables/columns, prune the schema to that linked subset, then generate SQL against it with execution-checked repair."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CKimiS2SchemaLink"]


class P2P2CKimiS2SchemaLink(SQLHarness):
    """Schema-link-then-generate harness around the frozen weak solver.

    Stage 1 (link, in control flow): parse ``self.schema`` into
    tables/columns and keep only those lexically mentioned by the question
    (word / multi-word-phrase matching with simple singular/plural
    variants), always retaining key columns and foreign-key hints so joins
    remain expressible on the pruned subset.

    Stage 2 (generate): prompt the frozen LLM for SQL against the *linked
    subset only*, extract it with ``bridge.extract_sql``, reject queries
    that reference non-linked tables, verify them with ``self.execute`` and
    repair with error feedback.  If the linked subset cannot produce a
    valid query, fall back to the full schema so a best-effort answer is
    always returned.
    """

    _SYSTEM = (
        "You are a meticulous text-to-SQL engine. Given a database schema and "
        "a natural-language question, write exactly one SQL query that answers "
        "the question. Use only the tables and columns shown in the schema. "
        "Return the SQL query and nothing else."
    )

    _MAX_ATTEMPTS = 3      # generation + repair rounds per schema view
    _MIN_TOKEN_LEN = 3     # shorter name tokens match only as exact words

    _CREATE_TABLE_RE = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'["`\[]?(?P<name>[A-Za-z0-9_]+)["`\]]?\s*'
        r'\((?P<body>.*?)\)\s*;',
        re.IGNORECASE | re.DOTALL,
    )
    _FK_RE = re.compile(
        r'FOREIGN\s+KEY\s*\((?P<cols>[^)]*)\)\s*REFERENCES\s+'
        r'["`\[]?(?P<table>[A-Za-z0-9_]+)["`\]]?\s*\((?P<rcols>[^)]*)\)',
        re.IGNORECASE,
    )
    _INLINE_REF_RE = re.compile(
        r'\bREFERENCES\s+["`\[]?(?P<table>[A-Za-z0-9_]+)["`\]]?'
        r'(?:\s*\((?P<col>[^)]*)\))?',
        re.IGNORECASE,
    )
    _TABLE_CONSTRAINT_WORDS = {
        "primary", "foreign", "unique", "key", "constraint", "check", "index",
    }
    _REF_TABLE_RE = re.compile(
        r'\b(?:FROM|JOIN|UPDATE|INTO)\s+["`\[]?([A-Za-z0-9_]+)["`\]]?',
        re.IGNORECASE,
    )
    _CTE_RE = re.compile(r"([A-Za-z0-9_]+)\s+AS\s*\(", re.IGNORECASE)

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        """Link question-mentioned tables/columns, then write SQL on them."""
        tables = self._parse_schema()

        if tables:
            # Stage 1 + 2: generate against the linked subset.
            linked_names, linked_schema = self._link_schema(question, tables)
            sql_linked, ok_linked = self._generate_verified(
                question, linked_schema, allowed_tables=set(linked_names),
            )
            if ok_linked:
                return sql_linked

            # Safety net: the linked subset was too restrictive for the weak
            # solver, so retry against the complete schema.
            sql_full, ok_full = self._generate_verified(
                question, self.schema, allowed_tables=set(tables),
            )
            if ok_full:
                return sql_full
            best = sql_full or sql_linked
            if best:
                return best

        # Last resort (schema not parseable or all attempts empty): one shot.
        raw = self._ask(self._prompt(self.schema, question))
        return bridge.extract_sql(raw) or raw.strip()

    # ------------------------------------------------------- schema parsing

    def _parse_schema(self):
        """Parse CREATE TABLE statements into {lower_name: table_info}."""
        tables = {}
        for match in self._CREATE_TABLE_RE.finditer(self.schema or ""):
            name = match.group("name")
            info = {
                "name": name,
                "columns": [],  # list[(column_name, column_type)]
                "keys": set(),  # lower-case PK/FK column names
                "fks": [],      # list[(column, ref_table, ref_column)]
            }
            for item in self._split_top_level(match.group("body")):
                self._parse_column_or_constraint(item, info)
            if info["columns"]:
                tables[name.lower()] = info
        return tables

    def _parse_column_or_constraint(self, item, info):
        if not item:
            return
        first = item.split(None, 1)[0].strip('"`[]').lower() if item.split() else ""
        if first in self._TABLE_CONSTRAINT_WORDS:
            fk = self._FK_RE.search(item)
            if fk:
                cols = [c.strip().strip('"`[]') for c in fk.group("cols").split(",")]
                rcols = [c.strip().strip('"`[]') for c in fk.group("rcols").split(",")]
                for i, col in enumerate(cols):
                    rcol = rcols[i] if i < len(rcols) else ""
                    info["keys"].add(col.lower())
                    info["fks"].append((col, fk.group("table"), rcol))
            for par in re.findall(r"\(([^)]*)\)", item):
                for tok in par.split(","):
                    tok = tok.strip().strip('"`[]')
                    if re.fullmatch(r"[A-Za-z0-9_]+", tok):
                        info["keys"].add(tok.lower())
            return
        parts = item.split(None, 1)
        col_name = parts[0].strip('"`[]')
        rest = parts[1] if len(parts) > 1 else ""
        col_type = re.split(
            r"\b(?:PRIMARY|NOT|NULL|DEFAULT|UNIQUE|CHECK|REFERENCES|COLLATE"
            r"|AUTOINCREMENT|CONSTRAINT)\b",
            rest, maxsplit=1, flags=re.IGNORECASE,
        )[0].strip()
        info["columns"].append((col_name, col_type))
        if re.search(r"\bPRIMARY\s+KEY\b", item, re.IGNORECASE):
            info["keys"].add(col_name.lower())
        ref = self._INLINE_REF_RE.search(item)
        if ref:
            info["keys"].add(col_name.lower())
            info["fks"].append(
                (col_name, ref.group("table"),
                 (ref.group("col") or "").strip().strip('"`[]'))
            )

    @staticmethod
    def _split_top_level(text):
        """Split a CREATE TABLE body on top-level commas only."""
        parts, buf, depth, quote = [], [], 0, None
        for ch in text:
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
            elif ch in ("'", '"', '`'):
                quote = ch
                buf.append(ch)
            elif ch == "(":
                depth += 1
                buf.append(ch)
            elif ch == ")":
                depth = max(0, depth - 1)
                buf.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        tail = "".join(buf).strip()
        if tail:
            parts.append(tail)
        return [p for p in parts if p]

    # -------------------------------------------------------------- linking

    def _link_schema(self, question, tables):
        """Select question-mentioned tables/columns; render the subset DDL."""
        q_text = question.lower()
        q_tokens = set(re.findall(r"[a-z0-9]+", q_text))

        col_hits, table_score = {}, {}
        for key, info in tables.items():
            hits = {}
            for col_name, _ in info["columns"]:
                score = self._mention_score(col_name, q_text, q_tokens)
                if score > 0:
                    hits[col_name.lower()] = score
            col_hits[key] = hits
            # A table is linked if its name is mentioned or any column is.
            table_score[key] = (
                self._mention_score(info["name"], q_text, q_tokens)
                + 0.5 * len(hits)
            )

        linked = [k for k in tables if table_score[k] > 0] or list(tables)

        keep = {}
        for key in linked:
            info = tables[key]
            cols = {c.lower() for c, _ in info["columns"]}
            # Mentioned columns plus key columns (needed for joins); if the
            # table matched but no column did, keep the whole table.
            selected = (set(col_hits[key]) | (info["keys"] & cols)) or cols
            keep[key] = selected
        return linked, self._render_schema(tables, keep)

    def _mention_score(self, name, q_text, q_tokens):
        """Score how strongly `name` is mentioned in the question (0 = not)."""
        lname = name.lower()
        score = 0
        phrase = lname.replace("_", " ").strip()
        if len(phrase) >= 2 and re.search(r"\b%s\b" % re.escape(phrase), q_text):
            score += 3
        for tok in re.split(r"[_\s]+", lname):
            if not tok:
                continue
            if tok in q_tokens:
                score += 2 if len(tok) >= self._MIN_TOKEN_LEN else 1
            elif len(tok) >= self._MIN_TOKEN_LEN and self._variants(tok) & q_tokens:
                score += 1
        return score

    @staticmethod
    def _variants(token):
        """Crude singular/plural variants of a name token."""
        out = {token}
        if token.endswith("ies") and len(token) > 4:
            out.add(token[:-3] + "y")
        if token.endswith("es") and len(token) > 3:
            out.add(token[:-2])
        if token.endswith("s") and len(token) > 2:
            out.add(token[:-1])
        if not token.endswith("s"):
            out.add(token + "s")
        return out

    def _render_schema(self, tables, keep):
        """Render the linked subset as CREATE TABLE DDL with key/FK hints."""
        blocks = []
        for key, cols in keep.items():
            info = tables[key]
            lines = []
            for col_name, col_type in info["columns"]:
                if col_name.lower() not in cols:
                    continue
                lines.append("    " + col_name + (" " + col_type if col_type else ""))
            if not lines:
                continue
            block = "CREATE TABLE {} (\n{}\n);".format(info["name"], ",\n".join(lines))
            notes = []
            key_cols = [c for c, _ in info["columns"]
                        if c.lower() in info["keys"] and c.lower() in cols]
            if key_cols:
                notes.append("-- key columns of {}: {}".format(
                    info["name"], ", ".join(key_cols)))
            for col, ref_table, ref_col in info["fks"]:
                if col.lower() in cols:
                    notes.append("-- {}.{} references {}({})".format(