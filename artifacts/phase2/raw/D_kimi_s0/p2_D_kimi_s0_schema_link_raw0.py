"""Two-stage harness: LLM schema-linking first isolates the tables/columns mentioned in the question, then SQL is generated strictly against that linked subset (with control-flow enforcement and one execution-feedback repair)."""

import json
import re
from typing import Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0SchemaLink(SQLHarness):
    """Schema-link-then-generate Text-to-SQL harness.

    The strategy lives in the control flow, not only in prompts:
      1. Parse ``self.schema`` into ``{table: [(column, definition), ...]}``.
      2. STAGE A (schema linking): ask the LLM which tables/columns the
         question mentions, parsed back as JSON; fall back to lexical
         matching if the LLM output is unusable.
      3. Rebuild a pruned schema containing only the linked subset.
      4. STAGE B (generation): ask the LLM for SQL written against the
         pruned schema only; if the emitted SQL still touches an unlinked
         table, regenerate once with an explicit prohibition.
      5. Execute; on failure run exactly one repair round fed with the
         database error message, still restricted to the linked subset.
    """

    _LINK_SYSTEM = (
        "You are a precise schema-linking assistant for Text-to-SQL. "
        "Given a database schema and a natural-language question, you identify "
        "exactly the tables and columns needed to answer the question."
    )

    _SQL_SYSTEM = (
        "You are an expert Text-to-SQL translator. You write a single, correct, "
        "executable SQL query using only the tables and columns provided."
    )

    _CREATE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`\[]?(.+?)[\"'`\]]?\s*\((.*)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )

    _CONSTRAINT_HEADS = {
        "primary", "foreign", "unique", "key", "constraint",
        "check", "index", "like", "exclude",
    }

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        schema_map = self._parse_schema(self.schema)

        # ---- Stage A: schema linking (a control-flow step, not just a prompt).
        linked = self._link_schema(question, schema_map)
        pruned_schema = self._build_pruned_schema(schema_map, linked)

        # ---- Stage B: SQL generation against the linked subset only.
        raw = self._llm_text(self._sql_prompt(question, pruned_schema),
                             system=self._SQL_SYSTEM)
        sql = bridge.extract_sql(raw)

        # Control-flow enforcement: the SQL must not touch unlinked tables.
        offender = self._sql_uses_unlinked_table(sql, schema_map, linked)
        if offender is not None:
            retry = self._llm_text(
                self._sql_prompt(question, pruned_schema)
                + "\n- STRICT: never reference table `{}` or any table not shown above.".format(offender),
                system=self._SQL_SYSTEM,
            )
            sql_retry = bridge.extract_sql(retry)
            if sql_retry and self._sql_uses_unlinked_table(sql_retry, schema_map, linked) is None:
                sql = sql_retry

        # ---- Stage C: execute once; on error, one repair round with feedback.
        result = self._try_execute(sql)
        if not result.get("ok"):
            raw_fix = self._llm_text(
                self._repair_prompt(question, pruned_schema, sql, result.get("error", "")),
                system=self._SQL_SYSTEM,
            )
            fixed = bridge.extract_sql(raw_fix)
            if fixed:
                if self._try_execute(fixed).get("ok") or not sql:
                    sql = fixed

        return sql or raw.strip()

    # ------------------------------------------------------------- plumbing

    def _llm_text(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _try_execute(self, sql: str) -> Dict:
        try:
            return self.execute(sql)
        except Exception as exc:  # never let the harness crash
            return {"ok": False, "rows": [], "error": str(exc)}

    # --------------------------------------------------------- schema parse

    def _parse_schema(self, schema: str) -> Dict[str, List[Tuple[str, str]]]:
        tables: Dict[str, List[Tuple[str, str]]] = {}
        if not schema:
            return tables

        # Format 1: standard "CREATE TABLE name ( col type, ... );" blocks.
        for m in self._CREATE_RE.finditer(schema):
            name = m.group(1).strip().strip("\"'`[]").split(".")[-1].strip()
            cols: List[Tuple[str, str]] = []
            for chunk in self._split_top_level(m.group(2)):
                toks = chunk.split()
                head = toks[0].strip("\"'`[]") if toks else ""
                if not head or head.lower() in self._CONSTRAINT_HEADS:
                    continue
                cols.append((head, chunk))
            tables.setdefault(name, cols)

        # Format 2: "Table name, columns = [c1, c2, ...]" listings.
        if not tables:
            for m in re.finditer(
                r"Table\s+([A-Za-z_][\w]*)\s*,\s*columns\s*=\s*\[([^\]]*)\]",
                schema, re.IGNORECASE,
            ):
                name = m.group(1)
                cols = [
                    (c, c)
                    for c in (p.strip().strip("\"'`") for p in m.group(2).split(","))
                    if c and c != "*"
                ]
                tables.setdefault(name, cols)

        # Format 3: "# Table: name" headers followed by column lines.
        if not tables:
            current = None
            for line in schema.splitlines():
                tm = re.match(r"\s*#*\s*Table\s*:\s*([A-Za-z_][\w]*)", line, re.IGNORECASE)
                if tm:
                    current = tm.group(1)
                    tables.setdefault(current, [])
                    continue
                if current:
                    cm = re.match(r"\s*#?\s*[-*\(]?\s*([A-Za-z_][\w]*)", line)
                    if cm and cm.group(1).lower() not in ("table", "columns"):
                        c = cm.group(1)
                        tables[current].append((c, c))
        return tables

    @staticmethod
    def _split_top_level(body: str) -> List[str]:
        parts, depth, cur = [], 0, []
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
        if cur:
            parts.append("".join(cur))
        return [p.strip() for p in parts if p.strip()]

    # -------------------------------------------------------- schema linking

    def _link_schema(self, question: str,
                     schema_map: Dict[str, List[Tuple[str, str]]]) -> Dict[str, List[str]]:
        if not schema_map:
            return {}
        listing = "\n".join(
            "- {}: {}".format(t, ", ".join(n for n, _ in cols) or "(no columns parsed)")
            for t, cols in schema_map.items()
        )
        prompt = (
            "Database tables and columns:\n"
            + listing
            + "\n\nQuestion: " + question
            + "\n\nReturn ONLY a raw JSON object of the form:\n"
            + '{"tables": ["table_a"], "columns": {"table_a": ["col1", "col2"]}}\n'
            + "Rules:\n"
            "- Include every table/column needed, including join keys and columns used "
            "for filtering, grouping, or ordering.\n"
            "- Use the exact names from the listing above.\n"
            "- If a whole table is needed, list all of its columns.\n"
            "- No prose, no markdown fences, JSON only."
        )
        raw = self._llm_text(prompt, system=self._LINK_SYSTEM)
        linked = self._parse_linking_json(raw, schema_map)
        if not linked:
            linked = self._lexical_link(question, schema_map)
        return linked

    def _parse_linking_json(self, raw: str,
                            schema_map: Dict[str, List[Tuple[str, str]]]) -> Dict[str, List[str]]:
        if not raw:
            return {}
        data = None
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
        if data is None:
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    return {}
        if data is None:
            return {}

        canon_t = {t.lower(): t for t in schema_map}
        linked: Dict[str, List[str]] = {}

        def add_table(name, col_list=None):
            if name is None:
                return
            key = str(name).strip().strip("\"'`[]").split(".")[-1].lower()
            t = canon_t.get(key)
            if t is None:
                return
            if isinstance(col_list, str):
                col_list = None if col_list.strip() in ("", "*", "all") else [col_list]
            if isinstance(col_list, (list, tuple)) and col_list:
                canon_c = {c.lower(): c for c, _ in schema_map[t]}
                picked = set()
                for c in col_list:
                    ck = str(c).strip().strip("\"'`[]").split(".")[-1].lower()
                    if ck in canon_c:
                        picked.add(canon_c[ck])
                if picked:
                    keep = set(linked.get(t, [])) | picked
                    linked[t] = [c for c, _ in schema_map[t] if c in keep]
                    return
            linked.setdefault(t, [c for c, _ in schema_map[t]])

        if isinstance(data, dict):
            tables = data.get("tables", [])
            if isinstance(tables, str):
                tables = [tables]
            columns = data.get("columns", {})
            if not isinstance(columns, dict):
                columns = {}
            for t in tables or []:
                cols = None
                for k, v in columns.items():
                    if str(k).strip().strip("\"'`[]").lower() == str(t).strip().strip("\"'`[]").lower():
                        cols = v
                        break
                add_table(t, cols)
            for k, v in columns.items():
                add_table(k, v)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    add_table(item.get("table") or item.get("name"), item.get("columns"))
                else:
                    add_table(item)
        return linked

    def _lexical_link(self, question: str,
                      schema_map: Dict[str, List[Tuple[str, str]]]) -> Dict[str, List[str]]:
        q = " " + re.sub(r"[^A-Za-z0-9_]+", " ", question).lower() + " "
        linked: Dict[str, List[str]] = {}
        for table, cols in schema_map.items():
            t = table.lower()
            variants = {t, t[:-1] if t.endswith("s") else t + "s"}
            table_hit = any((" " + v + " ") in q for v in variants if v)
            col_hits = []
            for name, _ in cols:
                c = name.lower()
                if (" " + c + " ") in q or (" " + c.replace("_", " ") + " ") in q:
                    col_hits.append(name)
            if table_hit or col_hits:
                linked[table] = col_hits or [n for n, _ in cols]
        return linked

    def _build_pruned_schema(self, schema_map: Dict[str, List[Tuple[str, str]]],
                             linked: Dict[str, List[str]]) -> str:
        if not linked:
            return self.schema  # graceful fallback: full schema
        chunks = []
        for table, cols in schema_map.items():
            if table not in linked:
                continue
            wanted = {w.lower() for w in (linked.get(table) or [n for n, _ in cols])}
            defs = [d for n, d in cols if n.lower() in wanted] or [d for _, d in cols]
            chunks.append("CREATE TABLE {} (\n  {}\n);".format(table, ",\n  ".join(defs)))
        return "\n\n".join(chunks) if chunks else self.schema

    # --------------------------------------------------------- SQL prompting

    def _sql_prompt(self, question: str, pruned_schema: str) -> str:
        return (
            "Relevant database schema (already schema-linked; use ONLY these tables/columns):\n\n"
            + pruned_schema
            + "\n\nQuestion: " + question
            + "\n\nWrite ONE SQL query answering the question.\n"
            "Rules:\n"
            "- Use only the tables and columns shown above.\n"
            "- Output only the SQL inside a single