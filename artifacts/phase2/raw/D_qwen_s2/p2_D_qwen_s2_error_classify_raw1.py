"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies targeted repairs for up to two rounds."""

import re
from difflib import get_close_matches

try:
    from ..harness_base import SQLHarness
    from .. import bridge
except Exception:
    SQLHarness = object
    bridge = None


class P2P2DQwenS2ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        sql = self._generate_initial_sql(question)
        best_sql = sql
        history = []

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            if not sql:
                sql = best_sql

            result = self._safe_execute(sql)
            if sql:
                best_sql = sql

            if result.get("ok") and str(sql or "").strip():
                if self._is_select_statement(sql):
                    return self._finalize_sql(sql)
                error = "The generated statement executed but is not a SELECT query."
                failure_class = "semantics"
            else:
                error = str(result.get("error") or "unknown execution error")
                failure_class = self._classify_failure(sql, error, result)

            history.append(
                {
                    "round": round_idx,
                    "sql": sql,
                    "error": error,
                    "class": failure_class,
                }
            )

            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break

            repaired = self._repair(question, sql, error, failure_class, history, result)
            if not repaired or repaired.strip().lower() == str(sql or "").strip().lower():
                break

            sql = repaired

        return self._finalize_sql(best_sql)

    def _generate_initial_sql(self, question: str) -> str:
        system = "You are an expert Text-to-SQL system. Return only one SQL query."
        prompt = f"""Schema:
{getattr(self, 'schema', '')}

Question:
{question}

Write a single SQL query that answers the question. Return only SQL, no explanation."""
        return self._finalize_sql(self._llm_text(prompt, system=system))

    def _repair(self, question: str, sql: str, error: str, failure_class: str, history, result):
        if failure_class == "syntax":
            return self._fix_syntax(question, sql, error, history)
        if failure_class == "schema":
            return self._fix_schema(question, sql, error, history)
        return self._fix_semantics(question, sql, error, history, result)

    def _fix_syntax(self, question: str, sql: str, error: str, history):
        mechanical = self._mechanical_syntax_fix(sql)
        if mechanical and mechanical.lower() != str(sql or "").lower():
            return mechanical

        system = "You are a precise SQL syntax repair tool. Return only SQL."
        prompt = f"""The following SQL query failed with a syntax error.

Question:
{question}

Schema:
{getattr(self, 'schema', '')}

Original SQL:
{sql}

Syntax error:
{error}

Previous attempts:
{self._format_history(history)}

Repair only the syntax problem so the query can execute. Preserve the original intent, tables, columns, and logic as much as possible. Return only the corrected SQL query."""
        return self._finalize_sql(self._llm_text(prompt, system=system))

    def _fix_schema(self, question: str, sql: str, error: str, history):
        missing_objects = self._extract_missing_objects(error)
        candidates = self._schema_candidates(missing_objects)
        help_text = self._schema_reference_help(missing_objects, candidates)

        system = "You are a SQL schema-reference repair tool. Return only SQL."
        prompt = f"""The following SQL query failed because it references invalid schema objects.

Question:
{question}

Schema:
{getattr(self, 'schema', '')}

Original SQL:
{sql}

Schema error:
{error}

{help_text}

Previous attempts:
{self._format_history(history)}

Rewrite the query so every table and column exists exactly as in the schema. Preserve the question's intent. Return only the corrected SQL query."""
        return self._finalize_sql(self._llm_text(prompt, system=system))

    def _fix_semantics(self, question: str, sql: str, error: str, history, result):
        hints = self._semantic_hints(error)
        hint_text = "\n".join(f"- {hint}" for hint in hints) if hints else "- Preserve the intended question semantics while making the query valid."

        sample = ""
        if isinstance(result, dict) and result.get("ok"):
            rows = result.get("rows")
            if rows is not None:
                sample = f"\nReturned rows sample: {str(rows[:3])[:500]}"

        system = "You are a SQL semantic/logic repair tool. Return only SQL."
        prompt = f"""The following SQL query has a semantic or logical problem.

Question:
{question}

Schema:
{getattr(self, 'schema', '')}

Original SQL:
{sql}

Execution error:
{error}{sample}

Repair guidance:
{hint_text}

Previous attempts:
{self._format_history(history)}

Rewrite the query so it correctly answers the question and executes safely. Use only valid schema objects. Return only the corrected SQL query."""
        return self._finalize_sql(self._llm_text(prompt, system=system))

    def _classify_failure(self, sql: str, error: str, result) -> str:
        err = str(error or "").lower()
        sql_text = str(sql or "").strip()

        if not sql_text:
            return "syntax"

        schema_terms = (
            "no such table",
            "no such column",
            "unknown table",
            "unknown column",
            "table not found",
            "column not found",
            "invalid column name",
            "invalid table name",
            "does not exist",
            "undefined column",
            "undefined table",
            "ambiguous column",
            "relation \"",
            "column \"",
        )
        if any(term in err for term in schema_terms):
            return "schema"

        syntax_terms = (
            "syntax",
            "parse",
            "near",
            "unexpected",
            "expected",
            "incomplete",
            "malformed",
            "unrecognized token",
            "missing",
            "invalid input",
        )
        if any(term in err for term in syntax_terms):
            return "syntax"

        semantic_terms = (
            "ambiguous",
            "type mismatch",
            "datatype",
            "conversion",
            "overflow",
            "division by zero",
            "aggregate",
            "group by",
            "misuse",
            "not authorized",
            "permission",
            "constraint",
            "foreign key",
            "unique",
            "check",
            "invalid use",
            "illegal",
            "unsupported",
            "no such function",
            "too many",
            "too few",
            "subquery",
        )
        if any(term in err for term in semantic_terms):
            return "semantics"

        if re.search(r"no such|not found|does not exist|unknown|invalid.*(column|table|field|relation)", err):
            return "schema"

        if re.search(r"near|expected|unexpected|parse|syntax|token", err):
            return "syntax"

        return "semantics"

    def _safe_execute(self, sql: str):
        sql_text = str(sql or "").strip()
        if not sql_text:
            return {"ok": False, "rows": [], "error": "empty SQL"}

        execute = getattr(self, "execute", None)
        if execute is None:
            return {"ok": False, "rows": [], "error": "no executor available"}

        try:
            result = execute(sql_text)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            raw_ok = result.get("ok")
            if raw_ok is None:
                raw_ok = not result.get("error")
            return {
                "ok": bool(raw_ok),
                "rows": result.get("rows", []),
                "error": str(result.get("error", "") or ""),
            }

        if isinstance(result, bool):
            return {"ok": result, "rows": [], "error": "" if result else "execution failed"}

        if isinstance(result, list):
            return {"ok": True, "rows": result, "error": ""}

        return {"ok": False, "rows": [], "error": str(result)}

    def _llm_text(self, prompt: str, system: str = "") -> str:
        llm = getattr(self, "llm", None)
        if llm is None:
            return ""

        try:
            response = llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                response = llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""

        return self._coerce_llm_output(response)

    def _coerce_llm_output(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore")

        if isinstance(response, (list, tuple)):
            if not response:
                return ""
            return self._coerce_llm_output(response[0])

        if isinstance(response, dict):
            for key in ("sql", "text", "content", "answer", "response", "output", "completion"):
                if key in response:
                    return self._coerce_llm_output(response[key])

            if "choices" in response:
                return self._coerce_llm_output(response["choices"])

            if "message" in response:
                return self._coerce_llm_output(response["message"])

        if hasattr(response, "content"):
            return str(response.content)

        if hasattr(response, "text"):
            return str(response.text)

        return str(response)

    def _finalize_sql(self, text) -> str:
        if text is None:
            return ""

        sql_text = str(text).strip()
        if not sql_text:
            return ""

        if bridge is not None:
            try:
                extracted = bridge.extract_sql(sql_text)
                extracted = self._coerce_llm_output(extracted)
                if extracted.strip():
                    sql_text = extracted.strip()
            except Exception:
                pass

        if sql_text.startswith("