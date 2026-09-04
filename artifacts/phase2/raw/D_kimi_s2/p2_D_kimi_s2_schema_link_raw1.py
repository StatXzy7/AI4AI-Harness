"""Two-stage Text-to-SQL harness: the LLM first schema-links the question to the relevant tables/columns, the schema is pruned to that linked subset (primary/foreign keys retained for joinability), SQL is generated against the subset, and a bounded execution-feedback loop repairs failures (escalating to the full schema if linking pruned too aggressively)."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2SchemaLink(SQLHarness):
    """Stage 1: LLM-based schema linking over the full schema.
    Stage 2: SQL generation constrained to the linked subset only.
    Stage 3: bounded execution-feedback repair with full-schema escalation.
    """

    MAX_REPAIRS = 2

    _CREATE_TABLE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"[\"'`\[]?([\w$. ]+)[\"'`\]]?\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    _CONSTRAINT_HEADS = {
        "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT", "KEY", "INDEX",
    }

    # ------------------------------------------------------------------ #
    # main pipeline
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        schema_map = self._parse_schema(self.schema)

        # ---- Stage 1: identify the tables/columns the question mentions.
        linked = self._link_schema(question, schema_map)
        working_schema = self._render_schema(schema_map, linked)

        # ---- Stage 2: write SQL against the linked subset.
        sql = self._generate_sql(question, working_schema)

        # ---- Stage 3: execute + bounded repair.
        return self._repair_loop(question, working_schema, sql)

    # ------------------------------------------------------------------ #
    # schema parsing
    # ------------------------------------------------------------------ #
    def _parse_schema(self, schema_text):
        """Return {table: {"columns": [(col, raw_def)], "pk", "fk_cols", "fks"}}."""
        tables = {}
        text = schema_text or ""
        for m in self._CREATE_TABLE_RE.finditer(text):
            name = m.group(1).strip()
            info = {"columns": [], "pk": set(), "fk_cols": set(), "fks": []}
            for part in self._split_top_level(m.group(2)):
                part = part.strip()
                if not part:
                    continue
                hm = re.match(r"[\"'`\[]?(\w+)", part)
                head = hm.group(1).upper() if hm else ""
                if head in self._CONSTRAINT_HEADS:
                    pm = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", part, re.IGNORECASE)
                    if pm:
                        info["pk"].update(self._split_names(pm.group(1)))
                    fm = re.search(
                        r"FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+"
                        r"[\"'`\[]?([\w$. ]+)[\"'`\]]?\s*(?:\(([^)]*)\))?",
                        part, re.IGNORECASE,
                    )
                    if fm:
                        locals_ = self._split_names(fm.group(1))
                        ref_cols = self._split_names(fm.group(3) or "")
                        info["fk_cols"].update(locals_)
                        for i, lc in enumerate(locals_):
                            info["fks"].append(
                                (lc, fm.group(2).strip(),
                                 ref_cols[i] if i < len(ref_cols) else "")
                            )
                    continue
                cm = re.match(r"[\"'`\[]?([\w$ ]+)[\"'`\]]?", part)
                if not cm:
                    continue
                col = cm.group(1).strip()
                if not col:
                    continue
                info["columns"].append((col, part))
                up = part.upper()
                if "PRIMARY KEY" in up:
                    info["pk"].add(col)
                rm = re.search(
                    r"REFERENCES\s+[\"'`\[]?([\w$. ]+)[\"'`\]]?"
                    r"\s*(?:\(\s*[\"'`\[]?([\w$ ]+)[\"'`\]]?\s*\))?",
                    part, re.IGNORECASE,
                )
                if rm:
                    info["fk_cols"].add(col)
                    info["fks"].append((col, rm.group(1).strip(),
                                        (rm.group(2) or "").strip()))
            if info["columns"]:
                tables[name] = info
        if not tables:
            tables = self._parse_loose_schema(text)
        return tables

    @staticmethod
    def _split_top_level(text):
        parts, depth, buf = [], 0, []
        for ch in text:
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
        return parts

    @staticmethod
    def _split_names(text):
        return [c.strip().strip("\"'`[]") for c in (text or "").split(",")
                if c.strip()]

    def _parse_loose_schema(self, text):
        """Fallback for non-DDL listings such as 'table(col1, col2)'."""
        tables = {}
        for line in text.splitlines():
            line = line.strip().lstrip("-*").strip().rstrip(";")
            if not line:
                continue
            m = re.match(r"^[\"'`]?([\w$]+(?: [\w$]+)?)[\"'`]?\s*\(([^()]*)\)$", line)
            if not m:
                m = re.match(r"^(\w+)\s*:\s*(\w[^:]*)$", line)
            if not m:
                continue
            name = m.group(1).strip()
            cols = [c for c in self._split_names(m.group(2))
                    if re.match(r"^[\w$ ]+$", c)]
            if name and cols and ("(" in line or "," in m.group(2)):
                tables.setdefault(name, {
                    "columns": [(c, c) for c in cols],
                    "pk": set(), "fk_cols": set(), "fks": [],
                })
        return tables

    # ------------------------------------------------------------------ #
    # Stage 1: schema linking
    # ------------------------------------------------------------------ #
    def _link_schema(self, question, schema_map):
        """Ask the LLM which tables/columns the question needs; None = keep all."""
        if not schema_map:
            return None
        listing = "\n".join(
            "- {}({})".format(t, ", ".join(c for c, _ in info["columns"]))
            for t, info in schema_map.items()
        )
        system = ("You are a meticulous schema-linking component of a "
                  "Text-to-SQL system.")
        prompt = (
            "Full database schema (table(column, ...)):\n\n"
            + listing + "\n\n"
            + "Question: " + question + "\n\n"
            + "Select exactly the tables and columns needed to write a SQL "
              "query answering the question. Include columns used for "
              "filtering, joining, grouping, ordering and the output.\n"
              "Answer with ONLY a JSON object, no prose, no code fences:\n"
              + '{"tables": ["table_a", "table_b"], '
                '"columns": ["table_a.col1", "table_b.col2"]}'
        )
        try:
            raw = self._first(self.llm(prompt, system=system,
                                       temperature=0.0, n=1))
        except Exception:
            return None
        return self._parse_linking(raw, schema_map)

    def _parse_linking(self, text, schema_map):
        if not text:
            return None
        tables_lower = {t.lower(): t for t in schema_map}
        col_lower = {}
        for t, info in schema_map.items():
            for c, _ in info["columns"]:
                col_lower[(t.lower(), c.lower())] = c

        linked = {}

        def add_table(name):
            key = str(name).strip().strip("\"'`[]").lower()
            actual = tables_lower.get(key)
            if actual is None and "." in key:
                actual = tables_lower.get(key.rsplit(".", 1)[-1])
            if actual is not None:
                linked.setdefault(actual, set())
            return actual

        def add_col(tname, cname):
            at = add_table(tname)
            if at is None:
                return
            ac = col_lower.get((at.lower(),
                                str(cname).strip().strip("\"'`[]").lower()))
            if ac is not None:
                linked[at].add(ac)

        data = None
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
        if data is None:
            lm = re.search(r"\[.*\]", text, re.DOTALL)
            if lm:
                try:
                    data = json.loads(lm.group(0))
                except Exception:
                    data = None

        if isinstance(data, dict):
            t_list, c_list = [], []
            for k, v in data.items():
                if not isinstance(v, list):
                    continue
                lk = str(k).lower()
                if "table" in lk:
                    t_list.extend(v)
                elif any(w in lk for w in ("column", "field", "attribute", "col")):
                    c_list.extend(v)
            for t in t_list:
                add_table(t)
            for entry in c_list:
                s = str(entry).strip()
                if "." in s:
                    tt, cc = s.split(".", 1)
                    add_col(tt, cc)
                else:
                    self._attach_unqualified(s, linked, schema_map, col_lower)
        elif isinstance(data, list):
            for entry in data:
                s = str(entry).strip()
                if "." in s:
                    tt, cc = s.split(".", 1)
                    add_col(tt, cc)
                elif s.strip("\"'`[]").lower() in tables_lower:
                    add_table(s)
                else:
                    self._attach_unqualified(s, linked, schema_map, col_lower)
        else:
            # Last-resort: scan the raw response for known schema names.
            for tl, at in tables_lower.items():
                if re.search(r"(?<![\w$])" + re.escape(tl) + r"(?![\w$])",
                             text, re.IGNORECASE):
                    linked.setdefault(at, set())
            for t in list(linked):
                for c, _ in schema_map[t]["columns"]:
                    if re.search(r"(?<![\w$])" + re.escape(c.lower()) + r"(?![\w$])",
                                 text, re.IGNORECASE):
                        linked[t].add(c)

        linked = {t: cs for t, cs in linked.items() if t in schema_map}
        if not linked:
            return None
        # A table named with no specific column keeps all of its columns.
        for t, cs in list(linked.items()):
            if not cs:
                linked[t] = {c for c, _ in schema_map[t]["columns"]}
        return linked

    @staticmethod
    def _attach_unqualified(cname, linked, schema_map, col_lower):
        ck = str(cname).strip().strip("\"'`[]").lower()
        hits = [t for t in schema_map if (t.lower(), ck) in col_lower]
        pref = [t for t in hits if t in linked]
        chosen = pref[0] if pref else (hits[0] if len(hits) == 1 else None)
        if chosen is not None:
            linked.setdefault(chosen, set()).add(col_lower[(chosen.lower(), ck)])

    # ------------------------------------------------------------------ #
    # pruned-schema rendering
    # ------------------------------------------------------------------ #
    def _render_schema(self, schema_map, linked):
        """Rebuild DDL for the linked subset; always retain PK/FK columns."""
        if not schema_map or not linked:
            return self.schema or ""
        chunks, rels = [], []
        for t, info in schema_map.items():
            if t not in linked:
                continue
            keep = set(linked[t]) | info["pk"] | info["fk_cols"]
            lines = [raw for c, raw in info["columns"] if c in keep]
            if not lines:
                lines = [raw for _, raw in info["columns"]]
            chunks.append('CREATE TABLE "{}" (\n  {}\n);'.format(
                t, ",\n  ".join(lines)))
            for a, rt, rc in info["fks"]:
                rels.append("{}.{} = {}.{}".format(t, a, rt, rc or "?"))
        if not chunks:
            return self.schema or ""
        out = "\n\n".join(chunks)
        if rels:
            out += "\n\n-- join hints (foreign keys): " + "; ".join(rels)
        return out

    # ------------------------------------------------------------------ #
    # Stage 2: SQL generation against the linked subset
    # ------------------------------------------------------------------ #
    def _generate_sql(self, question, schema_text):
        system = "You are an expert SQLite query writer. Output only SQL."
        prompt = (
            "You are given the subset of a SQLite database schema that has "
            "been linked to the question. Write a single SQL query answering "
            "the question using ONLY these tables and columns.\n\n"
            "Relevant schema:\n" + (schema_text or "No schema available.")
            + "\n\nQuestion: " + question + "\n\n"
            "Rules:\n"
            "- Use only tables/columns shown above.\n"
            "- Return one SQL statement; no explanation, no markdown fences."
        )
        try:
            raw = self._first(self.llm(prompt, system=system,
                                       temperature=0.0, n=1))
        except Exception:
            return ""
        return self._to_sql(raw)

    # ------------------------------------------------------------------ #
    # Stage 3: execution-feedback repair
    # ------------------------------------------------------------------ #
    def _repair_loop(self, question, working_schema, sql):
        current = sql
        schema_in_use = working_schema
        full_schema = self.schema or working_schema
        for _ in range(self.MAX_REPAIRS + 1):
            if not current:
                return current
            try:
                res = self.execute(current)
            except Exception as exc:  # defensive: treat harness errors as DB errors
                res = {"ok": False, "rows": [], "error": str(exc)}
            if isinstance(res, dict) and res.get("ok"):
                return current
            err = (res.get("error") if isinstance(res, dict) else None) \
                or "unknown execution error"
            # Linking may have pruned a needed object -> escalate once.
            if "no such" in err.lower() and schema_in_use != full_schema:
                schema_in_use = full_schema
            fixed = self._fix_sql(question, schema_in_use, current, err)
            if not fixed or fixed == current:
                if schema_in_use != full_schema:
                    schema_in_use = full_schema
                    fixed = self._fix_sql(question, schema_in_use, current, err)
                if not fixed or fixed == current:
                    return current
            current = fixed
        return current

    def _fix_sql(self, question, schema_text, bad_sql, error):
        system = ("You are an expert SQLite query writer. "
                  "Output only the corrected SQL.")
        prompt = (
            "Schema:\n" + (schema_text or "No schema available.")
            + "\n\nQuestion: " + question
            + "\n\nThe following SQL failed:\n" + bad_sql
            + "\n\nDatabase error:\n" + error
            + "\n\nRewrite it as ONE corrected SQL statement using only "
              "schema objects above. No explanation, no markdown fences."
        )
        try:
            raw = self._first(self.llm(prompt, system=system,
                                       temperature=0.0, n=1))
        except Exception:
            return bad_sql
        return self._to_sql(raw) or bad_sql

    # ------------------------------------------------------------------ #
    # small utilities
    # ------------------------------------------------------------------ #
    @staticmethod
    def _first(resp):
        if isinstance(resp, (list, tuple)):
            return resp[0] if resp else ""
        return resp or ""

    @staticmethod
    def _to_sql(text):
        text = text or ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        if sql:
            return sql.strip()
        t = text.strip()
        t = re.sub(r"^