"""Generate SQL with the frozen weak solver, execute it, then classify every failure as syntax, schema, or semantics and dispatch it to a class-specific repair strategy for at most two rounds."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2ErrorClassify"]


class P2P2DGlmS2ErrorClassify(SQLHarness):
    """Run the solver's SQL, label the failure (syntax / schema / semantics), and route each label to a dedicated repair prompt for up to two rounds."""

    MAX_ROUNDS = 2  # maximum number of classify -> repair -> re-execute rounds

    # Engine-error fragments that identify a SCHEMA-class failure:
    # the SQL names tables / columns / functions that do not exist.
    _SCHEMA_SIGNS = (
        "no such table",
        "no such column",
        "no such function",
        "no such collation",
        "no such index",
        "no such trigger",
        "no such view",
        "no such relation",
        "no column named",
        "no column",
        "has no column",
        "does not have a column",
        "unknown column",
        "unknown table",
        "unknown database",
        "unknown function",
        "unknown schema",
        "unknown relation",
        "column not found",
        "table not found",
        "invalid column name",
        "invalid table name",
        "invalid identifier",
        "undefined column",
        "undefined table",
        "undefined function",
        "does not exist",
        "doesn't exist",
        "ambiguous column",
        "ambiguous reference",
        "missing table",
        "missing column",
    )

    # Engine-error fragments that identify a SYNTAX-class failure:
    # the statement is malformed / unparsable.
    _SYNTAX_SIGNS = (
        "syntax error",
        "error in your sql syntax",
        "parse error",
        "parser error",
        "failed to parse",
        "could not parse",
        "cannot parse",
        "unable to parse",
        "unrecognized token",
        "unexpected token",
        "unexpected end",
        "unexpected character",
        "unexpected input",
        "unterminated",
        "incomplete input",
        "invalid syntax",
        "incorrect syntax",
        "malformed sql",
        "malformed query",
        "extraneous",
        "mismatched",
        "unbalanced",
        "missing keyword",
        "missing operator",
        "missing comma",
        "missing right paren",
        "expected ",
        "expects ",
        'near "',
        "near '",
    )

    # ------------------------------------------------------------------ #
    # Low-level helpers
    # ------------------------------------------------------------------ #

    @property
    def _schema_text(self) -> str:
        return str(getattr(self, "schema", "") or "").strip()

    def _ask(self, prompt: str, system: str = "") -> str:
        """One call to the frozen solver, normalised to plain text."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("output") or ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return str(out or "").strip()

    def _sql_from(self, text: str) -> str:
        """Pull a single normalised SQL statement out of a model answer."""
        try:
            sql = bridge.extract_sql(text or "") or ""
        except Exception:
            sql = str(text or "")
        sql = str(sql).strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    def _run(self, sql: str) -> dict:
        """Execute SQL defensively: executor failures never propagate."""
        try:
            res = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "