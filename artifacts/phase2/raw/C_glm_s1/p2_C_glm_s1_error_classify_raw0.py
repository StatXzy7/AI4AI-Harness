"""Generate SQL with the frozen solver, execute it, and for up to two rounds classify each failure as syntax, schema, or semantics and apply the repair strategy specific to that failure class."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS1ErrorClassify"]


class P2P2CGlmS1ErrorClassify(SQLHarness):
    """Plan -> execute -> classify the failure (syntax / schema / semantics)
    -> dispatch the class-specific repair, for at most two repair rounds,
    keeping the last cleanly executing SQL as a fallback answer."""

    name = "P2P2CGlmS1ErrorClassify"

    # ---- failure classes -------------------------------------------------
    SYNTAX = "syntax"        # malformed / dialect-invalid SQL
    SCHEMA = "schema"        # unknown tables / columns / functions
    SEMANTICS = "semantics"  # runs fine but does not answer the question

    # initial attempt + at most this many classify-and-fix rounds
    MAX_FIX_ROUNDS = 2

    # engine error snippets that reliably mean "broken SQL grammar"
    SYNTAX_ERROR_PATTERNS = (
        "syntax",
        "parse error",
        "unterminated",
        "unrecognized token",
        "unexpected token",
        "incomplete input",
        "malformed",
        "expected",
        "missing",
        "near",
    )

    # engine error snippets that reliably mean "identifier not in schema"
    SCHEMA_ERROR_PATTERNS = (
        "no such table",
        "no such column",
        "no such function",
        "unknown column",
        "unknown table",
        "unknown function",
        "unknown database",
        "does not exist",
        "doesn't exist",
        "not found",
        "undefined column",
        "undefined table",
        "undefined function",
        "invalid column",
        "invalid table",
        "invalid identifier",
    )

    # ------------------------------------------------------------------ I/O
    def _ask(self, prompt, system=""):
        """One frozen-solver LLM call, normalised to a plain string."""
        out = ""
        try:
            out = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            # tolerate a thinner LLM signature
            try:
                out = self.llm(prompt)
            except Exception:
                out = ""
        except Exception:
            out = ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            out = ""
        return str(out)

    @staticmethod
    def _extract(text):
        """Pull the SQL statement out of an LLM reply, never raising."""
        try:
            return (bridge.extract_sql(text) or "").strip()
        except Exception:
            return ""

    def _schema_text(self):
        s = getattr(self, "schema", None)
        if isinstance(s, (list, tuple)):
            return "\n".join(str(x) for x in s) or "(no schema provided)"
        return str(s) if s else "(no schema provided)"

    def _run(self, sql):
        """Execute a candidate query; always returns {ok, rows, error}."""
        if not sql or not str(sql).strip():
            return {"ok": False, "rows": [], "error": "empty SQL"}
        try:
            res = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"execution raised: {exc}"}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "executor returned a non-dict result